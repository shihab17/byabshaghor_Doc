# Job Orders — Core Model Spec (Phase 0 + Phase 1)

Status: DRAFT for implementation
Scope: rename `service_jobs` → `job_orders`, add work-breakdown (tasks), multi-employee
assignments, cost ledger, payout ledger, business-profile attributes, DB-driven
workflow tables. Phase 1 wires tasks + assignments end-to-end. Costs/payouts/workflow
tables are created in Phase 0 but only get their APIs in Phase 2/3/4.

Decisions already taken (do not re-open):
1. Full rename — DB tables, module folder, API path, web route, doc-type keys. Old
   `/service-jobs` web route stays as a redirect only.
2. Payouts support both payroll push and instant expense pay; default = payroll.
3. Ad-hoc (non-catalogue) lines are allowed; on delivery they bill against a hidden
   system product `SYS-SERVICE-CHARGE` (item_type = 'service').
4. Workflow tables are created now; the hardcoded transition map stays the runtime
   source of truth until Phase 4 flips to DB-driven.

---

## 0. Naming map (rename)

| Old | New |
|---|---|
| table `service_jobs` | `job_orders` |
| table `service_job_items` | `job_order_items` |
| table `service_job_status_history` | `job_order_status_history` |
| table `service_job_outsources` | `job_order_outsources` |
| table `service_job_devices` | dropped → rows copied into `job_order_attributes` (profile_key = 'device') |
| column `sales.service_job_id` | `sales.job_order_id` |
| column `job_orders.service_product_id` | keep name (still "catalogue service product") |
| `payments.reference_type = 'service_job'` | `'job_order'` (data UPDATE) |
| `cashbox_transactions.reference_type = 'service_job'` | `'job_order'` (data UPDATE) |
| number-series `doc_type = 'service_job'` | `'job_order'` (data UPDATE + code `DocType`), prefix default stays `SRV`? → **change default prefix to `JOB`** for new tenants; existing rows keep whatever prefix they have |
| template doc type `service_job_pdf` | `job_order_pdf` (data UPDATE on templates table + code) |
| index names `idx_<schema>_service_job*` | `idx_<schema>_job_order*` |
| backend module `src/modules/service-job/` | `src/modules/job-order/` (`job-order.service.ts`, `job-order-shared.ts`, `job-order.schema.ts`, `job-order.controller.ts`, `job-order.routes.ts`) |
| API mount `/service-jobs` (app.ts) | `/job-orders` |
| web `src/lib/service-jobs.ts` | `src/lib/job-orders.ts` |
| web route `/service-jobs/*` | `/job-orders/*`; `/service-jobs/*` and `/service-cases/*` → redirect pages |
| menu seed hrefs / keys `service_jobs.create`, `pos.service_job`, `/reports?tab=service-jobs` | `job_orders.create`, `pos.job_order`, `/reports?tab=job-orders` |
| unit-inspection schema `context: 'service_job'` | `'job_order'` |
| `customer.controller` job history endpoint | rename internal identifiers only, path unchanged |
| `sale-tx.ts` `serviceJobId` param, `sale.service.ts` reopen hook | `jobOrderId` |

Rename is done in ONE migration (`101_job_orders_core.ts`) using `ALTER TABLE ... RENAME`
so no data copy is needed except the devices → attributes move.

---

## 1. Migration `tenant/101_job_orders_core.ts`

Single transaction. Order matters.

### 1.1 Renames

```sql
ALTER TABLE "${schema}".service_jobs                RENAME TO job_orders;
ALTER TABLE "${schema}".service_job_items           RENAME TO job_order_items;
ALTER TABLE "${schema}".service_job_status_history  RENAME TO job_order_status_history;
ALTER TABLE "${schema}".service_job_outsources      RENAME TO job_order_outsources;
ALTER TABLE "${schema}".sales RENAME COLUMN service_job_id TO job_order_id;

-- indexes (Postgres keeps old names after table rename; rename explicitly)
ALTER INDEX IF EXISTS "${schema}".idx_${schema}_service_jobs_status      RENAME TO idx_${schema}_job_orders_status;
ALTER INDEX IF EXISTS "${schema}".idx_${schema}_service_jobs_customer    RENAME TO idx_${schema}_job_orders_customer;
ALTER INDEX IF EXISTS "${schema}".idx_${schema}_service_jobs_employee    RENAME TO idx_${schema}_job_orders_employee;
ALTER INDEX IF EXISTS "${schema}".idx_${schema}_service_jobs_promised    RENAME TO idx_${schema}_job_orders_promised;
ALTER INDEX IF EXISTS "${schema}".idx_${schema}_service_jobs_client_ref  RENAME TO idx_${schema}_job_orders_client_ref;
ALTER INDEX IF EXISTS "${schema}".idx_${schema}_service_job_items_job    RENAME TO idx_${schema}_job_order_items_job;
ALTER INDEX IF EXISTS "${schema}".idx_${schema}_service_job_history_job  RENAME TO idx_${schema}_job_order_history_job;

UPDATE "${schema}".payments             SET reference_type = 'job_order' WHERE reference_type = 'service_job';
UPDATE "${schema}".cashbox_transactions SET reference_type = 'job_order' WHERE reference_type = 'service_job';
UPDATE "${schema}".number_series        SET doc_type = 'job_order'       WHERE doc_type = 'service_job';
UPDATE "${schema}".templates            SET doc_type = 'job_order_pdf'   WHERE doc_type = 'service_job_pdf';
```

