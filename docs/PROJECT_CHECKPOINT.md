# NEXUS — Project Checkpoint

## Purpose
NEXUS is an AI intelligence & action engine for companies.
Core promise: **Give NEXUS a business goal; it discovers what it needs, reasons over evidence, decides, acts when authorized, and verifies the outcome.**

## Product identity
- Positioning: AI that monitors the digital environment of a company and acts on its behalf.
- Core loop: Observe → Understand → Reason → Decide → Act → Verify.
- Extended lifecycle in the MVP: Mission → Discovery → Research → Decision → Plan → Authorization → Approval → Execution → Verification.
- Goal-first architecture: the company gives an objective; NEXUS determines relevant evidence domains and actions.
- LEAP is a reasoning/cross-connection method and presentation layer, not the whole product.
- UI/demo must retain the existing LEAP path and UX; do not regress it.

## Repository
- GitHub: Muh15/-nexus-demo
- Default branch: main
- GitHub Pages: https://muh15.github.io/-nexus-demo/
- A preservation branch exists: `checkpoint/enterprise-guardrails`.
- Latest verified CI/Page state before this checkpoint: CI and Pages green; later checkpoint documentation does not alter runtime behavior.

## Architecture
Principle: **Adding a capability must not require modifying old capabilities. NEXUS grows by composition, not rebuild.**

Layers include:
- connectors and provider registry
- canonical business context / ingestion
- goal planner
- adaptive research planner/executor
- intelligence graph and impact assessment
- deterministic reasoner (current MVP; not an LLM yet)
- action planner / policy / action executor
- verification
- mission orchestration
- SQLite mission persistence
- API authentication / tenant isolation
- scheduled ingestion foundation

## Current implemented capabilities
### Goal intelligence
- Parses goal, objective, horizon, target value/unit and constraints.
- Profiles: cost, revenue, risk, customer, supplier, general.
- Selects evidence domains and research needs from the goal.

### Research / intelligence
- Research planning and execution abstractions.
- Connectors for file, HTTP JSON, business APIs, and provider registry.
- Provenance/hash handling for fetched business evidence.
- Intelligence graph and impact assessment structures.

### Decisioning
- Deterministic heuristic reasoner with profile-specific recommendations, confidence and evidence scoring.
- Decision precedes action.

### Actions
- Safe draft-email action.
- Real business-action connector supports POST/PATCH, bearer-token configuration through environment variables, allow-listed hosts, response-size limits, bounded retries and idempotency keys.
- Configurable real action handlers include `update_crm`, `change_purchase_order`, and `send_email`.
- Default policy is deny-by-default for unknown/high-risk/monetary actions.
- Critical actions such as transfers, refunds, deletion and permission changes are blocked by policy.
- Approval is required for supported actions.
- Action execution receives a stable execution ID.

### Enterprise guardrails
- Action approval is bound to an exact action fingerprint derived from action type, target and body.
- Changing the payload after approval invalidates the approval.
- Runtime authorization boundary distinguishes viewer/operator/approver/admin.
- Tenant isolation is enforced at repository/API boundaries.
- Actor identity is retained in mission audit.
- Strict auth mode supports server-defined API-key principals; client headers cannot spoof tenant/role in strict mode.
- Tokens are read from environment references rather than stored directly in code/config payloads.

### Persistence / audit
- Mission snapshots are persisted in SQLite.
- Mission repository supports tenant-scoped get/list/delete.
- Snapshot restoration recreates executable lifecycle state.
- Audit trail records actor/action lifecycle events.

### API
- API version currently 1.0.0.
- Mission creation accepts goal, constraints, action_type, target and body.
- Lifecycle endpoints support create/research/decide/plan/approve/execute/verify.
- Auth mode endpoint exists.

## Verification status
Latest confirmed GitHub CI run at checkpoint:
- CI: **success**
- Pages deployment: **success**
- Tests: **93 passed**
- Compileall: **success**

Warnings seen in CI are GitHub Actions Node 20 deprecation warnings, not NEXUS test failures.

## What is NOT finished yet
These are intentionally the next engineering gates; do not describe NEXUS as production-ready yet:
1. Strong read-after-write external verification (do not treat HTTP 200 alone as proof of business-state change).
2. Fully wired scheduled/incremental ingestion execution and cursor progression.
3. Production-grade real connectors for selected ERP/CRM/email/storage providers.
4. Production-grade real actions with stronger retry/backoff/jitter, compensation and operational safeguards.
5. Enterprise authentication beyond API-key prototype: OAuth/OIDC/JWT/SSO abstraction and integration.
6. Secret-manager abstraction and hardened credential handling.
7. Rate limiting, readiness/health endpoints and stronger configuration validation.
8. Mission history/replay and outcome measurement against the original goal.
9. Broader multi-domain roles: procurement, sales, operations, finance, contracts, compliance, security and executive workflows.
10. Production deployment, threat modeling, penetration/security testing and operational runbooks.

## Next exact starting point
**Resume at: Real post-action verification.**
Implement a verifier that can query an external read endpoint after an action and compare the observed state with the expected result, while binding the check to the execution ID/idempotency context and preserving audit evidence.

After that, continue in this order:
- scheduled incremental ingestion
- real connector hardening
- real action hardening
- enterprise auth/secrets/rate limits/health
- mission history/replay
- outcome measurement
- production security/deployment

## Product/demo rules
- Keep the dark futuristic RTL Arabic UI and existing LEAP path intact.
- Do not replace the product identity with a simple price-comparison or competitor-monitoring tool.
- Demo/synthetic data must be clearly labeled as experimental/presentation data.
- Do not put secrets in repository files.
- Every external action must be policy-controlled, authorized, approved when required, idempotent where applicable, and verified.
- Never claim a feature is production-ready merely because unit tests pass.

## Resume instruction
When the user returns and says **"كمل"**, resume from **Real post-action verification** using this checkpoint and the current `main` branch. Inspect the current code before changing it, implement the next gate directly, add tests, run CI, and report only verified results.
