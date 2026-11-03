# Offline Sync Contract (v1 draft)

Contract between the **ByabshaGhor offline POS app** (Flutter, `byabshaghor_pos`)
and **shop-app-backend**. Goal: a POS counter must be able to sell with zero
connectivity and reconcile with the cloud later.

Scope intentionally covers only **master data pull** + **counter operations
push**. Reports, purchases, settings, etc. stay online-only in v1.

---

## 1. Principles

- **Server-authoritative.** Cloud DB is the source of truth. The device holds a
  read replica of master data + an append-only outbox of its own operations.
- **Idempotent push.** Every operation carries a client-generated `op_id`
  (UUID). Retries are always safe — the server dedupes by `op_id`.
- **Delta pull.** After the first full snapshot, devices pull only rows changed
  since their last cursor (`updated_at` based).
- **Independent operations.** A push batch is NOT atomic. Each op gets its own
  result; one bad op never blocks the rest of the queue.
- **Tombstones.** Deleted rows sync via `deleted_at`, not by disappearing.

## 2. Conventions

- Base path: `/api/v1/sync` (new additive module `src/modules/sync/`).
- Same middleware chain as other routes: `authenticate` → `tenantResolver` →
  `branchResolver`. Sync is always scoped to one tenant + one branch.
- All timestamps ISO-8601 UTC. All ids UUIDs.
- Device sends `X-Device-Id` + `X-Device-Token` headers on every sync call.

## 3. Device registration

```
POST /api/v1/sync/devices/register
Authorization: Bearer <user jwt>          # owner/manager registers a counter
{
  "name": "Counter-1",                    # human label
  "branchId": "<uuid>",
  "platform": "windows"                   # windows|android
}
→ 201
{
  "deviceId": "<uuid>",
  "deviceToken": "<random secret>",       # stored in flutter_secure_storage
  "invoicePrefix": "C1"                   # per-device invoice prefix
}
```

- One row per physical counter in `sync_devices`.
- `deviceToken` is long-lived and revocable; shown once at registration.
  Re-registering an existing `name`+`branchId` rotates the token and returns a
  fresh one (covers a lost token) — never creates a duplicate row.
- Staff login on the device uses the counter PIN (`pin_hash` already on
  `public.global_users` — see public migration 042); no user JWT is needed
  for `/sync/*` device calls. When the server is unreachable the app verifies
  the PIN locally against the pulled `pin_hash` (bcrypt) and restores the
  last session profile.

### Device + conflict management (owner JWT)

```
GET   /api/v1/sync/devices                      # registered counters (with branch name)
PATCH /api/v1/sync/devices/:id/revoke           # { "revoked": true|false }
                                                # suspended devices get 401 on /sync/*
GET   /api/v1/sync/conflicts?resolved=false     # paginated review queue
POST  /api/v1/sync/conflicts/:id/resolve        # marks the conflict resolved
```

## 4. Pull — master data

```
GET /api/v1/sync/pull?since=<iso8601>&entities=products,units&cursor=<opaque>
X-Device-Id, X-Device-Token
→ 200
{
  "serverTime": "2026-09-27T10:00:00.000Z",
  "nextCursor": "eyJ...",
  "hasMore": true,
  "changes": {
    "products":  { "upsert": [...], "delete": ["<uuid>", ...] },
    "units":     { "upsert": [...], "delete": [] }
  }
}
```

- `since` omitted → full snapshot (first sync).
- `cursor` paginates large entities (IMEI stock can be thousands of rows).
  Client keeps pulling until `hasMore=false`, then stores `serverTime` as its
  new `since` watermark. **Never** use client clock as the watermark.
- `delete` contains ids of rows soft-deleted since `since`.

### Syncable entities (v1)

| entity | source | notes |
|---|---|---|
| `products` | products + variants + barcodes | incl. price, tax fields |
| `units` | serialized units / IMEI stock | the big one — paginate |
| `customers` | customers | incl. due/advance balance snapshot |
| `categories`,`brands`,`subcategories` | lookups | small |
| `payment_methods` | payment methods + accounts | |
| `users` | counter staff | `id, name, role, pinHash` only — never password hash |
| `settings` | branch-scoped invoice/print/tax settings | single object |
| `sales` | completed sales (for returns) | see §8 — window via tenant settings |
| `sale_items` | line items of those sales | streams by parent sale's `updated_at` (no own watermark columns) |

## 5. Push — operations outbox

```
POST /api/v1/sync/push
X-Device-Id, X-Device-Token
{
  "operations": [
    {
      "opId": "<uuid>",            // client-generated, idempotency key
      "type": "sale.create",
      "clientTs": "2026-09-27T09:41:12.000Z",
      "payload": { /* same shape as the matching REST schema */ }
    }
  ]
}
→ 200
{
  "results": [
    {
      "opId": "<uuid>",
      "status": "applied",          // applied | duplicate | conflict | rejected
      "serverId": "<uuid>",         // created row id (e.g. sale id)
      "invoiceNo": "INV-000412",    // official number where applicable
      "message": null               // human-readable reason on conflict/rejected
    }
  ]
}
```

### Operation types (v1)

| type | maps to | payload |
|---|---|---|
| `sale.create` | `sale.service` create path | `createSaleSchema` + `clientRef = opId` |
| `sale.pay` | `POST /sales/:id/pay` | `paySaleSchema` + target `saleId` or `clientRef` |
| `sale.void` | `POST /sales/:id/void` | `voidSaleSchema` + target |
| `sale_return.create` | sale-return create | return schema + original sale ref |
| `customer.create` / `customer.update` | customer module | customer schema |
| `cashbox.deposit` / `cashbox.withdraw` | `addTransaction` | amount + note + paymentAccountId |

