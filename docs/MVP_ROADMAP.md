# NEXUS — MVP → Platform Roadmap

NEXUS is built as a goal-driven intelligence and action engine, not as a single vertical application.

## North-star loop

**Goal → Observe → Understand → Reason → Decide → Act → Verify**

Every future integration should strengthen one or more stages without coupling the intelligence layer to a specific vendor or industry.

## Stage 0 — Demonstrator

- RTL executive interface
- LEAP mission playback
- Decision / action / verification narrative
- Synthetic data only

## Stage 1 — Functional MVP

- Canonical business context
- File ingestion: CSV / JSON / TXT / XLSX / PDF
- Evidence provenance and source hashing
- Goal + constraints model
- Decision object with rationale and confidence
- Human approval gate
- Safe action planner
- Verification + audit trail
- Automated smoke tests

## Stage 2 — Real business connectivity

- Gmail / Microsoft 365 connector
- Cloud storage connector
- One ERP connector
- One CRM connector
- Scheduled ingestion
- Incremental sync + deduplication
- Tenant isolation
- Secrets management

## Stage 3 — Closed-loop operations

- Real write-capable actions with scoped permissions
- Action idempotency
- Retry / timeout / compensation rules
- Approval policies by role and risk
- Outcome measurement
- Mission history and replay

## Stage 4 — Multi-domain intelligence

- Procurement
- Sales
- Operations
- Finance operations
- Contracts
- Compliance
- Security operations
- Executive / Chief-of-Staff mode

The intelligence engine remains the same; domain connectors and policy packs vary.

## Non-negotiable product principles

1. **Goal first.** The user states the business outcome; NEXUS decides which signals matter.
2. **Evidence before confidence.** Every important claim must retain provenance.
3. **Decision before action.** NEXUS must explain what it intends to do.
4. **Approval by risk.** Higher-risk actions must never silently become autonomous.
5. **Verify every action.** Execution without verification is incomplete.
6. **Tenant isolation by design.** Customer data must never cross organizational boundaries.
7. **Connector independence.** New data sources should not require rewriting the intelligence engine.