> Verify actual column names for `cashbox_transactions` / `number_series` / `templates`
> before writing the UPDATEs (check `032_finance_module.ts`, `072_number_series.ts`,
> `073_templates.ts`). If a table has a CHECK constraint on doc_type, drop/re-add it.

### 1.2 `job_orders` — new columns

```sql
ALTER TABLE "${schema}".job_orders
  ADD COLUMN IF NOT EXISTS workflow_id  UUID,                         -- FK added after job_workflows exists
  ADD COLUMN IF NOT EXISTS template_id  UUID,                         -- Phase 4, nullable now
  ADD COLUMN IF NOT EXISTS profile_key  VARCHAR(30) NOT NULL DEFAULT 'generic',  -- 'generic'|'device'|'garment'|'print'|'vehicle'|...
  ADD COLUMN IF NOT EXISTS items_total  DECIMAL(12,2) NOT NULL DEFAULT 0,        -- denormalised Σ job_order_items.total
  ADD COLUMN IF NOT EXISTS cost_total   DECIMAL(12,2) NOT NULL DEFAULT 0,        -- denormalised Σ job_order_costs.amount
  ADD COLUMN IF NOT EXISTS payout_total DECIMAL(12,2) NOT NULL DEFAULT 0;        -- denormalised Σ payouts.final_amount (status<>cancelled)

-- existing rows that have a device row → profile_key = 'device'
UPDATE "${schema}".job_orders j SET profile_key = 'device'
  WHERE EXISTS (SELECT 1 FROM "${schema}".service_job_devices d WHERE d.job_id = j.id);

UPDATE "${schema}".job_orders j SET items_total =
  COALESCE((SELECT SUM(total) FROM "${schema}".job_order_items i WHERE i.job_id = j.id), 0);
```

`assigned_employee_id` stays: it is the **lead** assignee and is kept in sync by the
service layer (see §3.4). Existing list/report queries keep working.

### 1.3 `job_order_items` — extend

```sql
ALTER TABLE "${schema}".job_order_items
  ALTER COLUMN product_id DROP NOT NULL,     -- was nullable already via ON DELETE SET NULL; make sure
  ADD COLUMN IF NOT EXISTS task_id     UUID,            -- FK added after tasks table
  ADD COLUMN IF NOT EXISTS cost_amount DECIMAL(12,2) NOT NULL DEFAULT 0,   -- per-line cost snapshot (qty * unit cost)
  ADD COLUMN IF NOT EXISTS seq         INT NOT NULL DEFAULT 0;

-- widen line_type: 'service' | 'part' | 'labour' | 'fee' | 'material' | 'other'
ALTER TABLE "${schema}".job_order_items DROP CONSTRAINT IF EXISTS job_order_items_line_type_check;
ALTER TABLE "${schema}".job_order_items
  ADD CONSTRAINT job_order_items_line_type_check
  CHECK (line_type IN ('service','part','labour','fee','material','other'));
```

Rules:
- `part` and `material` lines **must** have `product_id` (they hit inventory).
- `service`/`labour`/`fee`/`other` may have `product_id = NULL` (ad-hoc). Delivery maps
  them to the system product (see §1.9).
- Only `part` lines are reserved / deducted from stock (unchanged). `material` is a
  non-stock consumable charged to the customer, tracked in costs only.

### 1.4 `job_order_tasks` (NEW)

```sql
CREATE TABLE IF NOT EXISTS "${schema}".job_order_tasks (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id            UUID NOT NULL REFERENCES "${schema}".job_orders(id) ON DELETE CASCADE,
  parent_task_id    UUID REFERENCES "${schema}".job_order_tasks(id) ON DELETE CASCADE,
  seq               INT NOT NULL DEFAULT 0,
  title             VARCHAR(255) NOT NULL,
  description       TEXT,
  status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending','in_progress','blocked','done','skipped')),
  item_id           UUID REFERENCES "${schema}".job_order_items(id) ON DELETE SET NULL,  -- billable line this task delivers
  quantity          DECIMAL(12,3) NOT NULL DEFAULT 1,      -- for per_unit payouts (e.g. 3 shirts)
  estimated_minutes INT,
  actual_minutes    INT,
  started_at        TIMESTAMPTZ,
  completed_at      TIMESTAMPTZ,
  completed_by      UUID,
  -- Payout rule for whoever is assigned. NULL → fall back to employee default (Phase 3).
  -- {"basis":"fixed","rate":200} | {"basis":"percent_of_line","rate":30}
  -- | {"basis":"percent_of_job_total","rate":5} | {"basis":"per_unit","rate":50}
  -- | {"basis":"hourly","rate":150}
  payout_rule       JSONB,
  note              VARCHAR(500),
  created_by        UUID,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  updated_at        TIMESTAMPTZ DEFAULT NOW(),
  deleted_at        TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_tasks_job
  ON "${schema}".job_order_tasks(job_id) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_tasks_status
  ON "${schema}".job_order_tasks(status) WHERE deleted_at IS NULL;

ALTER TABLE "${schema}".job_order_items
  ADD CONSTRAINT job_order_items_task_fk FOREIGN KEY (task_id)
  REFERENCES "${schema}".job_order_tasks(id) ON DELETE SET NULL;
```

