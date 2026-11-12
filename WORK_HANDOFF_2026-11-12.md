# ChatGPT Work Handoff — Thanabunyapat Mini ERP
Updated: 2026-11-12 (Asia/Bangkok)

## Source of truth
- Repo: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp
- Current development branch: `feature/flow-loyverse-additions-20261112`
- Last fully validated purchasing code commit: `27d0fba05ae6c3be6f3f2603f1a76125280dd4b4`
- Passing GitHub Actions (code + PostgreSQL + browser): https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43206103948
- Original branch kept unchanged: `feature/thanabunyapat-online`; production branch `main` must not be modified or merged.
- Previous README/HANDOFF.md may describe an older MVP; inspect actual branch code before deciding whether features are absent.

## What exists in this branch
- Flask / SQLAlchemy / PostgreSQL / Alembic, authenticated roles and CSRF.
- POS and wholesale orders; inclusive/exclusive VAT price modes; idempotent order creation; delivery state.
- Customer-specific prices, product images, stock movements, sales, partial payments, issued document drafts, A4 and 58mm print views, BLE printer UI, Excel import/export, expenses, driver and LINE-draft modules.
- `erp/receivables_report.py`: read-only `GET /api/reports/receivables` for admin/accountant, with `tests/test_receivables_report.py`.
- `erp/customer_lookup.py`: `GET /api/customers/lookup` with q/limit/after, and `GET /api/customers/<customer_id>/history`, restricted to admin/sales/accountant, with `tests/test_customer_lookup.py`.
- `erp/static/online/app.js`: customer-directory button for server search and customer purchase-history panel.
- Successful CI on last code commit includes Ruff check/format, Alembic upgrade/check/downgrade/upgrade, PostgreSQL pytest, Playwright UI smoke test. This is not evidence of real-device Bluetooth printing or accounting/legal compliance.

## Owner's request
Continue adding missing FlowAccount-like accounting/document functions and Loyverse-like retail/POS functions to this existing app, *only when not already implemented*. Preserve existing business workflows, data, code behavior, and interfaces. Prioritize functions useful for bottled-water wholesale/distribution around Samut Prakan.

## Completed in this continuation (2026-11-12)

