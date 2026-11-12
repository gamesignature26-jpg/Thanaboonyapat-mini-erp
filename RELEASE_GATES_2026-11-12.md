# Staging release gates — Thanabunyapat Mini ERP

As reviewed 2026-11-12 (Asia/Bangkok):

- Target feature branch: `feature/flow-loyverse-additions-20261112`. Production `main` was not changed.
- Render workspace: `Gamesignature26's workspace` / `tea-dbkua1lg1s2s73dpnr6g`.
- Existing staging service: `thanabunyapat-erp-staging-c8km` / `srv-dbn9e6rrjlhs7384fq1g`.
- Service is connected to older `feature/thanabunyapat-online`, has `autoDeploy: yes` in Render's live configuration, and starts by running migrations. Repository `render.yaml` says `autoDeployTrigger: off`, so do not assume repository YAML matches live service.
- The last reported live deploy `dep-dbqagg08o4fc73d54ngg` came from older commit `5766df4e543a7c958c0c15a69829e83f756e1a8a`. Render event history also contains `server_failed` (nonzero exit), so deploy status **does not prove a healthy persistent server**.
- Existing Postgres: `thanabunyapat-erp-test` / `dpg-dbn2rn3ncjis73e0gcp0-a`, database name `thanabunyapat_test`, Free plan, expires 2026-12-06. A reliable separate staging database and successful restore rehearsal have **not** been established.
- No new deployment, no Render environment-variable changes, no database migration or data-test against Render is authorized until these gates pass. Physical printer testing is also pending.

## Before any staging deploy

1. Confirm the correct target service, branch, safety of auto-deploy and non-production exposure.
2. Provision or positively verify a **dedicated disposable staging Postgres** with no production-data connection. No test command may target the Render existing DB unless positively demonstrated disposable, isolated, and backed up.
3. Take an encrypted backup and prove recovery by restoring to a different isolated database. Verify tables, row counts and schema before any new migration.
4. Run local and CI lint, formatter, migration upgrade/check/downgrade/upgrade on a test-only DB, PostgreSQL tests and mobile Playwright. Never run downgrade on existing staging data.
5. Check actual Render health and readiness from the deployed branch; verify login, mock customer flows, and migration version. Actual A4 and BLE receipt tests require printer hardware.
6. Obtain accountant review for tax-document and COGS policies before any legal production use.

**Decision:** HOLD staging and production deploy. The existence of a Render URL alone is not successful URL verification. No claim of a new feature being deployed is permitted.
