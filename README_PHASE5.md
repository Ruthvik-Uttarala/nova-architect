# NovaArchitect Phase 5 (Hybrid Voice + Executive Reporting)

Phase 5 adds:
- Hybrid, demo-safe voice enhancement (`/voice`) that feeds goal input.
- Deterministic executive report artifacts (`/report`) from analyze/apply outputs.
- Lightweight local evidence history for analyze/voice/apply/report events.

## Safety Statement
- `/analyze` remains the core Bedrock Nova 2 Lite reasoning path.
- `/apply` remains mock-console-only automation.
- `/voice` is enhancement-only and fallback-safe.
- No real AWS console automation and no real AWS resource mutation.

## Environment Variables
- Core:
  - `AWS_REGION`
  - `BEDROCK_MODEL_ID`
  - `ENABLE_LIVE_BEDROCK`
- Apply/Nova Act:
  - `ENABLE_NOVA_ACT`
  - `NOVA_ACT_API_KEY`
  - `NOVA_ACT_HEADLESS`
- Voice/Nova Sonic:
  - `ENABLE_NOVA_SONIC` (`0` default for reliability)
  - `NOVA_SONIC_MODEL_ID`
  - `NOVA_SONIC_REGION`
  - `NOVA_SONIC_MAX_TOKENS`
  - `NOVA_SONIC_TEMPERATURE`
  - `NOVA_SONIC_TOP_P`
- Artifacts:
  - `NOVA_ARTIFACTS_DIR`

## Windows PowerShell Commands
Install backend dependencies:
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

## Manual `/voice` Verification
Fallback mode:
```powershell
$env:ENABLE_NOVA_SONIC="0"
$body = @{
  transcript = "Optimize for lower cost and strong reliability"
  latest_goal = "Reduce spend safely"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/voice -ContentType "application/json" -Body $body
```

Live Sonic mode (if configured):
```powershell
$env:ENABLE_NOVA_SONIC="1"
$env:NOVA_SONIC_MODEL_ID="us.amazon.nova-sonic-v1:0"
$env:NOVA_SONIC_REGION="us-east-1"
```

## Manual `/report` Verification
1. Run `/analyze` first.
2. Optionally run `/apply`.
3. Generate report:
```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/report -ContentType "application/json" -Body "{}"
```

Confirm:
- `report_id`, `executive_summary`, and `highlights` exist.
- `artifact_refs` points to local JSON/Markdown artifact files.

## End-to-End UI Check
1. Use Mic to capture or paste transcript.
2. Confirm goal box updates from `normalized_goal`.
3. Click Analyze (primary action).
4. Click Generate Report Artifact.
5. Optionally click Apply Changes to see run log.
