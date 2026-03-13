from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from .schemas import ArtifactReference, ExecuteRealRequest

DEMO_TAG_KEY = "NovaArchitectDemo"


def _client(service_name: str, region_name: str) -> Any:
    return boto3.client(service_name, region_name=region_name)


def _instance_id_from_arn(resource_arn: str) -> str:
    return resource_arn.rsplit("/", 1)[-1]


def _autoscaling_name_from_arn(resource_arn: str) -> str:
    marker = "autoScalingGroupName/"
    if marker in resource_arn:
        return resource_arn.split(marker, 1)[1]
    return resource_arn.rsplit(":", 1)[-1]


def _s3_bucket_from_arn(resource_arn: str) -> str:
    return resource_arn.split(":::", 1)[1] if ":::" in resource_arn else resource_arn


def _evidence_file(artifact_dir: Path, run_id: str, lines: List[str]) -> ArtifactReference:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / f"{run_id}_execute_real.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return ArtifactReference(
        label="Execute Real Evidence",
        file_path=str(path.resolve()),
        format="txt",
    )


def _native_tag_fallback(
    *,
    request: ExecuteRealRequest,
    run_id: str,
    region_name: str,
) -> Tuple[bool, str]:
    action = request.action
    resource_arn = request.resource_arn
    resource_type = request.resource_type

    if resource_type == "ec2":
        ec2 = _client("ec2", region_name)
        instance_id = _instance_id_from_arn(resource_arn)
        if action == "apply_demo_tag":
            ec2.create_tags(Resources=[instance_id], Tags=[{"Key": DEMO_TAG_KEY, "Value": run_id}])
            return True, f"native_ec2_tag_applied:{instance_id}"
        ec2.delete_tags(Resources=[instance_id], Tags=[{"Key": DEMO_TAG_KEY}])
        return True, f"native_ec2_tag_removed:{instance_id}"

    if resource_type == "rds":
        rds = _client("rds", region_name)
        if action == "apply_demo_tag":
            rds.add_tags_to_resource(ResourceName=resource_arn, Tags=[{"Key": DEMO_TAG_KEY, "Value": run_id}])
            return True, "native_rds_tag_applied"
        rds.remove_tags_from_resource(ResourceName=resource_arn, TagKeys=[DEMO_TAG_KEY])
        return True, "native_rds_tag_removed"

    if resource_type == "autoscaling":
        asg = _client("autoscaling", region_name)
        asg_name = _autoscaling_name_from_arn(resource_arn)
        if action == "apply_demo_tag":
            asg.create_or_update_tags(
                Tags=[
                    {
                        "ResourceId": asg_name,
                        "ResourceType": "auto-scaling-group",
                        "Key": DEMO_TAG_KEY,
                        "Value": run_id,
                        "PropagateAtLaunch": False,
                    }
                ]
            )
            return True, f"native_asg_tag_applied:{asg_name}"
        asg.delete_tags(
            Tags=[{"ResourceId": asg_name, "ResourceType": "auto-scaling-group", "Key": DEMO_TAG_KEY}]
        )
        return True, f"native_asg_tag_removed:{asg_name}"

    if resource_type == "s3":
        s3 = _client("s3", region_name)
        bucket = _s3_bucket_from_arn(resource_arn)
        existing_tags: List[Dict[str, str]] = []
        try:
            existing_tags = s3.get_bucket_tagging(Bucket=bucket).get("TagSet", [])
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"NoSuchTagSet", "NoSuchBucket"}:
                raise

        tag_map = {item["Key"]: item["Value"] for item in existing_tags if "Key" in item and "Value" in item}
        if action == "apply_demo_tag":
            tag_map[DEMO_TAG_KEY] = run_id
        else:
            tag_map.pop(DEMO_TAG_KEY, None)

        if tag_map:
            s3.put_bucket_tagging(
                Bucket=bucket,
                Tagging={"TagSet": [{"Key": key, "Value": value} for key, value in sorted(tag_map.items())]},
            )
        else:
            s3.delete_bucket_tagging(Bucket=bucket)
        return True, f"native_s3_tag_{'applied' if action == 'apply_demo_tag' else 'removed'}:{bucket}"

    return False, "native_tag_fallback_not_supported"


