# NEXUS Core Boundaries

The core package is the protected center of the MVP. New capabilities should be added through adapters/interfaces rather than by embedding provider-specific logic here.

## Boundaries

- `models.py` — domain primitives and traceable evidence.
- `context_builder.py` — converts connector records into business context.
- `orchestrator.py` — owns mission lifecycle/state transitions only.
- `planner.py` — turns decisions into proposed actions; never executes them.
- `policy.py` — security/policy gate; default deny for unknown or critical actions.
- `repository.py` — persistence boundary; current implementation is in-memory and replaceable.
- `sources.py` — source capability catalog, independent from connector implementations.

## Rule

A new connector, AI provider, database, domain, or executor must plug into a boundary. It must not rewrite the mission lifecycle or duplicate policy logic.
