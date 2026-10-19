# Project conventions

- Product name: Sierra, chosen by the user on 2026-10-10. Use it consistently in the UI and generated product descriptions.

- Target Dify stable release 1.17.1, verified 2026-10-09. Consult the tagged source, not main, for DSL and console interfaces.
- Product baseline: docs/requirements-v1.0.md. Preserve all explicit user decisions.
- User selects app type. Never silently change it. Unsupported features must return a precise limitation.
- Changes invalidate relevant confirmations and verification. Bind approvals and runs to revisions.
- No real external writes before a concrete resource plan is approved. Never silently overwrite existing Dify apps.
- Persist tasks and versions on the local backend. Do not store API keys in browser storage, logs, exported DSL, or Git.
- Mark mock dependencies and unverified results throughout UI, APIs and downloads. Static YAML validation is not an actual Dify import/run.
- Work in assigned files. Root agent owns shared API contract and integration. Coordinate before changing it.
- Prefer deterministic code for schema, graph and variable checks. Use model calls for semantic tasks.
- All product UI and user-facing errors are in Chinese. Model names and library identifiers remain exact.
- Keep docs/development-status.md accurate. Do not mark the entire 136-task plan complete after delivering an initial runnable slice.
