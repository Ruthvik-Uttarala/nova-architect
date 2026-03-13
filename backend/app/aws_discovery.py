from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

DEFAULT_DISCOVERY_TTL_SECONDS = 120
_DISCOVERY_CACHE: Dict[str, Dict[str, Any]] = {}


def _ttl_seconds() -> int:
    raw = os.getenv("DISCOVERY_CACHE_TTL_SECONDS", str(DEFAULT_DISCOVERY_TTL_SECONDS)).strip()
    try:
        value = int(raw)
        return max(0, value)
    except ValueError:
        return DEFAULT_DISCOVERY_TTL_SECONDS


def _principal_type(caller_arn: str) -> str:
    if ":assumed-role/" in caller_arn:
        return "assumed_role"
    if ":user/" in caller_arn:
        return "iam_user"
    if ":role/" in caller_arn:
        return "iam_role"
    return "unknown"


def _extract_name(tags: List[Dict[str, str]]) -> str:
    for tag in tags:
        if tag.get("Key") == "Name":
            return tag.get("Value", "")
    return ""


def _default_snapshot(account_id: str, region: str) -> Dict[str, Any]:
    return {
        "account": {
            "account_id": account_id,
            "region": region,
            "environment": "discovered",
        },
        "services": {
            "ec2": [],
            "rds": [],
            "s3": [],
        },
        "traffic": {
            "avg_requests_per_min": 1000,
            "peak_multiplier": 2.5,
            "peak_duration_min": 15,
            "inferred": True,
        },
        "constraints": {
            "target_uptime": "99.95",
            "max_budget_usd_per_month": 5000,
            "inferred": True,
        },
        "known_risks": [],
    }


def _cache_key(region: str) -> str:
    return f"discovery::{region}"


