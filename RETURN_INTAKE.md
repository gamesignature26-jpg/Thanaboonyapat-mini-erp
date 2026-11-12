# Customer Return Intake — Safe Add-on (2026-11-12)

This module records customer requests to return goods and warehouse inspection outcomes. It **does not issue a tax credit note, refund money, adjust the sale price, reduce a customer's outstanding balance, or reverse a payment**. Accounting review and legal credit-note issuance are a separate, unimplemented step.

## New API contract
- `POST /api/returns` — admin / sales only, CSRF required:
  ```json
  {
    "request_key": "synthetic-return-intake-0000001",
    "sale_id": 1,
    "reason": "Customer brought sealed packs back",
    "lines": [{"sale_line_id": 1, "quantity": 2}]
  }
  ```
  Requires 1–100 distinct lines from the same sale. Each quantity is positive and must not exceed the currently unreturned sold quantity. `request_key` is 16–80 characters, globally unique. Identical retries return 200; changed payload with same key returns 409.
- `GET /api/returns` with optional `limit` and `before` — admin, sales, warehouse and accountant.
- `GET /api/returns/sales/<sale_id>/eligible` — shows sold, previously received and remaining physical quantities for each sale line, but no sale monetary amounts.
- `GET /api/returns/<return_id>` — safe reason/status/quantity details, no financial change.
- `GET /api/returns/<return_id>/print` — clearly labeled internal return preview; not a tax credit note.
- `POST /api/returns/<return_id>/inspect` — admin / warehouse only:
  ```json
  {"condition": "resellable", "inspection_note": "Sealed packs checked"}
  ```
  Choose either `resellable` or `damaged`. `resellable` increases Product.stock and appends positive StockMovement records referencing the original Sale; `damaged` records received items but **does not** increase sellable stock. Receiving checks the sum of already received units under row locks to prevent overshooting sold quantity across overlapping requests. A repeated identical inspection cannot restock twice; a changed retry returns 409.
- `POST /api/returns/<return_id>/reject` — admin / warehouse only, with required `inspection_note`, no stock movement.

## User interface

`/app` now includes **รับคืนสินค้า** for admins, sales and warehouse/accountant staff with role-specific actions. Sales enters a sale ID, loads eligible lines, drafts a request and views status. Warehouse checks goods and marks resellable/damaged/rejected. All staff who can access returns may inspect and print internal records.

## Hard safety boundaries

1. A draft does not adjust stock. Only warehouse physical inspection of **resellable** items restores sellable stock; damaged stock is tracked as received but not on-hand inventory.
2. The original `Sale.total`, `Sale.paid`, `Payment`, `IssuedDocument` and receivables remain unchanged. A request marked received is **not** a customer refund or tax adjustment.
3. All identifiers, snapshots, actors and inspector notes are stored in new `return_intake` / `return_intake_line` tables. Migration `8ac4b7e0d221` is additive and retains all existing sales.
4. A single request uses one inspection condition for all its lines. Mixed resellable/damaged returns require separate return requests. Financial credit/returns ledger, refunded quantities per tax rate, formal approval, and legally valid Thai credit-note handling **remain to be designed and reviewed**.
5. The migration downgrade destroys return audit records. Never run downgrade in staging or production business data.
6. Tests use synthetic disposable PostgreSQL, checking authorization, duplicate submissions, concurrent-style over-return constraints, damaged returns, unchanged sales/receivables, and browser UI. A passing CI suite does not substitute for restoring a real verified backup.
7. Staging currently tracks an older feature branch; backup restore/isolation has not been verified. Do not deploy, migrate, or use real data until these gates are confirmed.

Refer to `WORK_HANDOFF_2026-11-12.md` for continuation and review gates.
