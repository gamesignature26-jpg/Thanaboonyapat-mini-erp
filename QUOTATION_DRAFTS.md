# Quotation Drafts — Safe Add-on (2026-11-12)

This module adds internal quotation drafts and a staff-recorded approval/conversion workflow. A quote alone creates no sale, payment, stock reservation, or binding tax document. An explicitly confirmed conversion uses the **existing** wholesale sale engine and creates a credit sale.

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
- `POST /api/quotations/<id>/status` — staff records `draft -> sent -> accepted/declined` with required contact note and immutable audit events. This records staff-reported communication, not externally verified customer approval. Expired quotes cannot be newly accepted.
- `POST /api/quotations/<id>/convert` — only accepted, unexpired quotes; makes an idempotent **wholesale credit sale** through `erp.online.create_order` with row-locked stock, current VAT/prices and expected total; rejects price/SKU/quantity mismatch, depleted inventory, expired quote and changed delivery payload on retry. It stores a unique `sale_id` on the quote. Optional request fields: `delivery_mode` (`pickup` or `delivery`), `delivery_date`, `address`, `phone`, `driver`, `note`. Conversion does not automatically receive payment. Shipping fee and discount are zero; changes require a new quotation workflow.
- On `/app` see **ใบเสนอราคา**, where sales/admin users can create drafts, record status notes, review history and convert an accepted quote. Accountant can view but cannot change statuses/convert.

## Pricing and stock behavior

- Prices come from the database: customer-specific `CustomerPrice` takes priority over `Product.price`; the client cannot submit arbitrary unit prices.
- Server computes Decimal totals and VAT for inclusive/exclusive inputs at document level with `ROUND_HALF_UP`, as in the current sales workflow.
- Creating a quotation does **not** create a `Sale`, `Payment`, `StockMovement`, invoice, receipt or warehouse reservation. Quote prices are *not guaranteed* at later sale time.
- Customer name/address/tax ID and product SKU/name/unit price are copied at creation. Later customer/product edits do not silently rewrite old quotation drafts.
- The reference `QT-DRAFT-000001` is a local quotation identifier, **not** a legally issued document number.

## Limits and gaps

- **Not implemented:** formal customer e-signature, automated email delivery, revision/version history, discount approvals, official sales order issuance, a legally effective quotation approval trail, or certified tax documents.
- `erp/billing_previews.py` offers `GET /api/billing-notes`, `GET /api/billing-notes/<sale_id>` and printable `GET /api/billing-notes/<sale_id>/print`: read-only billing previews from existing sales and current payment balances. These are **not persisted/issued billing notes** and do not add receivables. Sales and accountant may view; warehouse cannot.
- Printed preview is minimally styled, and hardware printing remains unverified.
- Customer/product selection on existing pages is still currently limited by legacy list endpoints; additional server search integration should be handled separately.
- Alembic `e2b6d09c4112` adds quotation tables; `7c2d441e9ab0` adds a unique sale link, conversion request hash and append-only quotation-event table. Existing Sale/Stock/Payment tables are not changed.
- Migration `downgrade` irreversibly drops quotation data. Never run it on business data.

## Verification and deployment gates

CI runs PostgreSQL 16, Alembic upgrade/schema drift/downgrade/upgrade, pytest role/stock/snapshot/idempotency tests, and Playwright UI smoke test on synthetic data. Last confirmed full CI green for code including both modules: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43083722162; inspect latest GitHub Actions again after subsequent documentation-only changes.

Render staging currently follows `feature/thanabunyapat-online` rather than this branch, and its database backup/restore status was **not verified**. No staging or production deployment is authorized until backup and isolation are verified. Never alter `main` or deploy Production as part of this add-on.