def discover_live_snapshot(
    *,
    region: Optional[str] = None,
    force_refresh: bool = False,
    client_factory: Optional[Callable[[str, str], Any]] = None,
) -> Dict[str, Any]:
    region_name = (region or os.getenv("AWS_REGION") or "us-east-1").strip()
    key = _cache_key(region_name)
    ttl = _ttl_seconds()
    now = time.time()

    if not force_refresh and ttl > 0:
        cached = _DISCOVERY_CACHE.get(key)
        if cached and (now - cached["cached_at_epoch"]) <= ttl:
            payload = cached["payload"].copy()
            payload["summary"] = {**payload["summary"], "cache_hit": True}
            return payload

    def _client(service_name: str, client_region: str) -> Any:
        if client_factory is not None:
            return client_factory(service_name, client_region)
        return boto3.client(service_name, region_name=client_region)

    warnings: List[str] = []
    partial_failures = 0

    sts_client = _client("sts", region_name)
    identity_raw = sts_client.get_caller_identity()
    account_id = identity_raw.get("Account", "unknown")
    caller_arn = identity_raw.get("Arn", "unknown")
    identity = {
        "account_id": account_id,
        "caller_arn": caller_arn,
        "principal_type": _principal_type(caller_arn),
    }

    snapshot = _default_snapshot(account_id, region_name)

    # EC2 discovery
    try:
        ec2_client = _client("ec2", region_name)
        paginator = ec2_client.get_paginator("describe_instances")
        ec2_items: List[Dict[str, Any]] = []
        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    tags = instance.get("Tags", [])
                    ec2_items.append(
                        {
                            "name": _extract_name(tags) or instance.get("InstanceId", ""),
                            "instance_id": instance.get("InstanceId", ""),
                            "instance_type": instance.get("InstanceType", ""),
                            "az": instance.get("Placement", {}).get("AvailabilityZone"),
                            "state": instance.get("State", {}).get("Name", "unknown"),
                            "autoscaling_group": next(
                                (
                                    tag.get("Value")
                                    for tag in tags
                                    if tag.get("Key") == "aws:autoscaling:groupName"
                                ),
                                None,
                            ),
                            "monthly_cost_usd": 0.0,
                            "inferred": True,
                        }
                    )
        snapshot["services"]["ec2"] = ec2_items
    except Exception as exc:
        partial_failures += 1
        warnings.append(f"ec2_discovery_failed:{exc.__class__.__name__}")

    # Auto Scaling discovery
    asg_count = 0
    try:
        asg_client = _client("autoscaling", region_name)
        paginator = asg_client.get_paginator("describe_auto_scaling_groups")
        for page in paginator.paginate():
            asg_count += len(page.get("AutoScalingGroups", []))
    except Exception as exc:
        partial_failures += 1
        warnings.append(f"autoscaling_discovery_failed:{exc.__class__.__name__}")

    # RDS discovery
    try:
        rds_client = _client("rds", region_name)
        paginator = rds_client.get_paginator("describe_db_instances")
        rds_items: List[Dict[str, Any]] = []
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                rds_items.append(
                    {
                        "name": db.get("DBInstanceIdentifier", ""),
                        "arn": db.get("DBInstanceArn", ""),
                        "engine": db.get("Engine", ""),
                        "multi_az": bool(db.get("MultiAZ", False)),
                        "storage_encrypted": bool(db.get("StorageEncrypted", False)),
                        "instance_class": db.get("DBInstanceClass", ""),
                        "monthly_cost_usd": 0.0,
                        "inferred": True,
                    }
                )
        snapshot["services"]["rds"] = rds_items
    except Exception as exc:
        partial_failures += 1
        warnings.append(f"rds_discovery_failed:{exc.__class__.__name__}")

    # S3 discovery
    s3_items: List[Dict[str, Any]] = []
    try:
        s3_client = _client("s3", region_name)
        buckets = s3_client.list_buckets().get("Buckets", [])
        for bucket in buckets:
            bucket_name = bucket.get("Name", "")
            encrypted = True
            try:
                s3_client.get_bucket_encryption(Bucket=bucket_name)
                encrypted = True
            except ClientError as exc:
                code = exc.response.get("Error", {}).get("Code", "")
                if code in {"ServerSideEncryptionConfigurationNotFoundError", "NoSuchBucket"}:
                    encrypted = False
                else:
                    warnings.append(f"s3_encryption_check_failed:{bucket_name}:{code or exc.__class__.__name__}")
                    encrypted = False
            s3_items.append(
                {
                    "name": bucket_name,
                    "arn": f"arn:aws:s3:::{bucket_name}",
                    "default_encryption": encrypted,
                    "monthly_cost_usd": 0.0,
                    "inferred": True,
                }
            )
        snapshot["services"]["s3"] = s3_items
    except Exception as exc:
        partial_failures += 1
        warnings.append(f"s3_discovery_failed:{exc.__class__.__name__}")

    # Optional tagging inventory call (best effort only).
    try:
        tagging = _client("resourcegroupstaggingapi", region_name)
        paginator = tagging.get_paginator("get_resources")
        for _ in paginator.paginate(ResourcesPerPage=50):
            break
    except Exception as exc:
        warnings.append(f"tagging_api_unavailable:{exc.__class__.__name__}")

    known_risks: List[str] = []
    ec2_items = snapshot["services"].get("ec2", [])
    rds_items = snapshot["services"].get("rds", [])
    s3_items = snapshot["services"].get("s3", [])

    if ec2_items and asg_count == 0:
        known_risks.append("no_autoscaling")
    azs = {item.get("az") for item in ec2_items if item.get("az")}
    if len(azs) <= 1 and ec2_items:
        known_risks.append("single_az_deployment")
    if any(not bool(item.get("multi_az", False)) for item in rds_items):
        if "single_az_deployment" not in known_risks:
            known_risks.append("single_az_deployment")
    if any(item.get("default_encryption") is False for item in s3_items):
        known_risks.append("s3_default_encryption_disabled")
    snapshot["known_risks"] = known_risks

    payload = {
        "identity": identity,
        "snapshot": snapshot,
        "summary": {
            "ec2_count": len(ec2_items),
            "rds_count": len(rds_items),
            "s3_count": len(s3_items),
            "autoscaling_count": asg_count,
            "partial_failure_count": partial_failures,
            "cache_hit": False,
        },
        "warnings": warnings,
        "discovery_mode": "live_aws",
        "discovered_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    _DISCOVERY_CACHE[key] = {"cached_at_epoch": now, "payload": payload}
    return payload