def execute_aws_api_safe_tag(
    *,
    request: ExecuteRealRequest,
    run_id: str,
    region_name: str,
    artifact_dir: Path,
) -> Dict[str, Any]:
    steps: List[Dict[str, Any]] = []
    evidence_lines: List[str] = [f"run_id={run_id}", f"region={region_name}", f"mode=aws_api_safe_tag"]

    rgta = _client("resourcegroupstaggingapi", region_name)
    try:
        if request.action == "apply_demo_tag":
            response = rgta.tag_resources(
                ResourceARNList=[request.resource_arn],
                Tags={DEMO_TAG_KEY: run_id},
            )
            failed = response.get("FailedResourcesMap", {})
            if failed:
                steps.append(
                    {
                        "step": 1,
                        "action": "rgta_tag_resources",
                        "result": f"partial_failed:{list(failed.keys())[0]}",
                    }
                )
                ok, message = _native_tag_fallback(request=request, run_id=run_id, region_name=region_name)
                steps.append({"step": 2, "action": "native_tag_fallback", "result": "ok" if ok else f"failed:{message}"})
                status = "success" if ok else "partial"
            else:
                steps.append({"step": 1, "action": "rgta_tag_resources", "result": "ok"})
                status = "success"
        else:
            response = rgta.untag_resources(
                ResourceARNList=[request.resource_arn],
                TagKeys=[DEMO_TAG_KEY],
            )
            failed = response.get("FailedResourcesMap", {})
            if failed:
                steps.append(
                    {
                        "step": 1,
                        "action": "rgta_untag_resources",
                        "result": f"partial_failed:{list(failed.keys())[0]}",
                    }
                )
                ok, message = _native_tag_fallback(request=request, run_id=run_id, region_name=region_name)
                steps.append({"step": 2, "action": "native_untag_fallback", "result": "ok" if ok else f"failed:{message}"})
                status = "success" if ok else "partial"
            else:
                steps.append({"step": 1, "action": "rgta_untag_resources", "result": "ok"})
                status = "success"
    except Exception as exc:
        ok, message = _native_tag_fallback(request=request, run_id=run_id, region_name=region_name)
        steps.append({"step": 1, "action": "rgta_call", "result": f"failed:{exc.__class__.__name__}"})
        steps.append({"step": 2, "action": "native_tag_fallback", "result": "ok" if ok else f"failed:{message}"})
        status = "success" if ok else "failed"

    notes = (
        "Reversible demo tag operation completed."
        if status == "success"
        else "Reversible demo tag operation completed partially; check step results."
    )
    evidence_lines.extend([f"step_{step['step']}={step['action']}:{step['result']}" for step in steps])
    evidence_ref = _evidence_file(artifact_dir, run_id, evidence_lines)
    return {"status": status, "steps": steps, "notes": notes, "evidence_refs": [evidence_ref]}


def execute_console_safe(
    *,
    request: ExecuteRealRequest,
    run_id: str,
    region_name: str,
    artifact_dir: Path,
) -> Dict[str, Any]:
    if os.getenv("ENABLE_REAL_AWS_CONSOLE", "0").strip() != "1":
        return {
            "status": "blocked",
            "steps": [{"step": 1, "action": "console_mode_gate", "result": "blocked:ENABLE_REAL_AWS_CONSOLE_not_enabled"}],
            "notes": "aws_console_safe mode is disabled. Use aws_api_safe_tag or enable explicit console mode.",
            "evidence_refs": [],
        }

    console_allowlist = os.getenv(
        "REAL_AWS_CONSOLE_ALLOWLIST",
        "console.aws.amazon.com,us-east-1.console.aws.amazon.com",
    )
    host = "console.aws.amazon.com"
    if host not in [item.strip() for item in console_allowlist.split(",") if item.strip()]:
        return {
            "status": "blocked",
            "steps": [{"step": 1, "action": "console_allowlist_check", "result": "blocked:console_host_not_allowlisted"}],
            "notes": "Console allowlist does not permit AWS console host.",
            "evidence_refs": [],
        }

    if request.action != "open_console_view":
        return {
            "status": "blocked",
            "steps": [{"step": 1, "action": "console_action_policy", "result": "blocked:only_open_console_view_allowed"}],
            "notes": "Phase 6 console mode allows read-only open_console_view only.",
            "evidence_refs": [],
        }

    url = f"https://console.aws.amazon.com/{request.resource_type}/home?region={region_name}"
    steps = [
        {"step": 1, "action": "validate_allowlist", "result": "ok"},
        {"step": 2, "action": "open_console_view", "result": f"ok:{url}"},
    ]
    evidence_ref = _evidence_file(
        artifact_dir,
        run_id,
        [
            f"run_id={run_id}",
            f"mode=aws_console_safe",
            f"resource_arn={request.resource_arn}",
            f"url={url}",
        ],
    )
    return {
        "status": "success",
        "steps": steps,
        "notes": "Generated safe read-only console navigation target.",
        "evidence_refs": [evidence_ref],
    }