Task status rules (service layer):
- `pending → in_progress | blocked | done | skipped`
- `in_progress → blocked | done | pending`
- `blocked → in_progress | pending | skipped`
- `done → in_progress` (reopen; only while job not delivered)
- `skipped → pending`
- Setting `in_progress` sets `started_at` if null; `done` sets `completed_at`,
  `completed_by`, and `actual_minutes` if null and `started_at` set
  (`(NOW()-started_at)` in minutes).
- A task cannot be edited/added when the job is `delivered` or `cancelled`.
- Sub-task depth max = 1 (parent may not itself have a parent).

### 1.5 `job_order_assignments` (NEW)

```sql
CREATE TABLE IF NOT EXISTS "${schema}".job_order_assignments (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id         UUID NOT NULL REFERENCES "${schema}".job_orders(id) ON DELETE CASCADE,
  task_id        UUID REFERENCES "${schema}".job_order_tasks(id) ON DELETE CASCADE,  -- NULL = job-level
  employee_id    UUID NOT NULL REFERENCES "${schema}".employees(id),
  role           VARCHAR(30) NOT NULL DEFAULT 'worker'
                 CHECK (role IN ('lead','worker','helper','qc','sales')),
  share_percent  DECIMAL(5,2) NOT NULL DEFAULT 100 CHECK (share_percent > 0 AND share_percent <= 100),
  assigned_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  unassigned_at  TIMESTAMPTZ,
  assigned_by    UUID,
  unassigned_by  UUID,
  note           VARCHAR(500),
  created_at     TIMESTAMPTZ DEFAULT NOW()
);
-- one active assignment per (task, employee); task_id NULL handled with COALESCE sentinel
CREATE UNIQUE INDEX IF NOT EXISTS idx_${schema}_job_order_assign_active
  ON "${schema}".job_order_assignments(job_id, COALESCE(task_id, '00000000-0000-0000-0000-000000000000'::uuid), employee_id)
  WHERE unassigned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_assign_employee
  ON "${schema}".job_order_assignments(employee_id) WHERE unassigned_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_assign_job
  ON "${schema}".job_order_assignments(job_id);

-- backfill: existing assigned_employee_id → job-level 'lead' assignment
INSERT INTO "${schema}".job_order_assignments (job_id, task_id, employee_id, role, assigned_at, assigned_by)
SELECT id, NULL, assigned_employee_id, 'lead', COALESCE(received_at, created_at), created_by
FROM "${schema}".job_orders WHERE assigned_employee_id IS NOT NULL;
```

Rules:
- Unassign = set `unassigned_at` (never delete) — history is the audit trail.
- At most **one active job-level `lead`** per job. Creating a new lead auto-unassigns the
  previous one and updates `job_orders.assigned_employee_id`.
- Σ `share_percent` of active assignments on the same task must be ≤ 100 (validation
  error otherwise). Used by Phase 3 to split payouts.
- Employee must be `status = 'Active'` and not deleted.

### 1.6 `job_order_costs` (NEW — API in Phase 2)

```sql
CREATE TABLE IF NOT EXISTS "${schema}".job_order_costs (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id       UUID NOT NULL REFERENCES "${schema}".job_orders(id) ON DELETE CASCADE,
  task_id      UUID REFERENCES "${schema}".job_order_tasks(id) ON DELETE SET NULL,
  cost_type    VARCHAR(20) NOT NULL
               CHECK (cost_type IN ('part','material','labour','outsource','transport','consumable','other')),
  source_type  VARCHAR(20) NOT NULL DEFAULT 'manual'
               CHECK (source_type IN ('manual','sale_item','outsource','payout','expense')),
  source_id    UUID,                         -- sale_items.id / job_order_outsources.id / job_order_payouts.id / expenses.id
  description  VARCHAR(255) NOT NULL,
  quantity     DECIMAL(12,3) NOT NULL DEFAULT 1,
  unit_cost    DECIMAL(12,2) NOT NULL DEFAULT 0,
  amount       DECIMAL(12,2) NOT NULL DEFAULT 0,   -- quantity * unit_cost (stored, not computed)
  is_billable  BOOLEAN NOT NULL DEFAULT false,     -- true → also expected to appear as an item line
  employee_id  UUID REFERENCES "${schema}".employees(id) ON DELETE SET NULL,
  payee_id     UUID REFERENCES "${schema}".payees(id) ON DELETE SET NULL,
  expense_id   UUID REFERENCES "${schema}".expenses(id) ON DELETE SET NULL,
  incurred_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  note         VARCHAR(500),
  created_by   UUID,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW(),
  deleted_at   TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_costs_job
  ON "${schema}".job_order_costs(job_id) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_${schema}_job_order_costs_source
  ON "${schema}".job_order_costs(source_type, source_id) WHERE source_id IS NOT NULL AND deleted_at IS NULL;

-- backfill from returned outsources
INSERT INTO "${schema}".job_order_costs
  (job_id, cost_type, source_type, source_id, description, amount, unit_cost, payee_id, expense_id, incurred_at, created_by)
SELECT job_id, 'outsource', 'outsource', id, 'Outsourced repair', cost, cost, payee_id, expense_id,
       COALESCE(returned_at, sent_at), created_by
FROM "${schema}".job_order_outsources WHERE status = 'returned' AND cost > 0 AND deleted_at IS NULL;
```

