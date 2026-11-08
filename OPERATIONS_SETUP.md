# Operations extension

Staging branch only. Never put SMTP credentials, LINE secrets, or evidence in git.

## Available in the workspace

After login open **รายสัปดาห์ / ค่าแรง / หลักฐาน** in the sidebar.

- Email: each active user can verify their own address after re-entering their current password. The signed link expires in 30 minutes, becomes invalid when changed/resubmitted, and is single-use. Only active owners can subscribe to company-wide weekly financial/payroll reports.
- Wages: an owner/accountant records actual workdays, completed delivery rounds, advances, bonuses and reimbursements. Rates are snapshotted into the entries. A delivery must be completed and assigned to the named driver. Each delivery and expense can be counted only once. Duplicate workdays are rejected. This is a weekly calculation, not a paid payroll register or a carried-forward advance ledger. It excludes withholding and social security. Negative balances need human review.
- Evidence: JPEG/PNG up to 3 MB and 16 megapixels. Images are decoded and re-encoded to remove metadata. Stored privately in PostgreSQL so redeploys do not erase them; download requires a current authorized session. Total staging budget 100 MB; production scale requires private object storage and retention/backup policies. Submitted slips stay pending until reviewed; reviewing never changes the sale balance. Record verified money separately in Receive Payment.
- LINE: approved sender user IDs are mapped to an existing customer. Group messages additionally require the mapped group ID. Direct messages are accepted from the same mapped sender. Format `ORDER SKU:quantity SKU:quantity`. The inbox deduplicates `webhookEventId`, never stores unrelated chat text, and does not reserve stock. A sales user reviews address, phone, driver, delivery date and current catalog prices before accepting. Acceptance creates a credit wholesale sale using existing stock row locks and an idempotency key. Rejected/disabled senders cannot create accepted orders. Ordinary natural-language chat, image orders and automatic price negotiation are unsupported.

## Email configuration (Render Environment, secret fields)

Render free services block SMTP ports 25/465/587. Prefer Resend over HTTPS: set `RESEND_API_KEY`, `MAIL_FROM` (verified domain sender), and `PUBLIC_BASE_URL`. The client sends an idempotency key, uses verified TLS and only the fixed official API endpoint. Provider keys must be sending-only and restricted to the verified domain. The SMTP alternative below is for hosts/plans where those ports are available.

- `PUBLIC_BASE_URL`: HTTPS staging origin without a trailing slash
- `SMTP_HOST`, `SMTP_PORT` (465 implicit TLS or provider STARTTLS port), `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`

Use the provider's authenticated sender/domain. No cleartext fallback. Do not paste secrets into chat. The UI reports a missing provider honestly; no outgoing emails are sent until configured. An actual provider delivery test remains necessary.

## Weekly scheduler

Run `flask --app erp send-weekly-reports` every Monday 09:00 Asia/Bangkok (02:00 UTC). Alternatively an authenticated scheduler can POST `/internal/weekly-report` with `Authorization: Bearer <REPORT_JOB_SECRET>`, with a random secret of at least 32 characters stored on both sides. Cron expression in UTC: `0 2 * * 1`.

No paid cron service is provisioned automatically. A web process's timer is not reliable on a sleeping free Render instance. The job sends the last completed Monday–Sunday Bangkok week and reserves a unique contact/week before sending. `sending` or `needs_review` is an ambiguous outcome: inspect the provider before retrying manually; there is no automatic resend. Successful records are `sent`. Disabled/unverified/non-owner accounts never receive financial reports. Job times and provider acceptance do not guarantee inbox delivery. An external scheduler must be enabled and tested before advertising automatic reports as active.

## LINE Official Account configuration

In LINE Developers configure the Messaging API webhook at `/integrations/line/webhook` on the HTTPS app origin; set `LINE_CHANNEL_SECRET` in Render, enable webhooks and enable the bot to join groups if needed. Invite the Official Account to the target group. Obtain user/group IDs through the official channel's verified webhook tooling; do not use a display name as an ID. The application verifies HMAC-SHA256 over the exact raw body. No outbound LINE replies or group financial broadcasts are enabled. An actual LINE event test is required after connecting the channel.

## Validation and release

Run ruff, the full test suite on a disposable PostgreSQL database ending `_test`, upgrade/downgrade/upgrade and Alembic drift checks. Test forbidden roles, missing CSRF, email replay, webhook signature and duplicates, stock rollback, wage double counting and evidence access. Production rollout, statutory accounting/tax reports, payroll disbursement, automated slip/bank verification and outbound LINE notifications are outside this extension.
