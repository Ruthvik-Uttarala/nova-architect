# NovaArchitect Phase 3 (Nova Act on Mock Console)

Phase 3 adds real Nova Act execution behind a feature flag for `/apply`, targeting only the local mock console:
`http://127.0.0.1:3000/console`

## Safety
- Automation is scoped to the local mock console only.
- Do not automate real AWS Console.
- Do not mutate real AWS resources.

## Environment Variables (PowerShell)
```powershell
$env:ENABLE_NOVA_ACT="1"
$env:NOVA_ACT_API_KEY="YOUR_NOVA_ACT_API_KEY"
# Optional: show browser UI instead of headless mode
$env:NOVA_ACT_HEADLESS="0"
```

Defaults:
- `ENABLE_NOVA_ACT=0` keeps deterministic simulated `/apply` behavior.
- `NOVA_ACT_HEADLESS` defaults to headless mode unless set to `0`.

## Run Backend + Frontend
Backend:
```powershell
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Frontend:
```powershell
cd frontend
npm install
npm run dev
```

## Manual `/apply` Test
With frontend and backend both running:
```powershell
python backend\scripts\smoke_nova_act_apply.py
```

Direct request example:
```powershell
$body = @{ actions = @("resize_instance","enable_autoscaling","enable_s3_encryption") } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/apply -ContentType "application/json" -Body $body
```