### 1.7 `job_order_payouts` (NEW — API in Phase 3)

```sql
CREATE TABLE IF NOT EXISTS "${schema}".job_order_payouts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id           UUID NOT NULL REFERENCES "${schema}".job_orders(id) ON DELETE CASCADE,
  task_id          UUID REFERENCES "${schema}".job_order_tasks(id) ON DELETE SET NULL,
  assignment_id    UUID REFERENCES "${schema}".job_order_assignments(id) ON DELETE SET NULL,
  employee_id      UUID NOT NULL REFERENCES "${schema}".employees(id),
  basis            VARCHAR(30) NOT NULL
                   CHECK (basis IN ('fixed','percent_of_line','percent_of_job_total','percent_of_labour','per_unit','hourly','manual')),
  basis_amount     DECIMAL(12,2) NOT NULL DEFAULT 0,   -- the number the rate was applied to
  rate             DECIMAL(12,4) NOT NULL DEFAULT 0,
  share_percent    DECIMAL(5,2)  NOT NULL DEFAULT 100,
  computed_amount  DECIMAL(12,2) NOT NULL DEFAULT 0,
  adjustment       DECIMAL(12,2) NOT NULL DEFAULT 0,
  final_amount     DECIMAL(12,2) NOT NULL DEFAULT 0,   -- computed + adjustment
  status           VARCHAR(20) NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft','approved','in_payroll','paid','cancelled')),
  pay_mode         VARCHAR(20) NOT NULL DEFAULT 'payroll' CHECK (pay_mode IN ('payroll','instant')),
  payroll_item_id  UUID REFERENCES "${schema}".payroll_items(id) ON DELETE SET NULL,
  expense_id       UUID REFERENCES "${schema}".expenses(id) ON DELETE SET NULL,
  approved_by      UUID,
  approved_at      TIMESTAMPTZ,
  paid_at          TIMESTAMPTZ,
  note             VARCHAR(500),
  created_by       UUID,
  created_at       TIMESTAMPTZ DEFAULT NOW(),
  updated_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_payouts_job      ON "${schema}".job_order_payouts(job_id);
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_payouts_employee ON "${schema}".job_order_payouts(employee_id, status);

ALTER TABLE "${schema}".payroll_items ADD COLUMN IF NOT EXISTS job_payout DECIMAL(14,2) DEFAULT 0;
ALTER TABLE "${schema}".payrolls      ADD COLUMN IF NOT EXISTS total_job_payout DECIMAL(14,2) DEFAULT 0;

-- employee default payout rule (Phase 3 uses it; column added now so the form can expose it)
ALTER TABLE "${schema}".employees ADD COLUMN IF NOT EXISTS job_payout_rule JSONB;  -- same shape as tasks.payout_rule
```

### 1.8 `job_order_attributes` (NEW) + devices migration

```sql
CREATE TABLE IF NOT EXISTS "${schema}".job_order_attributes (
  job_id       UUID PRIMARY KEY REFERENCES "${schema}".job_orders(id) ON DELETE CASCADE,
  profile_key  VARCHAR(30) NOT NULL DEFAULT 'generic',
  data         JSONB NOT NULL DEFAULT '{}'::jsonb,
  -- encrypted secrets kept out of `data` so it can be logged/searched safely
  secrets      JSONB NOT NULL DEFAULT '{}'::jsonb,      -- {"lockValue":"<aes-gcm>"}
  -- searchable denormalised keys (kept in sync by service layer)
  search_1     VARCHAR(100),   -- device: imei1 | vehicle: reg_no | garment: order tag
  search_2     VARCHAR(100),   -- device: serial_number
  search_3     VARCHAR(255),   -- device: model_name
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_attr_search1 ON "${schema}".job_order_attributes(search_1) WHERE search_1 IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_${schema}_job_order_attr_search2 ON "${schema}".job_order_attributes(search_2) WHERE search_2 IS NOT NULL;

INSERT INTO "${schema}".job_order_attributes (job_id, profile_key, data, secrets, search_1, search_2, search_3, created_at, updated_at)
SELECT job_id, 'device',
  jsonb_strip_nulls(jsonb_build_object(
    'brandId', brand_id, 'modelName', model_name, 'color', color,
    'imei1', imei1, 'imei2', imei2, 'serialNumber', serial_number,
    'productUnitId', product_unit_id, 'saleItemId', sale_item_id, 'unitWarrantyId', unit_warranty_id,
    'isWarrantyClaim', is_warranty_claim, 'warrantySnapshot', warranty_snapshot,
    'lockType', lock_type, 'physicalCondition', physical_condition,
    'accessoriesReceived', accessories_received, 'inspection', inspection)),
  CASE WHEN lock_value IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('lockValue', lock_value) END,
  imei1, serial_number, model_name, created_at, updated_at
FROM "${schema}".service_job_devices;

DROP TABLE "${schema}".service_job_devices;
```