- Added `erp/quotations.py`: authenticated, idempotent quotation drafts with immutable price/customer/product snapshots, inclusive/exclusive VAT, expiry/note and zero stock/sale/payment side effects.
- Added `migrations/versions/e2b6d09c4112_quotation_drafts.py`: additive `quotation` / `quotation_line` tables. No existing tables changed.
- Added `erp/templates/quotation_print.html` draft-only print preview, `/app` navigation/form/list/detail under `erp/static/online/app.js`, `tests/test_quotations.py` and mobile Playwright test in `tests/ui_smoke.py`.
- Contract, limitations, and rollout safeguards: `QUOTATION_DRAFTS.md`.
- Added audited status transitions in `erp/quotations.py` and new `QuotationEvent`/sale-link fields via `migrations/versions/7c2d441e9ab0_quotation_workflow.py`.
- Added idempotent accepted-quote conversion through existing wholesale sale/stock path, strict price/quantity/VAT checks and role-limited UI. Corresponding tests: `tests/test_quotation_conversion.py` plus Playwright mobile checks.
- Added `erp/billing_previews.py` and `erp/templates/billing_preview.html`: read-only customer billing view/print from existing Sale (not legally issued). Added Sales-page print link, `tests/test_billing_previews.py` and browser smoke check.
- Last verified **code** CI pass: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43083722162 (commit `91ad03407ebf15d361058578c2a050acd89b1288`). Browser diagnostic cleanup and docs revisions are later commits; check latest CI.
- Render review: selected confirmed workspace `Gamesignature26's workspace`; staging web service is `thanabunyapat-erp-staging-c8km`, still follows original `feature/thanabunyapat-online`; Postgres `thanabunyapat-erp-test` is Free with expiry date 2026-12-06. No verified backup restore, so **no Deploy**, no Render migrations and no production changes.
- Added `erp/return_intake.py`, migration `migrations/versions/8ac4b7e0d221_return_intake.py`, `erp/templates/return_intake_print.html`, return menu/actions in `erp/static/online/app.js`, test suite `tests/test_return_intake.py` and mobile UI smoke. Return drafts are idempotent, warehouse-only inspection records condition/actor, only resellable returns restock with a positive StockMovement; overlapping returns cannot exceed sold quantities.
- **This is NOT a tax credit note/refund**. Sale.total, Sale.paid, Payment, IssuedDocument and outstanding receivables are not modified. Damaged returns are recorded but not restocked. Read `RETURN_INTAKE.md` for exact contract and limits.
- Latest full CI PASS for code including return print/mobile flow: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43185938399 (SHA `7e968f8c649d032caded9ac9caabe6a85f9ffb79`). Documentation-only follow-up commits may have newer CI checks.
- Added `erp/purchasing.py` and `migrations/versions/9b2a11e4d508_purchasing.py` with separate Supplier, PurchaseOrder and PurchaseOrderLine data. Supplier registration and idempotent purchase drafts (snapshot quantity, SKU/name and ex-VAT unit cost) **do not** move stock. Warehouse-only full physical receiving increments stock with StockMovement audit in one transaction, rejects conflicting retries, and locks purchase/product rows in PostgreSQL.
- Added `/app` purchasing UI, new menus and restricted roles in `erp/static/online/app.js`; purchase/create/detail/receive endpoints, synthetic `tests/test_purchasing.py` including concurrent receiving protection, plus Playwright browser flow in `tests/ui_smoke.py`. Detailed contracts: `PURCHASING.md`.
- Latest full CI green including migration verification, Python/Postgres, concurrent receipts and browser: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43206103948 (code SHA `27d0fba05ae6c3be6f3f2603f1a76125280dd4b4`).
- This is **not yet cost of goods sold**: purchase costs are ex-purchase-VAT snapshots only. Historical stock and sales lack reliable opening/inventory costs; no supplier payable, supplier payment, purchasing tax entry, weighted-average/FIFO inventory valuation, or gross/net profit can be inferred.
- Added `erp/billing_batches.py`, `migrations/versions/6f9d20c8a7b1_billing_batches.py`, and `erp/templates/billing_batch_print.html`: multi-sale billing drafts with 1–25 unpaid sales of **one customer**, snapshot of original and current outstanding amounts, per-sale active-draft protection, staff audit metadata, idempotent creation/void, and a clearly labeled print preview.
- New **ใบวางบิลรวม** UI under Sales in `erp/static/online/app.js` for owner/accountant to create/void drafts; sales can read and print. `tests/test_billing_batches.py` covers unauthorized access, mixed customers, fully paid sales, idempotency, void/reissue, concurrency, payment updates, and snapshot immutability. `tests/ui_smoke.py` covers mobile draft creation and printing.
- Latest verified full CI **PASS** for code and mobile print preview: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43226624112 (SHA `7f65feffb9efe155870c35221b8e3079beab8dbc`). This proves automated tests only, not real printer or legal document compliance.
- Full contract, limitations, rollout gates: `BILLING_BATCHES.md`. Multi-sale batches are **drafts**, not official issued billing notes, tax invoices or payments. No changes to Sale/Payment/StockMovement, and no staging or production deployment.
- Next: opening stock valuation and verifiable cost basis, cost-at-sale snapshot and gross profit; accountant-reviewed financial credit-note drafts, real customer quote approvals/revisions; LINE webhook duplicate event security; actual Bluetooth printer compatibility tests. Never confuse physical return intake with a tax credit note.

## Immediate next work (in priority order)
1. Re-audit actual routes, models, templates, JS and tests to prevent duplicate features and identify incomplete implementations.
2. Multi-sale billing **drafts** are implemented and tested. Next: formal legally valid billing-note issuance, customer acceptance/delivery verification, quote revisions and evidence, only after document/business rules are approved. Never bypass stock/price checks when converting a quote. Do **not** misuse `IssuedDocument` tax invoice/receipt semantics. Draft numbers must be separate from legally issued document numbers. New states must have explicit validation, auth and immutable snapshots where appropriate.
3. Physical return draft/inspection with guarded resellable stock restock is already implemented. Next add a **separately approved financial credit-note draft** with review of Thai tax rules, VAT mode, payment reconciliation and receivables; do not reverse financial ledgers automatically when warehouse receives goods.
4. Supplier purchase drafts and one-time full physical stock receiving **are implemented**. Next: define safe opening stock costs, purchase-lot valuation or weighted average, cost-at-sale snapshot, return-cost treatment and a properly labeled gross-profit report. Never treat recorded purchase costs alone or sales minus expenses as net profit.
5. Improve POS customer lookup selection/search, customer history paging, and outstanding report paging; fix gaps without removing old UI.
6. Test receipt and 58mm Bluetooth integration on actual supported hardware (BLE vs classic SPP vs browser/platform compatibility). Do not claim universal Web Bluetooth or actual print success based only on simulation.
7. Document route capacity as <=550 packs per truck only after validating units/weights/vehicle capacity and delivery constraints.
8. Review LINE webhook security and duplicate event handling before turning on real customer auto-orders.

## Mandatory working rules
- Keep changes isolated to `feature/flow-loyverse-additions-20261112` or a fresh child feature branch; **never modify main**, never auto-merge.
- Test-driven development: failing regression test first, implement, then run entire test suite.
- Inspect models/migrations and backup/restore strategy before any schema changes.
- Use synthetic data and disposable DB only; do not migrate, overwrite, or touch real production data.
- Render: inspect service, database, existing deployment and backups first. Deploy **staging only after all tests pass and staging is isolated from production**. Do not deploy production without separate authorization.
- Never copy proprietary FlowAccount/Loyverse code/UI/assets. Use them only as functional references.
- Explicitly separate tax-document drafts from legally usable Thai tax invoices, and request accountant verification before real issuance.
- For each work batch report: changed files/commit, tests and CI URLs, migrations, staging URL if actually deployed, blockers, and what's still missing.
- Do not promise that a feature is ready if only an API exists without usable UI/e2e verification.

