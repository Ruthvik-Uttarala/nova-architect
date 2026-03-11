# NovaArchitect Phase 2

Phase 2 adds:
- Next.js single-screen UI for analyze results and apply run logs
- Next.js proxy routes for `/analyze` and `/apply`
- Mock console page at `/console` with stable `data-testid` attributes
- Backend deterministic `POST /apply` simulation endpoint

## Backend (Windows PowerShell)
```powershell
.\venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Note: `--reload` may fail on some Windows environments.

## Backend Tests
```powershell
pytest backend\tests -q
```

## Frontend (Windows PowerShell)
```powershell
cd frontend
npm install
npm run dev
```

Frontend default URL: `http://127.0.0.1:3000`

## Frontend Environment
Create or keep:
`frontend/.env.local`
```env
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
```

## Manual Verification
1. Start backend on port `8000`.
2. Start frontend on port `3000`.
3. Open `http://127.0.0.1:3000`.
4. Enter goal and click **Analyze**.
5. Confirm reasoning cards, tradeoff table, metrics, and scenarios render.
6. Click **Apply Changes** and confirm deterministic run log appears.
7. Open `http://127.0.0.1:3000/console` and confirm UI controls and `data-testid` hooks exist.

