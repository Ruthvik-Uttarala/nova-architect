# NovaArchitect Phase 6 (Dual-Mode: Sandbox + Live AWS)

Phase 6 keeps the demo-safe sandbox path and adds a guarded real AWS path.

## What Phase 6 Adds
- `POST /discover`: live AWS inventory discovery normalized to NovaArchitect snapshot shape.
- `POST /analyze` additive support for:
  - `snapshot_mode: "sample" | "live_aws"`
  - optional `discovered_snapshot`.
- `POST /execute-real`: approval-gated, policy-enforced real execution path.
- Real execution in this phase is restricted to:
  - read-only discovery/navigation
  - reversible demo tagging (`NovaArchitectDemo=<run_id>`) and rollback.

## Safety Model
- Sandbox mode (`Sample Demo`) remains fully intact and default-safe.
- Real AWS mode is explicit and should be tested only in a dedicated dev/staging account.
- No destructive operations are allowed in Phase 6.
- No root credentials.

## Recommended Test Account Checklist
- Dedicated dev/staging AWS account.
- Least-privilege IAM user/role (no root credentials).
- One known EC2 or RDS test resource ARN available for demo tagging.
- Bedrock invoke permission confirmed for Nova analyze path.

## Core Environment Variables
- `AWS_REGION`
- `BEDROCK_MODEL_ID`
- `ENABLE_LIVE_BEDROCK`
- `ENABLE_REAL_AWS_MODE`
- `DISCOVERY_CACHE_TTL_SECONDS`
- `ENABLE_REAL_AWS_CONSOLE`
- `REAL_AWS_CONSOLE_ALLOWLIST`
- `NOVA_ARTIFACTS_DIR`

## Least-Privilege IAM Guidance (Template)
Grant only what is required for Phase 6:
- `bedrock:InvokeModel`
- `sts:GetCallerIdentity`
- `ec2:DescribeInstances`
- `autoscaling:DescribeAutoScalingGroups`
- `rds:DescribeDBInstances`
- `s3:ListAllMyBuckets`
- `s3:GetEncryptionConfiguration`
- `s3:GetBucketTagging`
- `s3:PutBucketTagging`
- `s3:DeleteBucketTagging`
- `tag:GetResources`
- `tag:TagResources`
- `tag:UntagResources`
- Native safe tag fallback (only if needed):
  - `ec2:CreateTags`, `ec2:DeleteTags`
  - `rds:AddTagsToResource`, `rds:RemoveTagsFromResource`
  - `autoscaling:CreateOrUpdateTags`, `autoscaling:DeleteTags`

## PowerShell Commands
Install backend deps:
```powershell
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Run tests:
```powershell
venv\Scripts\python.exe -m pytest backend\tests -q
```

Start backend:
```powershell
venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Start frontend:
```powershell
cd frontend
npm install
npm run dev
```

## Verify Discover
```powershell
$body = @{ force_refresh = $false } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/discover -ContentType "application/json" -Body $body
```

## Verify Analyze with Live Snapshot Mode
```powershell
$body = @{ goal = "Optimize cost with reliability guardrails"; snapshot_mode = "live_aws" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/analyze -ContentType "application/json" -Body $body
```

## Verify Execute Real (Safe Tag / Rollback)
```powershell
$apply = @{
  execution_mode = "aws_api_safe_tag"
  resource_arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0"
  resource_type = "ec2"
  action = "apply_demo_tag"
  approval_confirmed = $true
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/execute-real -ContentType "application/json" -Body $apply

$rollback = @{
  execution_mode = "aws_api_safe_tag"
  resource_arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0"
  resource_type = "ec2"
  action = "remove_demo_tag"
  approval_confirmed = $true
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/execute-real -ContentType "application/json" -Body $rollback
```

## Verify Console-Safe Mode (Opt-in)
```powershell
$env:ENABLE_REAL_AWS_CONSOLE="1"
$console = @{
  execution_mode = "aws_console_safe"
  resource_arn = "arn:aws:ec2:us-east-1:123456789012:instance/i-0123456789abcdef0"
  resource_type = "ec2"
  action = "open_console_view"
  approval_confirmed = $true
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/execute-real -ContentType "application/json" -Body $console
```
