# Quotation Drafts — Safe Add-on (2026-11-12)

This module adds **draft quotations only**, not legal tax documents, accounts-receivable entries, sales orders, delivery reservations, or binding offers.

## Scope and routes

- `POST /api/quotations` — roles `admin` and `sales`. Requires authenticated session and CSRF. JSON:
  ```json
  {
    "request_key": "synthetic-quotation-idempotency-0001",
    "customer_id": 1,
    "vat_price_mode": "exclusive",
    "lines": [{"product_id": 1, "quantity": 2}],
    "expires_on": null,
    "note": "Synthetic example"
  }
  ```
  `request_key` must be 16–80 characters; a replay with the identical request returns the same draft with HTTP 200. A changed request that reuses a key returns 409. Concurrent key conflicts are also rejected; callers must reconcile a 409 by reading their known quotation, not blindly repeat with a different key.
- `GET /api/quotations?limit=50&before=<id>` — roles `admin`, `sales`, `accountant`.
- `GET /api/quotations/<id>` — immutable customer/product/price snapshot.
- `GET /api/quotations/<id>/print` — explicitly labeled *QUOTATION DRAFT* browser print preview, not a tax invoice.
- On `/app` see **ใบเสนอราคา**, where authorized sales users can add product lines, select customer and VAT pricing mode, then create and review a draft.

## Pricing and stock behavior

- Prices come from the database: customer-specific `CustomerPrice` takes priority over `Product.price`; the client cannot submit arbitrary unit prices.
- Server computes Decimal totals and VAT for inclusive/exclusive inputs at document level with `ROUND_HALF_UP`, as in the current sales workflow.
- Creating a quotation does **not** create a `Sale`, `Payment`, `StockMovement`, invoice, receipt or warehouse reservation. Quote prices are *not guaranteed* at later sale time.
- Customer name/address/tax ID and product SKU/name/unit price are copied at creation. Later customer/product edits do not silently rewrite old quotation drafts.
- The reference `QT-DRAFT-000001` is a local quotation identifier, **not** a legally issued document number.

## Limits and gaps

- Draft-only state; sending, customer acceptance, quote-to-order conversion, revision history, discount approval, legally effective quotation content, sales order and billing note workflow are **not implemented**.
- Printed preview is minimally styled, and hardware printing remains unverified.
- Customer/product selection on existing pages is still currently limited by legacy list endpoints; additional server search integration should be handled separately.
- This module uses a new Alembic revision `e2b6d09c4112`, adding `quotation` and `quotation_line` tables only; it does not rewrite existing tables.
- Migration `downgrade` irreversibly drops quotation data. Never run it on business data.

## Verification and deployment gates

CI runs PostgreSQL 16, Alembic upgrade/schema drift/downgrade/upgrade, pytest role/stock/snapshot/idempotency tests, and Playwright UI smoke test on synthetic data. Check the latest run rather than assuming prior success.

Render staging currently follows `feature/thanabunyapat-online` rather than this branch, and its database backup/restore status was **not verified**. No staging or production deployment is authorized until backup and isolation are verified. Never alter `main` or deploy Production as part of this add-on.