Profile registry (code, `job-order.profiles.ts`) — one zod schema per `profile_key`:

| profile_key | fields (data) | secrets | search_1/2/3 |
|---|---|---|---|
| `generic` | `{}` free-form `notes?` | – | – |
| `device` | exactly the old device schema | `lockValue` | imei1 / serialNumber / modelName |
| `garment` | `measurements: Record<string,number>`, `fabricProvidedBy: 'customer'\|'shop'`, `fabricDetails?`, `styleNotes?`, `pieces: [{name, qty}]` | – | – / – / styleNotes |
| `vehicle` | `regNo`, `make`, `model`, `year?`, `odometer?`, `fuelLevel?`, `damageNotes?` | – | regNo / – / model |
| `print` | `sizeSpec`, `material`, `finish?`, `colorMode?`, `artworkUrls: string[]`, `quantity` | – | – |

Phase 0/1 ships `generic` + `device` only (device keeps 100% of current UI). Others in
Phase 4 when template/profile forms land. The `unit lookup` + warranty-claim logic from
`upsertDeviceTx` moves into the `device` profile handler unchanged.

### 1.9 System product for ad-hoc lines

```sql
-- once per tenant; idempotent
INSERT INTO "${schema}".products (name, sku/code?, item_type, selling_price, is_system, ...)
VALUES ('Service Charge', 'SYS-SERVICE-CHARGE', 'service', 0, true, ...)
ON CONFLICT DO NOTHING;
```

> Check `products` columns + unique keys (`code`/`sku`) and whether an `is_system` /
> hidden flag exists. If not, add `ALTER TABLE products ADD COLUMN IF NOT EXISTS is_system BOOLEAN NOT NULL DEFAULT false`
> and filter `is_system = false` in product list/search endpoints and POS search.

Delivery (`deliverJobTx`) maps `product_id IS NULL` lines → this product id, keeps
`item_name` as the sale line name (check `processSaleItems` supports a name override; if
not, add `itemNameOverride?: string` to `SaleItemInput` and write it to `sale_items.item_name`
or equivalent column).

### 1.10 Workflow tables (NEW — runtime use in Phase 4)

```sql
CREATE TABLE IF NOT EXISTS "${schema}".job_workflows (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  key           VARCHAR(50) UNIQUE NOT NULL,        -- 'default', 'repair', 'tailoring', ...
  name          VARCHAR(100) NOT NULL,
  is_default    BOOLEAN NOT NULL DEFAULT false,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ DEFAULT NOW(),
  updated_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS "${schema}".job_workflow_states (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workflow_id   UUID NOT NULL REFERENCES "${schema}".job_workflows(id) ON DELETE CASCADE,
  key           VARCHAR(30) NOT NULL,
  label         VARCHAR(100) NOT NULL,
  label_bn      VARCHAR(100),
  color         VARCHAR(20),
  seq           INT NOT NULL DEFAULT 0,
  kind          VARCHAR(20) NOT NULL DEFAULT 'open'
                CHECK (kind IN ('initial','open','ready','done','cancelled')),
  allowed_next  TEXT[] NOT NULL DEFAULT '{}',
  notify_customer BOOLEAN NOT NULL DEFAULT false,
  UNIQUE (workflow_id, key)
);
-- seed 'default' workflow = today's 8 hardcoded states + JOB_TRANSITIONS
-- job_orders.workflow_id FK + backfill every row to default
ALTER TABLE "${schema}".job_orders
  ADD CONSTRAINT job_orders_workflow_fk FOREIGN KEY (workflow_id) REFERENCES "${schema}".job_workflows(id);
UPDATE "${schema}".job_orders SET workflow_id = (SELECT id FROM "${schema}".job_workflows WHERE key = 'default');
```

Invariant (all phases): exactly one state with `kind='done'` (`delivered`) and one
`kind='cancelled'`; `done` is only reachable through `deliverJobTx`, `cancelled` only
through `cancelJobOrder`.

### 1.11 `down()`

Reverse order: drop new tables, drop new columns, recreate `service_job_devices` from
attributes (profile_key='device'), rename tables/indexes/column back, reverse the data
UPDATEs. Must be exact so `migrate down` on a dev DB works.

---

## 2. Backend module `src/modules/job-order/`

Files (renamed + new):

```
job-order.schema.ts        zod
job-order-shared.ts        state machine, reservations, advance, deliverJobTx, reopen hook
job-order.service.ts       CRUD, status, items, advance, deliver, cancel, outsource, lookup, report, stats
job-order-tasks.service.ts tasks + assignments (NEW)
job-order.profiles.ts      profile registry (NEW)
job-order.controller.ts
job-order.routes.ts
```

### 2.1 Shared helpers (`job-order-shared.ts`)

