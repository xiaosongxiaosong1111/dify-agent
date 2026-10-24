# Project conventions

- Product name: Sierra, chosen by the user on 2026-10-10. Use it consistently in the UI and generated product descriptions.

## Standing user instructions (2026-10-21)

- For major updates, commit the reviewed changes and push to `https://github.com/xiaosongxiaosong1111/dify-agent.git`. This explicit user instruction supersedes earlier blanket no-push instructions. Verify the remote, exclude secrets, and do not force-push.
- Before every GitHub push, update root `CHANGELOG.md` with the shipped changes, targeted verification and remaining limitations. The user explicitly requested this on 2026-10-24; handoff notes alone do not replace the changelog.
- Reuse the dedicated Dify connection's encrypted credentials. The user authorizes obtaining a new token with their supplied login when it expires; do not repeatedly request manual login if secure credentials are available. Never write the password into Git, handoffs, logs, or browser storage. Since 0.245.0 opt-in encrypted email/password storage and automatic reauthentication are implemented. The dedicated after-sales connection has been explicitly authorized and activated; reuse its local encrypted credentials, not chat history. Since 0.248 they also pin the original Dify workspace; renewed tokens must prove the same workspace before commit or original request dispatch. URL/version changes clear the saved identity; forgetting deletes email/password while retaining the workspace identity. Legacy saved credentials without workspace proof must not silently reauthenticate. The dedicated case has been read-only verified and pinned. Failed login/new-token401 pauses automatic login; never loop or replay external writes. Natural-expiry behavior is isolated-tested, not yet observed live.
- Prioritize the complete public after-sales case in `docs/core-delivery-focus.md`. Continue from the existing implementation and regression tests; local isolated acceptance records do not close real platform or business acceptance.

- Delegate simple, repetitive independent work through the existing Claude Code gateway as a subagent. The user explicitly selected that gateway (actual model DeepSeek) and authorized sending necessary private code snippets, excluding credentials, customer data, and the whole repository. Report actual model identity; root agent owns design, integration, and verification. A worker budget failure is not success and must not be automatically retried.

## Delegated routine decisions (2026-10-23)

- The user explicitly said routine work does not need repeated questions and delegated decisions to the agent. Proceed autonomously with normal development, reversible local fixes, isolated verification, commits/pushes, and necessary verification within existing explicit resource and cost bounds. Reuse authorization already given in this session.
- Record a delegated decision as an agent decision under that standing user instruction, never as a fabricated direct human answer. Consumed one-shot batches remain consumed; failure/no-retry rules and explicit resource/cost limits still apply. Ask only when the concrete next action cannot be covered by existing authorization and would exceed those boundaries. This updates the earlier blanket need-user rule for routine work already covered by the user's delegation.

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
