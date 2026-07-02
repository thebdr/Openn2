# Findings & treatments

Every check the pipeline runs lands as a **finding**: a phase, a type slug, a severity, a location,
and the detail text. The severities:

- **FAIL** halts the phase (nothing is written past a raw FAIL),
- **ERROR** skips the item and continues,
- **WARN / INFO / SKIP / PASS / DEBUG** inform; the **Levels ▾** dropdown filters what the log shows.

## Re-grading a finding

When a finding is formally right but wrong for THIS project (a naming rule the customer overrides,
say), give it a **treatment**: right-click the finding in the **Findings** tab (or the `[LEVEL]` link
in the log) and pick the effective severity - `fail`, `error`, `warn`, `skip`, or `ignore`. A
treatment can downgrade a FAIL so the phase proceeds, or escalate a WARN into a halting FAIL.

Treatments are keyed by the finding's content hash, so they survive re-runs and document revisions
that don't change the finding itself. They live in
[config_project/user_input/error_management.csv](src://config_project/user_input/error_management.csv) -
a project-owned file; review it like code.

## Where findings go

All treatable findings are also recorded in the `validation_issues` SSOT table - query them in the
[Database Explorer](guide://database-explorer):

```
SELECT phase, severity, COUNT(*) FROM validation_issues GROUP BY phase, severity
```
