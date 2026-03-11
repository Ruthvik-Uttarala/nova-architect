# NovaArchitect Phase 1 Backend

This Phase 1 backend implements:
- FastAPI health and analyze endpoints
- Bedrock Converse call to Nova 2 Lite
- Strict Plan schema validation with one retry and guaranteed-valid fallback
- Deterministic simulation from local snapshot JSON
- Local unit tests with Bedrock stubs (no live Bedrock calls in tests)

## Prerequisites
- Python virtual environment already created at `.\venv`
- AWS credentials configured locally (for optional live smoke test)

Use the model ID shown in Bedrock Model Catalog for your region; default tested: `us.amazon.nova-2-lite-v1:0`.

## Setup (PowerShell)
```powershell
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

## Run API (PowerShell)
```powershell
uvicorn backend.app.main:app --reload
```

Health check:
```powershell
Invoke-RestMethod -Method Get http://127.0.0.1:8000/
```

Analyze request:
```powershell
$body = @{ goal = "Reduce monthly AWS costs while improving uptime and security" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/analyze -ContentType "application/json" -Body $body
```

## Run Tests (PowerShell)
```powershell
pytest backend\tests -q
```

## Optional Live Bedrock Smoke Test (PowerShell)
```powershell
python backend\scripts\smoke_bedrock_converse.py
```

## Environment Notes
- Recommended defaults:
  - `AWS_REGION=us-east-1`
  - `BEDROCK_MODEL_ID=us.amazon.nova-2-lite-v1:0`
- Converse API requires IAM permission: `bedrock:InvokeModel`.
- Never commit `.env` files containing secrets.

