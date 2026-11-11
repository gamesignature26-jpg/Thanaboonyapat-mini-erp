# ChatGPT Work Handoff — Thanabunyapat Mini ERP
Updated: 2026-11-12 (Asia/Bangkok)

## Source of truth
- Repo: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp
- Current development branch: `feature/flow-loyverse-additions-20261112`
- Last fully validated code commit (prior to docs and cleanup): `91ad03407ebf15d361058578c2a050acd89b1288`
- Passing GitHub Actions (code + browser): https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp/actions/runs/43083722162
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
- Next: real versioned quote revisions and external customer approval; formal multi-sale billing note workflow; return/credit-note drafts; supplier purchasing, receiving and COGS. Do not confuse the new billing preview with a formal billing note.

## Immediate next work (in priority order)
1. Re-audit actual routes, models, templates, JS and tests to prevent duplicate features and identify incomplete implementations.
2. Review the new **staff-recorded** quote acceptance and conversion code (already implemented) and add formal quote revisions/customer acceptance evidence and multi-sale billing-note issuance only after document/business rules are approved. Never bypass stock/price checks when converting a quote. Do **not** misuse `IssuedDocument` tax invoice/receipt semantics. Draft numbers must be separate from legally issued document numbers. New states must have explicit validation, auth and immutable snapshots where appropriate.
3. Implement return/credit-note *draft* workflow, including safe stock-reversal design. Do not create or issue legally valid tax credit notes without verified Thai tax/accounting requirements and explicit review.
4. Add purchasing/suppliers, stock receiving, cost/COGS support and per-order gross margin when data model permits. Never label sales minus recorded expenses as net profit.
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
