# Role-based access control

Six tiers; each implies every lower tier's privileges:

```
viewer ⊂ observer ⊂ operator ⊂ approver ⊂ commander ⊂ admin
```

| Tier | Allowed actions (in addition to lower tiers) |
|---|---|
| **viewer** | `GET /v1/*` — read boards, targets, audit log |
| **observer** | `POST /v1/targets` — create new target observations |
| **operator** | `PATCH /v1/targets/{id}`, `POST /v1/targets/{id}/move` (non-approval columns) |
| **approver** | `POST /v1/targets/{id}/move` into a column with `requires_approval=true` |
| **commander** | `POST /v1/boards` — create/destroy boards |
| **admin** | full access; bootstrap-seeded user, can manage users (when that endpoint lands) |

Unknown role strings fall back to `viewer` (least privilege). Default
for a freshly-created user with no explicit role: `viewer`.

## Why these tiers

Mapped from Ukrainian field practice per
[`docs/research/ukraine-fires-targeting.md`](../research/ukraine-fires-targeting.md) §1:
Delta enforces tiered access (battalion → brigade → division). A
front-line observer submits raw cues. An operator works the kanban. An
approver satisfies RoE-gated transitions (typically kinetic effects).
A commander owns the workspace's shape (board layout, columns,
approval policy). Admin is the operations-staff role; reserved for
the bootstrap user today.

## Where it's enforced

- **`src/target_workspace/api/rbac.py`** — `require_role(user_role, required, action=...)`
  raises 403 with a specific reason in the detail
- **`api/routers/targets.py`** — guards `create_target` (observer+),
  `update_target` (operator+), `move_target` (operator+, approval-gated
  columns additionally require approver+)
- **`api/routers/boards.py`** — guards `create_board` (commander+)

GETs are intentionally not role-gated beyond cookie-session auth.
Boards / targets / audit are workspace-scoped and any authenticated
session is at least a viewer.

## What's NOT here yet

- An admin UI for promoting users between tiers — today roles are set
  via direct DB / migration. See GitHub Issues for follow-ups.
- Row-level access (per-target visibility / classification) — out of
  scope for v0; the workspace boundary is the only data isolation.
- Federated / multi-workspace role mapping — that's tw-0xg (tw_mesh).

## Test coverage

- `tests/integration/test_rbac.py` covers all 5 transition matrices
  (viewer-can't-create, observer-can-create-not-edit,
  operator-can-move-not-approve, approver-satisfies-gate,
  operator-can't-create-board).
