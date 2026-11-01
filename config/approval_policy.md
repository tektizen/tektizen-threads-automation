# Approval Policy

This document describes the publishing safety rules. The rules marked **(enforced)** are implemented in code (`tektizen/publishing/gate.py`) and cannot be bypassed by editing this file — this file documents them for humans and gives agents context.

## Modes

### Mode A — Human approval required (default)

1. Automation researches, generates, evaluates, and refines content.
2. Final content is saved as `PENDING_APPROVAL`.
3. It appears in the dashboard Approval Center.
4. A human approves (→ `READY_TO_PUBLISH`) or rejects (→ `REJECTED`, with reason stored as learning feedback).
5. Only `READY_TO_PUBLISH` content with a recorded human approval can be published.

### Mode B — Full automatic publishing

Content may be published without a human only if **all** of the following hold:

1. Approval mode is explicitly set to `auto_publish` in `data/settings.json`. **(enforced)**
2. The global kill switch is off. **(enforced)**
3. Overall quality score ≥ `quality.min_overall` (default 80). **(enforced)**
4. Factuality score ≥ `quality.min_factuality` (default 90). **(enforced)**
5. Brand compliance score ≥ `quality.min_brand` (default 90). **(enforced)**
6. No critical fact-check failure. **(enforced)**
7. No unresolved `high` or `critical` severity warnings. **(enforced)**
8. Not a duplicate of previously published content (content hash and similarity). **(enforced)**
9. The per-run publishing limit `publishing.max_posts_per_run` has not been reached. **(enforced)**

Content that fails any check falls back to `PENDING_APPROVAL` for a human.

## Always-on Safety Rules (enforced)

- A missing, invalid, or unreadable approval setting is treated as **human approval required**.
- Critical fact-check failures block publication in every mode — even a human approval cannot publish content whose latest fact check is a critical failure; it must be edited and re-checked first.
- Rejected, pending, archived, or failed content is never published.
- Each content item has a stable idempotency key; Zernio's `Idempotency-Key` header and our own publishing state prevent double publishing.
- An uncertain publish (timeout, 5xx, or unparseable response after the request was sent) is recorded as `PUBLISH_UNCERTAIN` and is **never retried automatically**. A human must reconcile it from the dashboard after checking Threads.
- The kill switch blocks all publishing, including human-approved content.

## Switching Modes

Switching to `auto_publish` from the dashboard requires a confirmation dialog and records who enabled it and when.
