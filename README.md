# NovaArchitect

Autonomous Infrastructure Strategy Agent built with Amazon Nova 2 Lite, Nova Act, and Nova 2 Sonic.

NovaArchitect helps operators reduce unnecessary AWS cost while preserving uptime and improving security posture. Instead of giving static recommendations, it generates a structured optimization plan, simulates before-and-after impact, and supports safe action workflows through a judge-friendly UI.

## What it does

NovaArchitect takes an infrastructure snapshot and turns it into:

- identified issues with evidence
- a multi-step optimization plan
- a tradeoff matrix across cost, uptime, and security
- simulated before-and-after metrics
- executive-ready summary and report artifacts
- optional safe action workflow through a mock console or sandbox flow

## Why it matters

Cloud teams often face the same problem: they either overprovision and waste money or cut too aggressively and risk outages. Existing tools usually stop at alerts and static suggestions. NovaArchitect is built to fill the missing layer between detection and action.

## Core Amazon Nova usage

- **Amazon Nova 2 Lite**  
  Used for structured multi-objective reasoning and plan generation through Amazon Bedrock.

- **Amazon Nova Act**  
  Used to bridge recommendation to action through safe UI automation workflows.

- **Amazon Nova 2 Sonic**  
  Used for voice-driven goal input in push-to-talk style interactions.

## Key features

- simple single-screen UI
- goal-based infrastructure optimization
- deterministic simulation for stable demo results
- before vs after monthly cost comparison
- uptime and security tradeoff visibility
- report artifact generation
- sandbox apply flow
- mock console support
- graceful separation between Sample Demo mode and Live AWS mode

## Demo modes

### Sample Demo
This is the recommended and most reliable evaluation path.

Use Sample Demo to:
- enter a cost optimization goal
- click Analyze
- view KPI cards and summary output
- generate report artifacts
- demonstrate the safe sandbox workflow

### Live AWS
This mode is experimental and intended for controlled local testing with proper AWS configuration. It should not be required for judging.

## Example goal

Use this exact goal for the best demo:

`Reduce unnecessary monthly AWS cost while preserving uptime and improving security posture.`

## Architecture overview

### Frontend
- Next.js
- TypeScript
- Tailwind CSS
- Recharts

### Backend
- FastAPI
- Python
- schema validation and orchestration
- deterministic simulation logic
- artifact generation

### Model and automation layer
- Amazon Bedrock
- Amazon Nova 2 Lite
- Amazon Nova Act
- Amazon Nova 2 Sonic

### Artifacts
- local report outputs
- automation logs
- evidence artifacts for demo workflows

## High-level flow

1. user enters a goal by text or voice
2. frontend sends request to backend
3. backend loads infrastructure snapshot data
4. Nova 2 Lite generates a structured plan
5. backend validates output against strict contracts
6. simulation engine computes before-and-after metrics
7. frontend renders KPI cards, summary, and recommendations
8. user can trigger a safe action flow
9. system generates a report artifact and summary output

## Tech stack

- Python
- FastAPI
- Next.js
- TypeScript
- Tailwind CSS
- Recharts
- Amazon Bedrock
- Amazon Nova 2 Lite
- Amazon Nova Act
- Amazon Nova 2 Sonic

## Project structure

\`\`\`text
nova-architect/
├─ backend/
│  ├─ app/
│  ├─ tests/
│  ├─ artifacts/
│  └─ artifacts_phase5_test/
├─ frontend/
│  ├─ app/
│  ├─ lib/
│  └─ public/
├─ .env.example
└─ README.md
\`\`\`

## Local setup

### 1. Clone the repo

\`\`\`bash
git clone https://github.com/Ruthvik-Uttarala/nova-architect.git
cd nova-architect
\`\`\`

### 2. Backend setup

Create and activate a virtual environment, then install dependencies.

#### Windows PowerShell

\`\`\`powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
\`\`\`

### 3. Frontend setup

\`\`\`bash
cd frontend
npm install
cd ..
\`\`\`

## Run locally

### Start backend

From the repo root:

\`\`\`powershell
.\venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
\`\`\`

### Start frontend

In a second terminal:

\`\`\`powershell
cd frontend
npm run dev -- -H 127.0.0.1 -p 3000
\`\`\`

### Open the app

- Frontend: `http://127.0.0.1:3000`
- Backend health check: `http://127.0.0.1:8000`

## Recommended demo and judge flow

1. open the app
2. keep **Sample Demo** selected
3. keep or paste the default goal:  
   `Reduce unnecessary monthly AWS cost while preserving uptime and improving security posture.`
4. click **Analyze**
5. review the KPI cards:
   - Monthly Cost Before
   - Monthly Cost After
   - Monthly Savings
   - Savings Percent
6. scroll to **Summary** and review identified issues and actions
7. click **Generate Report Artifact**
8. optionally open **Mock Console** or use **Sandbox Apply**

## Testing instructions

### Backend tests

From the repo root:

\`\`\`powershell
.\venv\Scripts\Activate.ps1
python -m pytest backend\tests -q
\`\`\`

### Manual browser smoke test

- backend health endpoint responds
- frontend home page loads
- Sample Demo mode is selected
- Analyze completes successfully
- KPI cards populate
- Summary populates
- Generate Report Artifact works
- optional mock console or sandbox flow works cleanly

## API overview

Core routes include:

- `/`
- `/analyze`
- `/discover`
- `/apply`
- `/report`
- `/voice`
- `/execute-real`

Exact behavior may vary by mode and local environment.

## Safety notes

- Sample Demo is the intended hackathon evaluation path
- Live AWS mode may require local AWS credentials and configuration
- do not use root credentials
- use least-privilege IAM where applicable
- do not commit secrets, keys, or sensitive credentials
- no destructive production actions should be part of the normal demo flow

## Demo highlights

NovaArchitect is designed to show:

- structured reasoning instead of vague chat output
- simulation before execution
- visible cost reduction
- tradeoff-aware decision support
- safe action support with evidence artifacts
- business-readable reporting for both engineers and decision-makers

## Current status

This repository contains the hackathon prototype for NovaArchitect, focused on a clean browser-based demo experience and a strong explanation of how agentic AI can support infrastructure strategy.

## Roadmap

Planned next steps include:

- live telemetry integration
- stronger policy and approval workflows
- rollback-aware remediation
- staged rollout across environments
- stronger observability and artifact management
- hardened deployment path beyond local demo mode

## Submission positioning

NovaArchitect is built as an agentic infrastructure strategist that combines:
- reasoning
- simulation
- safe action
- executive reporting

This project is intended to demonstrate how Amazon Nova can move cloud operations from static recommendation systems toward intelligent, auditable decision workflows.

## Author

Built by Ruthvik Uttarala.

## License

Add your preferred license here.
