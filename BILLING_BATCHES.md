# Multi-sale Billing Drafts (2026-11-12)

This feature extends existing **per-sale** billing previews with a separate, auditable multi-sale billing **draft**. It is **not** a tax invoice, receipt, automatically delivered bill or recorded accounts-receivable posting.

## User workflow

1. In **ใบวางบิลรวม**, an owner/accountant selects one customer and loads available unpaid sales.
2. Select 1–25 eligible sales (all belonging to that customer) and provide an optional internal note.
3. Save a new draft. The reference is `BATCH-DRAFT-000001`, **not an issued invoice number**.
4. Inspect the immutable *amount outstanding at draft creation* alongside the *current outstanding* computed from actual recorded payments each time the document is opened. Print the labeled draft if useful.
5. If grouping is wrong, the owner/accountant may void it with a mandatory reason; only then can the same sale join a new draft. Voiding does not reverse payments or stock.

Sales staff can view drafts and print previews, but cannot create or void them. Warehouse staff cannot access draft endpoints.

## APIs

- `GET /api/billing-batches/eligible?customer_id=<id>&limit=50&before=<id>` — returns open, unclaimed customer sales, paged by descending Sale ID.
- `POST /api/billing-batches` — accountant/admin. Requires session CSRF and exact JSON:

  ```json
  {
    "request_key": "synthetic-billing-intent-20261112-0001",
    "customer_id": 1,
    "sale_ids": [1, 2],
    "note": "Synthetic November billing draft"
  }
  ```

- `GET /api/billing-batches?limit=50&before=<id>` — list history, including voided drafts.
- `GET /api/billing-batches/<id>` — creator/print metadata, snapshots and currently outstanding balances.
- `GET /api/billing-batches/<id>/print` — printable browser draft, explicitly not a tax invoice/receipt.
- `POST /api/billing-batches/<id>/void` — accountant/admin, body `{"reason":"Synthetic revised customer grouping"}`.

## Financial integrity guarantees

- Does not alter `Sale`, `Payment`, `SaleLine`, `StockMovement`, `IssuedDocument`, or any other existing financial ledger.
- Only open sales of **one** customer are accepted; paid-in-full sales, duplicate sale IDs, bad amounts and missing sales are rejected.
- A sale can belong to only one **active** billing draft at a time. Sorted row locks serialize concurrent attempts to claim the same sale. Voided drafts are retained for audit history.
- Identical retries with the same 16–80 character `request_key` return the existing draft; changed payload using that key returns HTTP 409. A simultaneous conflicting key may return HTTP 409 from database uniqueness checks.
- Original sale date/total, paid-to-date and outstanding amount are snapshotted into `billing_batch_line`. Later payments automatically change `current_outstanding` shown on reads, while originals remain unchanged.
- Customer name, tax ID and address are snapshotted when the draft is created; later changes do not silently rewrite historical drafts.
- This is **not legal issuing or delivery**. There are no due dates, e-signatures, customer acknowledgements, accounting postings or email/LINE delivery. Real document validity must be reviewed separately with the accountant.

## Schema and rollout

Migration `6f9d20c8a7b1_billing_batches.py` adds only `billing_batch` and `billing_batch_line`; no modifications to historic tables. Its downgrade **irreversibly deletes billing drafts** and is for disposable CI databases only.

Tests in `tests/test_billing_batches.py` cover role/CSRF access, multiple sales, data snapshots, live balance changes after payment, rejection of mixed customers/paid sales, idempotent retries, duplicate active claims, explicit void/recreate, print escaping, pagination and concurrent PostgreSQL locking. Mobile browser flow in `tests/ui_smoke.py` checks draft creation and preview printing.

Check **latest** GitHub Actions on `feature/flow-loyverse-additions-20261112` for full CI status. Tests use synthetic data in disposable databases only.

Render staging still tracks the older `feature/thanabunyapat-online`. Until isolation and verified backup/restore are established, **do not deploy this branch, change Render's branch, or run migrations against its existing Postgres**. Never modify `main` or Production.
