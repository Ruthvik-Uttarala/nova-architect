from __future__ import annotations

from fastapi.testclient import TestClient

import backend.app.main as main_module
from backend.app.aws_discovery import discover_live_snapshot


class _Paginator:
    def __init__(self, pages):
        self.pages = pages

    def paginate(self, **_kwargs):
        return self.pages


class _Client:
    def __init__(self, *, data=None, paginators=None, errors=None):
        self.data = data or {}
        self.paginators = paginators or {}
        self.errors = errors or {}

    def __getattr__(self, name):
        if name in self.errors:
            raise self.errors[name]
        if name == "get_paginator":
            return lambda op: _Paginator(self.paginators.get(op, []))
        if name in self.data:
            return self.data[name]
        raise AttributeError(name)


def _factory_with_partial_failure(service_name: str, _region: str):
    if service_name == "sts":
        return _Client(data={"get_caller_identity": lambda: {"Account": "111122223333", "Arn": "arn:aws:iam::111122223333:user/test"}})
    if service_name == "ec2":
        return _Client(
            paginators={
                "describe_instances": [
                    {
                        "Reservations": [
                            {
                                "Instances": [
                                    {
                                        "InstanceId": "i-1",
                                        "InstanceType": "t3.micro",
                                        "Placement": {"AvailabilityZone": "us-east-1a"},
                                        "State": {"Name": "running"},
                                        "Tags": [{"Key": "Name", "Value": "web-1"}],
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        )
    if service_name == "autoscaling":
        return _Client(paginators={"describe_auto_scaling_groups": [{"AutoScalingGroups": []}]})
    if service_name == "rds":
        raise RuntimeError("rds_down")
    if service_name == "s3":
        return _Client(
            data={
                "list_buckets": lambda: {"Buckets": [{"Name": "demo-bucket"}]},
                "get_bucket_encryption": lambda Bucket: (_ for _ in ()).throw(Exception("no_encryption")),
            }
        )
    if service_name == "resourcegroupstaggingapi":
        return _Client(paginators={"get_resources": [[]]})
    raise RuntimeError(service_name)


def _factory_success(service_name: str, _region: str):
    if service_name == "sts":
        return _Client(data={"get_caller_identity": lambda: {"Account": "111122223333", "Arn": "arn:aws:iam::111122223333:user/test"}})
    if service_name == "ec2":
        return _Client(
            paginators={
                "describe_instances": [
                    {
                        "Reservations": [
                            {
                                "Instances": [
                                    {
                                        "InstanceId": "i-1",
                                        "InstanceType": "t3.micro",
                                        "Placement": {"AvailabilityZone": "us-east-1a"},
                                        "State": {"Name": "running"},
                                        "Tags": [{"Key": "Name", "Value": "web-1"}],
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        )
    if service_name == "autoscaling":
        return _Client(paginators={"describe_auto_scaling_groups": [{"AutoScalingGroups": []}]})
    if service_name == "rds":
        return _Client(
            paginators={
                "describe_db_instances": [
                    {
                        "DBInstances": [
                            {
                                "DBInstanceIdentifier": "db-1",
                                "DBInstanceArn": "arn:aws:rds:us-east-1:111122223333:db:db-1",
                                "Engine": "postgres",
                                "MultiAZ": False,
                                "StorageEncrypted": True,
                                "DBInstanceClass": "db.t3.micro",
                            }
                        ]
                    }
                ]
            }
        )
    if service_name == "s3":
        return _Client(
            data={
                "list_buckets": lambda: {"Buckets": [{"Name": "demo-bucket"}]},
                "get_bucket_encryption": lambda Bucket: {"ServerSideEncryptionConfiguration": {}},
            }
        )
    if service_name == "resourcegroupstaggingapi":
        return _Client(paginators={"get_resources": [[]]})
    raise RuntimeError(service_name)


def test_discover_partial_success_with_warnings() -> None:
    result = discover_live_snapshot(region="us-east-1", force_refresh=True, client_factory=_factory_with_partial_failure)
    assert result["discovery_mode"] == "live_aws"
    assert result["summary"]["partial_failure_count"] >= 1
    assert any("rds_discovery_failed" in warning for warning in result["warnings"])
    assert "services" in result["snapshot"]


def test_discover_normalizes_snapshot_shape() -> None:
    result = discover_live_snapshot(region="us-east-1", force_refresh=True, client_factory=_factory_success)
    snapshot = result["snapshot"]
    assert set(snapshot["services"].keys()) == {"ec2", "rds", "s3"}
    assert isinstance(snapshot["services"]["ec2"], list)
    assert isinstance(snapshot["known_risks"], list)


def test_discover_endpoint_fallback_when_discovery_raises(monkeypatch) -> None:
    def _raise(*_args, **_kwargs):
        raise RuntimeError("aws_unavailable")

    monkeypatch.setattr(main_module, "discover_live_snapshot", _raise)
    client = TestClient(main_module.app)
    response = client.post("/discover", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["discovery_mode"] == "fallback"
    assert "snapshot" in payload
    assert payload["warnings"]
