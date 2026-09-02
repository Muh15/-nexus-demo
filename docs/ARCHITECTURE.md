# NEXUS Architecture

## Layers

```text
                  ┌──────────────────────────────┐
                  │         NEXUS UI/API         │
                  └──────────────┬───────────────┘
                                 │
                  ┌──────────────▼───────────────┐
                  │      Mission / Goal Layer    │
                  └──────────────┬───────────────┘
                                 │
                  ┌──────────────▼───────────────┐
                  │    Intelligence Orchestrator │
                  │ Observe → Understand →       │
                  │ Reason → Decide              │
                  └───────┬───────────┬──────────┘
                          │           │
             ┌────────────▼───┐   ┌──▼──────────────┐
             │ Business Context│   │ Evidence Store │
             │ entities/links  │   │ provenance     │
             └────────────┬────┘   └──────┬─────────┘
                          │               │
                    ┌─────▼───────────────▼─────┐
                    │       Connector Layer     │
                    └─────┬─────┬─────┬─────┬───┘
                          │     │     │     │
                        File  Email  ERP   CRM  Web

                         Decision
                            │
                     ┌──────▼───────┐
                     │ Action Policy│
                     └──────┬───────┘
                            │
                   ┌────────▼────────┐
                   │ Action Executor  │
                   └────────┬────────┘
                            │
                      ┌─────▼─────┐
                      │ Verify    │
                      └─────┬─────┘
                            │
                      Audit / History
```

## Separation of concerns

**Connectors** transport and parse data. They do not decide.

**Business Context** represents entities and relationships such as supplier → contract, customer → deal, or branch → region.

**Evidence** preserves the exact origin of important claims so decisions can be reviewed.

**Intelligence** turns goals, constraints, context, and evidence into a decision. The MVP keeps this deterministic so it is easy to test; an LLM can later be introduced as a reasoning component behind the same contract.

**Action Policy** determines what NEXUS is permitted to do. The default posture is deny-by-default for critical or unknown actions.

**Executor** performs only policy-approved operations.

**Verification** checks the post-action state and writes the result to the audit trail.

## Why this shape matters

The architecture lets NEXUS add a new source or a new business domain without rewriting its core reasoning pipeline. It also makes the safety boundary explicit: a model may recommend an action, but the policy layer controls whether that action can be executed.
