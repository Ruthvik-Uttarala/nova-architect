# NovaArchitect Phase 4 (Live Bedrock Analyze)

Phase 4 upgrades `/analyze` to use real Amazon Nova through Amazon Bedrock (Converse API) with strict JSON validation, retry, and guaranteed fallback.

`/apply` remains scoped to local mock-console automation only.

## Safety
- `/analyze` uses Bedrock reasoning only.
- `/apply` automates only `http://127.0.0.1:3000/console`.
- No real AWS console automation.
- No real AWS resource mutation.

## Environment Variables
- `AWS_REGION` (default `us-east-1`)
- `BEDROCK_MODEL_ID` (used exactly as configured in your environment if set)
- `ENABLE_LIVE_BEDROCK`
  - `1` => live Bedrock path
  - `0` => deterministic fallback/demo path (no Bedrock call)
- `NOVA_MAX_TOKENS` (default `1400`)
- `NOVA_TEMPERATURE` (default `0.1`)
- `NOVA_TOP_P` (default `0.9`)

Optional:
- `ENABLE_ANALYZE_ARTIFACTS=1` to write local analyze evidence artifacts
- `ANALYZE_ARTIFACTS_DIR` to override artifact folder path

## Commands (Windows PowerShell)
Install dependencies:
```powershell
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

Run backend tests:
```powershell
pytest backend\tests -q
```

Start backend:
```powershell
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Start frontend:
```powershell
cd frontend
npm install
npm run dev
```

## Manual Live Analyze Verification
Set live mode + region/model:
```powershell
$env:ENABLE_LIVE_BEDROCK="1"
$env:AWS_REGION="us-east-1"
# Use your machine's configured model ID exactly
$env:BEDROCK_MODEL_ID="us.amazon.nova-2-lite-v1:0"
```

Call analyze:
```powershell
$body = @{ goal = "Reduce monthly cost while improving uptime and security" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/analyze -ContentType "application/json" -Body $body
```

What to confirm:
- `plan` + `simulation` are present.
- `used_fallback` indicates whether fallback was needed.
- Optional `analyze_metadata` shows model, region, mode (`live_bedrock` or `fallback`), retries, fallback flag.
- Frontend trust badge reflects metadata when present.
