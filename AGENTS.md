# Project conventions

- Product name: Sierra, chosen by the user on 2026-10-10. Use it consistently in the UI and generated product descriptions.

## Standing user instructions (2026-10-21)

- For major updates, commit the reviewed changes and push to `https://github.com/xiaosongxiaosong1111/dify-agent.git`. This explicit user instruction supersedes earlier blanket no-push instructions. Verify the remote, exclude secrets, and do not force-push.
- Reuse the dedicated Dify connection's encrypted credentials. The user authorizes obtaining a new token with their supplied login when it expires; do not repeatedly request manual login if secure credentials are available. Never write the password into Git, handoffs, logs, or browser storage. The current implementation stores tokens, not the login password; persistent encrypted login storage and automatic reauthentication remain to be implemented. Do not claim that they already work or treat chat history as a permanent credential store.
- Prioritize the complete public after-sales case in `docs/core-delivery-focus.md`. Continue from the existing implementation and regression tests; local isolated acceptance records do not close real platform or business acceptance.

- Delegate simple, repetitive independent work through the existing Claude Code gateway as a subagent. The user explicitly selected that gateway (actual model DeepSeek) and authorized sending necessary private code snippets, excluding credentials, customer data, and the whole repository. Report actual model identity; root agent owns design, integration, and verification. A worker budget failure is not success and must not be automatically retried.

## Where work comes from

- The single source of pending work is `docs/BACKLOG.md`. Its queue table is authoritative; do not substitute the ordering or numbering of `docs/development-tasks.md` for it.
- If `docs/BACKLOG.md` exists and has a `pending` row, the default action is to do that row. Do not stop to ask which item to take next.
- One row at a time, top-down by number. Only act on the first `pending` row; skip `done`, `blocked`, `need-user`.
- A row may only be marked `done` after its acceptance command has actually passed and a commit exists. Never mark `done` from intention or partial work.
- After finishing a row, update its status and evidence in `docs/BACKLOG.md`, commit that change, then continue to the next `pending` row.
- Stop the whole queue only when: quota is exhausted, two consecutive items fail, or every remaining row is `blocked`/`need-user`. Report which case applies.
- Items that need a human (login, real Dify authorisation, paid model calls) are marked `need-user`; do not attempt them and do not silently downgrade them.
- Local isolated green tests do not equal real Dify platform acceptance. Record that boundary in the evidence cell rather than implying the business scenario passed.

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