- `recomputeJobTotalsTx(client, schema, jobId)` — updates `items_total`, `cost_total`,
  `payout_total` on `job_orders`. Call after any item/cost/payout write.
- `syncLeadAssigneeTx(client, schema, jobId)` — sets `job_orders.assigned_employee_id`
  = active job-level `lead` assignment employee (or NULL).
- `assertJobOpen(job)` — throws unless status ∉ {delivered, cancelled}.
- `deliverJobTx` changes:
  - ad-hoc lines → system product mapping (§1.9)
  - after `insertCompletedSaleTx`, insert `job_order_costs` rows
    `(cost_type='part', source_type='sale_item', source_id=sale_item.id, amount=qty*cost_price)`
    for every part line — pull cost from the returned `saleItems` (they already carry
    cost for profit). Then `recomputeJobTotalsTx`.
  - Phase 3 will add payout generation here; leave a clearly named hook
    `afterDeliverHooks: Array<(ctx) => Promise<void>>` so it is one insertion point.
- `reopenJobFromVoidedSaleTx`: also soft-delete `job_order_costs WHERE source_type='sale_item' AND source_id IN (voided sale's items)` and recompute totals.

### 2.2 Items (`replaceJobItems`) changes

- Accept new `lineType` values; `productId` optional except `part`/`material`.
- Optional `taskId` per line (must belong to same job).
- `costAmount` optional (manual) — for `part` lines default from
  `products.cost_price` (or variant cost) × qty if not supplied.
- After replace: recompute totals; re-reserve only `part` lines (unchanged logic).
- Items cannot be replaced when job is delivered/cancelled (already true — keep).

### 2.3 Tasks API (`job-order-tasks.service.ts`)

All routes under `/job-orders/:id/tasks`. All require job open unless noted.

| Method & path | Body | Behaviour |
|---|---|---|
| `GET /job-orders/:id/tasks` | – | Tree (parents with `children[]`), each with `assignments[]` (active only unless `?includeHistory=1`), item link summary |
| `POST /job-orders/:id/tasks` | `createTaskSchema` | Insert; `seq` defaults to max+1 among siblings; optional `assignments: [{employeeId, role, sharePercent}]` created atomically |
| `PATCH /job-orders/:id/tasks/:taskId` | `updateTaskSchema` | title/description/quantity/estimatedMinutes/itemId/payoutRule/note/seq |
| `POST /job-orders/:id/tasks/:taskId/status` | `{status, note?, actualMinutes?}` | Transition per §1.4 rules; if all top-level tasks are `done|skipped` and job status is `in_progress`/`waiting_parts`, response includes `suggestStatus: 'ready'` (no auto-change) |
| `DELETE /job-orders/:id/tasks/:taskId` | – | Soft delete; cascades soft-delete to children; unassigns active assignments (`unassigned_at = NOW()`); fails if task has approved/paid payouts (Phase 3) |
| `PUT /job-orders/:id/tasks/reorder` | `{order: [{taskId, seq, parentTaskId?}]}` | Bulk reorder |
| `POST /job-orders/:id/tasks/bulk` | `{tasks: [createTask...]}` | Used by template apply (Phase 4) and by the "add several" UI |

### 2.4 Assignments API

| Method & path | Body | Behaviour |
|---|---|---|
| `GET /job-orders/:id/assignments` | `?includeHistory=1` | Flat list (job-level + task-level) with employee name, task title |
| `POST /job-orders/:id/assignments` | `{taskId?: uuid\|null, employeeId, role, sharePercent?, note?}` | Create; enforces one active lead (job-level), unique active (task, employee), Σ share ≤ 100 per task; calls `syncLeadAssigneeTx` when role='lead' && taskId null |
| `PATCH /job-orders/:id/assignments/:aid` | `{role?, sharePercent?, note?}` | Only active assignments |
| `DELETE /job-orders/:id/assignments/:aid` | `{note?}` (body optional) | Sets `unassigned_at`, `unassigned_by`; sync lead |
| `GET /job-orders/my-tasks` | `?status=&from=&to=` | For logged-in user → `employees.user_id = req.user.id`; returns tasks (with job header) where employee has active assignment, task-level or job-level. Route defined **before** `/:id` |

`createJobOrder` / `updateJobOrder` keep accepting `assignedEmployeeId` for backward
compat: it is translated into a job-level `lead` assignment (create) or lead replacement
(update). Also accept optional `tasks: [...]` in create payload (same shape as bulk).

### 2.5 Read model changes

