# NEXUS MVP v0.1 — Goal-Driven Intelligence Engine

This folder is the first real MVP foundation for NEXUS.

## What it proves

NEXUS receives a business goal, reads business signals, reasons across them, produces a decision, creates an authorized action plan, and records verification/audit events.

## First scenario

The included demo scenario is intentionally **not product price comparison**. It is operational cost reduction:

> Reduce operating cost by 10% within 90 days without changing quality and without breaking active contracts.

The sample signal set combines supplier pricing, contract timing, spend concentration, and market context into one recommended decision.

## Connector foundation

The file connector now supports:

- CSV
- JSON
- TXT
- XLSX
- PDF text extraction

Every ingest returns a SHA-256 source hash and record-level provenance such as row, sheet/row, or PDF page. This gives NEXUS a traceable evidence chain instead of anonymous data.

## Core foundation

`core/models.py` introduces canonical business entities, relationships, evidence, and a graph-like business context. `core/policy.py` provides a deny-by-default action safety boundary. `core/planner.py` separates a recommended decision from an executable action plan.

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
Goal / Mission
      ↓
Connector Layer
      ↓
Business Context + Evidence
      ↓
Observe → Understand → Reason → Decide
      ↓
Action Policy → Approve → Act
      ↓
Verify → Audit / History
```

Connectors handle transport and parsing; intelligence handles reasoning; policy controls execution. This separation is the foundation for adding email, ERP, CRM, cloud storage, web sources, and other enterprise systems without rewriting the intelligence core.

## Important

This remains an MVP foundation, not a production system. The included scenario/data is synthetic and safe for demos. Production authentication, tenant isolation, secrets management, persistence, real write-capable connectors, observability, and stronger approval controls remain planned milestones.