Every counter op also carries `soldBy` (staff user uuid) — audit columns
can't come from a JWT on device-authenticated calls.

Payloads reuse the existing zod schemas verbatim — the sync module validates
then calls the same service functions as the REST routes. No duplicated
business logic.

v1 restrictions on push ops:

- `sale.create` with `emi` set → `rejected` ("EMI requires connectivity").
  Exchange/trade-in inside a sale IS allowed.
- `sale.void` is allowed only if the device has offline-void permission —
  owner/manager PIN required on-device.

### Result semantics

- `applied` — committed.
- `duplicate` — `opId` already applied; `serverId`/`invoiceNo` return the
  original result. Client marks synced, does not retry.
- `conflict` — committed but needs human review (see §6). The op is NOT lost.
- `rejected` — hard failure (invalid payload, voided target, etc.). Client
  surfaces it to staff; does not auto-retry.

Ops are applied **in array order** per device, so `sale.pay` after
`sale.create` in one batch sees its own sale.

## 6. Conflicts

| case | rule |
|---|---|
| Same `unitId` (IMEI) sold on 2 devices while offline | Second op applies → `conflict`, row created with `flagged=true`, lands in a review queue for owner. Never silently drop a real-world sale. |
| `sale.pay`/`sale.void` targeting a sale that doesn't exist on server (e.g. original was itself voided) | `rejected` with message. |
| Stock goes negative after replay | Allowed. Sale applies; stock row flagged. Counters must never block a sale. |
| `customer.create` with same phone as existing | Server merges → returns existing `serverId`, status `applied`. |

`sync_conflicts` table stores every conflict for owner review in the web UI.

## 7. Invoice numbering

- Offline invoice shows a provisional number: `<prefix>-<local seq>`
  (e.g. `C1-000137`). Prefix comes from device registration — no cross-device
  collisions by construction.
- On push, server assigns the official `invoiceNo` via the existing
  number-series and returns it in the result. App stores the mapping and
  reprints/shows official number once synced.
- `clientRef` (already in `createSaleSchema`) carries `opId` so a sale can be
  traced back to its device operation.

## 8. Returns offline

A return needs the original sale. Options per sync policy:

- v1: pull `sales` for the last N days (configurable via tenant settings,
  default 30) so most returns work offline. Return op carries
  `saleId`/`invoiceNo` — if the original isn't on server yet it must be (it
  was synced or made online).
- Edge: original sale was made offline on the SAME device → return references
  `clientRef`; server resolves after the create op applies (ordering
  guarantees this within a device queue).

## 9. Client-side requirements (Flutter)

- `outbox` table: `op_id, type, payload_json, status, attempts, created_at`.
  FIFO drain on connectivity (`connectivity_plus` already present).
- Watermark per entity stored in `sync_meta` (replaces single `lastPulledAt`).
- Current full-replace pull (`replaceAllProducts`) must become upsert/delete
  merge per entity.
- Exponential backoff on 5xx; never retry on 4xx/`rejected`.
- Pull on app start + after every successful push + periodic (e.g. 5 min).

## 10. Backend implementation notes

- New module `src/modules/sync/` — `sync.routes.ts`, `sync.controller.ts`,
  `sync.service.ts`, `sync.schema.ts`, `sync.middleware.ts`. Mounted at
  `/api/v1/sync` **before** the `/api/v1` catch-all (templateRoutes) — its
  router-level `authenticate` would 401 device calls that carry no JWT.
- Device auth: counters hold `X-Device-Id` + `X-Device-Token` (bcrypt hash on
  file), no user JWT. `requireDevice` resolves tenant schema + branch from the
  device row itself.
- `public.sync_devices(tenant_id, branch_id, name, platform, token_hash,
  invoice_prefix, last_seen_at, revoked_at)` — public schema so device auth is
  self-resolving. Management routes (register/conflicts) still use JWT +
  tenantResolver.
- Tenant-schema tables:
  - `sync_operations(op_id PK, device_id, type, payload jsonb, status, server_id, invoice_no, applied_at)`
  - `sync_conflicts(id, op_id, device_id, type, detail jsonb, resolved_at, resolved_by, created_at)`
- Pull queries filter `updated_at > since OR deleted_at > since`; require
  `updated_at` index on every syncable table — audit schema before build.
- Push handler: per-op `for` loop, each op in its own transaction, calls the
  existing service; wrap outcome into result row. Never let one op abort the
  batch.
- Keep `sync_operations` for 90+ days for dedupe + audit.

## 11. Decisions

- **New customers offline: allowed.** Server merges by phone number; returns
  existing `serverId` with `applied` if a match exists.
- **Offline login: dedicated counter PIN.** `users` pull carries a `pinHash`
  (bcrypt of a 4–6 digit POS PIN set from web Settings) — never the account
  password hash. Device enforces local rate limiting (5 tries → 5 min lock).
- **One device = one branch** for v1. Registration binds device to branch;
  multi-branch counters deferred.
- **EMI sales are online-only.** `sale.create` carrying `emi` is `rejected`
  on push; the app blocks EMI checkout while offline.
- **Exchange/trade-in offline: allowed.** It's just inventory intake +
  sale-line value; replay-safe.
- **Stale price is final.** The `unitPrice` captured at sale time applies —
  server never overrides with current price.
- **Offline duration soft cap: 7 days.** App shows a staleness warning but
  keeps selling; no hard block.
- **Return window pull: last 30 days of `sales`**, tenant-configurable.