- `getJobOrderById` returns additionally: `attributes` (profile_key, data, secrets
  decrypted only for roles owner/manager/technician — same rule as today's lock_value),
  `tasks` (tree), `assignments` (active), `costs` (list; Phase 2 fills UI),
  `payouts` (list; Phase 3), `totals: {items, costs, payouts, profit = items - costs - payouts}`.
- `listJobOrders`: add filters `employeeId` (any active assignment, not just lead),
  `taskStatus`, `profileKey`; keep `assignedEmployeeId` (lead only). `search` now hits
  `job_order_attributes.search_1/2/3` instead of device columns.
- `getJobOrderStats`: add `myOpenTasks` when the caller maps to an employee.

### 2.6 Zod additions (`job-order.schema.ts`)

```ts
export const LINE_TYPES = ['service','part','labour','fee','material','other'] as const;
export const TASK_STATUSES = ['pending','in_progress','blocked','done','skipped'] as const;
export const ASSIGNMENT_ROLES = ['lead','worker','helper','qc','sales'] as const;
export const PAYOUT_BASES = ['fixed','percent_of_line','percent_of_job_total','percent_of_labour','per_unit','hourly'] as const;

export const payoutRuleSchema = z.object({ basis: z.enum(PAYOUT_BASES), rate: z.number().min(0) });

const jobItemSchema = z.object({
  lineType: z.enum(LINE_TYPES).default('service'),
  productId: uuid.optional().nullable(),
  variantId: uuid.optional().nullable(),
  itemName: z.string().max(255).optional().nullable(),
  quantity: z.number().positive(),
  unitPrice: z.number().min(0),
  discount: z.number().min(0).default(0),
  costAmount: z.number().min(0).optional().nullable(),
  taskId: uuid.optional().nullable(),
  unitIds: z.array(uuid).optional().default([]),
  isWarrantyCovered: z.boolean().optional().default(false),
}).superRefine((v, ctx) => {
  if ((v.lineType === 'part' || v.lineType === 'material') && !v.productId)
    ctx.addIssue({ code: 'custom', path: ['productId'], message: 'Parts/materials must reference a product' });
  if (!v.productId && !v.itemName)
    ctx.addIssue({ code: 'custom', path: ['itemName'], message: 'Ad-hoc lines need a name' });
});

export const assignmentInputSchema = z.object({
  taskId: uuid.optional().nullable(),
  employeeId: uuid,
  role: z.enum(ASSIGNMENT_ROLES).default('worker'),
  sharePercent: z.number().gt(0).max(100).default(100),
  note: z.string().max(500).optional().nullable(),
});

export const createTaskSchema = z.object({
  parentTaskId: uuid.optional().nullable(),
  title: z.string().min(1).max(255),
  description: z.string().max(2000).optional().nullable(),
  quantity: z.number().positive().default(1),
  estimatedMinutes: z.number().int().min(0).optional().nullable(),
  itemId: uuid.optional().nullable(),
  payoutRule: payoutRuleSchema.optional().nullable(),
  note: z.string().max(500).optional().nullable(),
  assignments: z.array(assignmentInputSchema.omit({ taskId: true })).max(10).optional().default([]),
});
export const updateTaskSchema = createTaskSchema.omit({ assignments: true, parentTaskId: true }).partial().extend({ seq: z.number().int().min(0).optional() });
export const changeTaskStatusSchema = z.object({ status: z.enum(TASK_STATUSES), note: z.string().max(500).optional().nullable(), actualMinutes: z.number().int().min(0).optional().nullable() });
export const reorderTasksSchema = z.object({ order: z.array(z.object({ taskId: uuid, seq: z.number().int().min(0), parentTaskId: uuid.optional().nullable() })).max(200) });

// createJobOrderSchema: replace `device` with
//   profileKey: z.enum(['generic','device']).default('generic'),
//   attributes: z.record(z.unknown()).optional().default({}),   // validated against profile registry in service
// keep `device` accepted for one release as alias → { profileKey:'device', attributes: device }
// add: tasks: z.array(createTaskSchema).max(50).optional().default([])
```

### 2.7 Other backend touch points for the rename

- `app.ts` mount `/job-orders`; keep `app.use('/service-jobs', jobOrderRoutes)` alias
  for one release (partner-api consumers) — log deprecation.
- `number-series`: `DocType 'job_order'`, default `{ name: 'Job Order', prefix: 'JOB' }`,
  table map `{ table: 'job_orders', column: 'job_no' }`, ordering CASE.
- `templates`: `job_order_pdf` in types/schema/controller/routes/render; `document-context.ts`
  reads `job_orders`, `job_order_items`, attributes (device fields from `data`).
- `sale-tx.ts` `serviceJobId` → `jobOrderId`, column `job_order_id`.
- `sale.service.ts` void hook import path.
- `customer.controller.ts` job history query → `job_orders`.
- `unit-inspection.schema.ts` context `'job_order'`.
- `seeds/menus.ts` labels "Job Orders", hrefs `/job-orders`, keys `job_orders.create`,
  `pos.job_order`, `/reports?tab=job-orders`. Also add `{ label: 'My Tasks', href: '/job-orders/my-tasks' }`
  child for all roles.

---

## 3. Frontend (`shop-app-web`)

### 3.1 Rename

- `src/lib/service-jobs.ts` → `src/lib/job-orders.ts` (API base `/job-orders`, types renamed
  `JobOrder`, `JobOrderItem`, `JobOrderTask`, `JobOrderAssignment`, …).
- `app/(dashboard)/service-jobs/*` → `app/(dashboard)/job-orders/*`.
- `app/(dashboard)/service-jobs/page.tsx`, `service-jobs/new/page.tsx`,
  `service-jobs/[id]/page.tsx`, `service-cases/*` → tiny redirect components to the
  matching `/job-orders/...` path (preserve `[id]`).
- Update references: `sidebar.tsx`, `pos/_components/payment-panel.tsx`, `customers/page.tsx`,
  `settings/page.tsx`, `settings/templates/_components/template-editor.tsx`, `lib/templates.ts`,
  `lib/number-series.ts`, `lib/unit-inspection.ts`, `reports/page.tsx` (tab key `job-orders`),
  dashboard `page.tsx`.
- UI copy: "Service Job" → "Job Order" (en), "জব অর্ডার" (bn) — check translation module keys.

### 3.2 New / changed screens (Phase 1)

**`/job-orders/[id]` — add "Work" tab** (between Overview and Items):
- Task list (tree, drag reorder), each row: seq, title, status pill, assignees (avatar
  chips with role), linked item name, est/actual minutes, quantity.
- Row actions: start / done / block / skip / reopen; edit; add sub-task; delete.
- "Add task" inline form: title, quantity, estimated minutes, link to item (select from
  job items), assign employees (multi-select with role + share %), payout rule (basis +
  rate — visible only to owner/manager).
- Banner when all tasks done and job not ready: "All tasks complete — mark job Ready?"
  (calls existing status endpoint).

**Assignments panel** (Overview tab, replaces the single "Assigned to" select):
- Lead (single select, writes role=lead job-level).
- "Team" list: job-level workers + per-task assignees, with unassign.
- Reassign lead → confirm dialog (history preserved).

**Items tab**:
- Line type select gets `labour`, `fee`, `material`, `other`.
- Product picker optional for non-part lines; free-text name required then.
- Optional "task" column (link line to a task).
- Cost column (owner/manager only), default filled for parts.

**Intake (`/job-orders/new`)**:
- Profile switch: `generic` | `device` (device only offered when business category ∈
  MOBILE_SHOP / electronics — reuse the same `categories` gating the menu seed uses;
  otherwise default generic and hide the switch).
- Optional "Tasks" section (repeatable rows: title, qty, assign) sent as `tasks[]`.
- Lead employee select stays (maps to `assignedEmployeeId`).

**`/job-orders/my-tasks`** (new page, all roles):
- List of the current user's tasks grouped by job; quick status buttons; filter by
  status/date. Uses `GET /job-orders/my-tasks`.

**Employee form (finance → employees)**: add "Default job payout rule" (basis + rate)
field bound to `employees.job_payout_rule`. Display only; Phase 3 consumes it.

### 3.3 Components to add under `src/components/job-orders/`

`task-tree.tsx`, `task-row.tsx`, `task-form-dialog.tsx`, `assignee-picker.tsx`
(employee multi-select with role/share), `payout-rule-field.tsx`, `profile-fields/device.tsx`
(moved out of the 1088-line new page), `profile-fields/generic.tsx`.

Use existing UI primitives (`Button`, `Dialog`, `Badge`, `Table`, `EmptyState`, …) and
theme tokens only — no hardcoded colors (see `AGENTS.md`).

---

## 4. Verification checklist

Backend
- `npx tsc --noEmit` clean.
- Fresh tenant: run all migrations → `job_orders*` tables exist, `service_job*` do not,
  default workflow seeded, system product exists.
- Existing tenant snapshot: run `101` up → row counts equal before/after for jobs, items,
  history, outsources; every old device row has a matching attributes row with
  `profile_key='device'` and identical IMEI/serial; every `assigned_employee_id` has a
  matching active lead assignment; `payments.reference_type='service_job'` count = 0.
- `migrate down` then `up` again on a dev DB succeeds.
- Smoke (curl / REST client): create job with `tasks[]` + `assignedEmployeeId` → GET shows
  lead assignment + tasks; add ad-hoc `labour` line without productId → deliver → sale
  created with system product line named from `item_name`; part line → cost row exists
  with `source_type='sale_item'`; void sale → job back to `ready`, cost row soft-deleted.
- Assignment rules: second lead replaces first (history has 2 rows, 1 active); share >100
  on a task → 400; inactive employee → 400.
- Task rules: `done → in_progress` allowed while open, rejected after deliver; delete
  task unassigns.
- Old `/service-jobs` API alias still answers.

Frontend
- `npm run build` clean.
- `/service-jobs`, `/service-jobs/<id>`, `/service-cases` redirect to `/job-orders/...`.
- Intake → detail → Work tab → assign → mark done → banner → Ready → Deliver full path
  works in browser for both `generic` and `device` profile.
- Sidebar shows "Job Orders" + "My Tasks"; reports tab `job-orders` loads.

---

## 5. Out of scope for Phase 0/1 (later phases, tables already exist)

- Phase 2: costs API + manual cost entry + profitability panel/report; outsource returned →
  auto cost row (hook in `updateOutsource`).
- Phase 3: payout generation on deliver (rule resolution: task.payout_rule →
  employee.job_payout_rule → none), approve/adjust/cancel, payroll pull (`payroll_items.job_payout`),
  instant pay → expense + cashbox, void → cancel payouts.
- Phase 4: workflow CRUD + DB-driven transitions, job templates, extra profiles
  (garment/vehicle/print) with schema-driven forms.
- Phase 5: estimate approval, milestone invoicing (`job_order_invoices`), time tracking.
