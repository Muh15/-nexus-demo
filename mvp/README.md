# NEXUS MVP v0.1 — Goal-Driven Intelligence Engine

This folder is the first real MVP foundation for NEXUS.

## What it proves

NEXUS receives a business goal, reads normalized business signals, reasons across those signals, produces a decision, creates an authorized action draft, and records verification/audit events.

## First scenario

The included demo scenario is intentionally **not product price comparison**. It is operational cost reduction:

> Reduce operating cost by 10% within 90 days without changing quality and without breaking active contracts.

The sample signal set contains supplier pricing, contract timing, spend concentration, and market context. The engine combines them into one recommended decision.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open `http://127.0.0.1:8000/docs`.

## MVP API

- `GET /health` — service health
- `GET /api/context` — current business context
- `POST /api/missions` — create a mission and run the reasoning pipeline
- `GET /api/missions/{mission_id}` — inspect mission, decision, action, verification, and audit
- `POST /api/missions/{mission_id}/approve` — approve the proposed action
- `POST /api/missions/{mission_id}/execute` — execute the safe demo action
- `POST /api/missions/{mission_id}/verify` — verify the execution and close the mission

## Architecture

```text
Mission
  -> Observe
  -> Understand
  -> Reason
  -> Decide
  -> Approve
  -> Act
  -> Verify
  -> Audit
```

Connectors are deliberately normalized behind a common signal model so later we can swap the demo data for email, ERP, CRM, files, APIs, or approved web sources without rewriting the intelligence engine.

## Important

This is an MVP foundation, not a production system. The included data is synthetic and safe for demos. Real connectors, authentication, authorization, tenant isolation, production persistence, and production-grade action controls are next milestones.