## Commands and test expectations
```sh
ruff check erp tests migrations
ruff format --check erp tests migrations
flask --app erp db upgrade
flask --app erp db check
python -m pytest -q
PYTHONPATH=. python tests/ui_smoke.py
```
Read `requirements.txt`, `.github/workflows/tests.yml`, `tests/conftest.py`, `render.yaml`, and `PRODUCTION_READINESS.md` before running anything. Tests erase TEST_DATABASE_URL; it **must** point to a disposable database with a name ending in `_test`. Never point it at DATABASE_URL / production.

## Acceptance criteria for next batch
- Existing CI remains green and no historical business data is modified.
- New behavior is accessible via role-appropriate UI and protected API.
- Idempotency, Decimal currency/VAT, isolation, authorization, auditability, and rollback safety are covered by tests.
- Deployment remains staging-only until separately reviewed.


## Continuation: cost evidence and financial credit drafts (2026-11-12 evening)

**Implemented in feature branch, not deployed**:

- `erp/cost_evidence.py` + `tests/test_cost_evidence.py` + Reports UI: accountant-only, read-only purchase receipt cost evidence, stock-movement reconciliation, pagination. Critically returns `null` for COGS and gross profit until an audited opening valuation and per-sale costs exist. Contract in `COST_EVIDENCE.md`. No migration for cost evidence. Fully green CI at commit `500c993d41572ee70e0433361b6c9a4c33871d26`, run https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43242672847 .
- `erp/credit_note_drafts.py`, `erp/templates/credit_note_draft_print.html`, migration `bd8c1a770e21_credit_note_drafts.py`, `tests/test_credit_note_drafts.py` and mobile browser flow: financial credit-review drafts bound to received physical returns; accountant-only, idempotent, immutable sale/buyer/return snapshots, per-sale monetary cap, explicit void history, read/print. No adjustment to sale/payment/stock/tax documents. Fully green CI at commit `d28eee764a42fccd309d3af8e2b196636e11bd43`, run https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43245122676 . Contract in `CREDIT_NOTE_DRAFTS.md`. **Not an issued Thai tax credit note**.
- `erp/receivables_report.py` and Reports UI: pagination and literal search escaping, preserving grand total across all pages. Extra regression test in `tests/test_receivables_report.py`. Fully green CI at commit `630a810f31e30520a92d3cee00cf0f6d4b60646e`, run https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43245853537 .
- `RELEASE_GATES_2026-11-12.md` captures current Render staging branch and Postgres expiry, missing restore verification, and health uncertainty. No deployment was made.

**Audited existing features, do not duplicate**:

- LINE webhook in `erp/operations.py` verifies LINE HMAC, filters approved users/groups, deduplicates webhook event IDs, and creates review-only order drafts; only sales staff can accept via the existing stock-locked order code. Existing `tests/test_operations.py` covers bad signature, duplicate ID, permissions and insufficient stock. It is **not** active natural-language auto-ordering or capacity-aware route optimization; real LINE configuration and callbacks remain unverified.
- Existing 58 mm BLE UI uses user-provided GATT service/write UUID and ESC/POS raster transport in `erp/static/online/printer.js`. Mobile tests use fake BLE. Real printer compatibility, Thai glyphs, USB/A4 and mobile Bluetooth capabilities must be checked with actual devices.
- Existing Render staging remains on older branch `feature/thanabunyapat-online`; Render service live config has autoDeploy enabled even though repository `render.yaml` has it off. Postgres Free expires 2026-12-06; backup restoration and dedicated DB isolation unverified. **Do not deploy, migrate, test against existing Render data or touch main.**

**Priorities still open**:

1. Operator-reviewed opening cost valuation, explicit cost policy, cost-at-sale immutable snapshots, returns and adjustments, and fully reconciled COGS/gross profit. Do not present read-only purchase evidence as completed COGS.
2. Legal-accounting review before tax credit-note issuance, refund/receivable adjustment; financial drafts are not posted.
3. Customer-history UI pagination, ageing/due-date modeling, report filters and financial export.
4. Capacity-safe LINE route planning with verified pack/weight/unit semantics and delivery coordinates; real LINE webhook test.
5. Real BLE 58 mm and A4 printer tests on supported devices; browser simulation alone is insufficient.
6. Separate disposable staging DB, proven backup/restore, branch alignment and verified Render health before staging deploy. No production deployment.

Final CI must be checked against the final branch HEAD after any documentation commit; never use an older green run to claim the current HEAD passed.
