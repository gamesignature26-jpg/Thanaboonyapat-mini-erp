# Financial credit-note review drafts — NON-POSTING

## Scope

Separate from physical ReturnIntake, customer receivables, cash refunds, tax invoices, and officially issued Thai tax credit notes. No draft number should be displayed as a legal tax-document number.

- The warehouse must first mark the linked return as `received` (resellable or damaged).
- Owner/admin and accountant may create, read, print or void a `CREDIT-DRAFT-000001` preview. Sales and warehouse roles cannot access these endpoints.
- Human-entered `amount_ex_vat` and `vat_amount` must be validated Decimal currency strings, with an explicit reason and idempotency key. The combined active proposals for a sale cannot exceed the sale's original before-VAT amount or VAT.
- A given physically received return can have only **one** financial review record, even after voiding. This prevents silent rewriting of an earlier reviewed proposal; a correction requires a separate formally reviewed process.
- Creation snapshots buyer/return details, the original recorded sale and payment amounts, and each returned sale line. Current sale balance is re-read on each detail request and does not change on draft creation.
- The printable HTML states visibly that the draft is not a tax credit note, receipt or refund record.
- Voiding requires an explanation, actor and timestamp; it never changes the sales ledger.
- Duplicate key + identical body is safe. Same key + altered body, or a second draft for the same received return, is rejected.

## API

POST `/api/credit-note-drafts`:

```json
{
  "request_key": "synthetic-credit-review-00001",
  "return_id": 1,
  "reason": "Synthetic accounting review",
  "amount_ex_vat": "100.00",
  "vat_amount": "7.00"
}
```

GET `/api/credit-note-drafts?limit=50&before=<id>` — list all including voided.

GET `/api/credit-note-drafts/<id>` — immutable snapshots and live outstanding.

GET `/api/credit-note-drafts/<id>/print` — preview only.

POST `/api/credit-note-drafts/<id>/void` with `{"reason":"Synthetic correction"}`.

## Critical accounting boundary

No Sale, Payment, Product, StockMovement, IssuedDocument, receivables posting or refund is created/modified. No automatic VAT reassessment or allocation of mixed VAT/discount/shipping items is attempted. The operator must reconcile issued tax invoice references, customer payments, net tax, and statutory credit-note rules with an accountant before any legal issuance. The draft **does not establish that the proposed amount is correct**.

## Schema and tests

Migration `bd8c1a770e21_credit_note_drafts.py` adds only one new `credit_note_draft` table. Its downgrade irreversibly drops the draft records; run downgrade only in disposable CI databases. CI covers migration upgrade/check/downgrade/upgrade, synthetic Python tests in `tests/test_credit_note_drafts.py`, and mobile browser draft-creation flow. The printable endpoint is covered by the Python integration test; physical printing was not tested. The staging database has **not** been migrated.
