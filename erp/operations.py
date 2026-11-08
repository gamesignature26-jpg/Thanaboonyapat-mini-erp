"""Operations tools. External delivery is disabled until credentials are configured."""

import base64
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import smtplib
import ssl
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from email.message import EmailMessage
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import click
from flask import abort, current_app, g, request, send_file
from itsdangerous import BadSignature, URLSafeTimedSerializer
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func
from werkzeug.security import check_password_hash

from . import data, integer, money, roles, text
from .models import Customer, Payment, Product, Sale, User, db
from .online import OnlineExpense, OnlineOrder, create_order, money_json, parse_day
from .operations_models import Driver, DriverEntry, EmailContact, Evidence, LineDraft, LineSender, ReportDelivery

TZ = ZoneInfo("Asia/Bangkok")


def setting(name):
    return current_app.config.get(name, os.getenv(name, ""))


def origin():
    value = setting("PUBLIC_BASE_URL").rstrip("/")
    if not value.startswith("https://"):
        abort(503, "PUBLIC_BASE_URL must be configured with HTTPS")
    return value


def mail_ready():
    return bool(setting("PUBLIC_BASE_URL")) and (
        bool(setting("RESEND_API_KEY") and setting("MAIL_FROM"))
        or all(setting(k) for k in ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM"))
    )


def send_mail(address, subject, content):
    if not mail_ready():
        abort(503, "Email provider is not configured")
    if setting("RESEND_API_KEY"):
        payload = json.dumps(
            {"from": setting("MAIL_FROM"), "to": [address], "subject": subject, "text": content}
        ).encode()
        req = Request(
            "https://api.resend.com/emails",
            data=payload,
            headers={
                "Authorization": "Bearer " + setting("RESEND_API_KEY"),
                "Content-Type": "application/json",
                "Idempotency-Key": hashlib.sha256(payload).hexdigest(),
            },
            method="POST",
        )
        with urlopen(req, timeout=15, context=ssl.create_default_context()) as response:
            result = json.loads(response.read(65536))
        if not isinstance(result, dict) or not result.get("id"):
            raise OSError("Email provider did not acknowledge the request")
        return
    message = EmailMessage()
    message["From"] = setting("SMTP_FROM")
    message["To"] = address
    message["Subject"] = subject
    message.set_content(content)
    # No plaintext fallback; use authenticated TLS on the configured mail host.
    port = int(setting("SMTP_PORT") or "465")
    context = ssl.create_default_context()
    if port == 465:
        connection = smtplib.SMTP_SSL(setting("SMTP_HOST"), port, timeout=15, context=context)
    else:
        connection = smtplib.SMTP(setting("SMTP_HOST"), port, timeout=15)
        connection.starttls(context=context)
    with connection as smtp:
        smtp.login(setting("SMTP_USERNAME"), setting("SMTP_PASSWORD"))
        smtp.send_message(message)


def week_bounds(value=None):
    day = parse_day(value) if value else datetime.now(TZ).date()
    monday = day - timedelta(days=day.weekday())
    start = datetime.combine(monday, time.min, TZ).astimezone(UTC)
    return monday, start, start + timedelta(days=7)


def weekly_report(value=None):
    monday, start, end = week_bounds(value)

    def total(model, column):
        return money_json(
            db.session.scalar(db.select(func.sum(column)).where(model.created_at >= start, model.created_at < end)) or 0
        )

    return {
        "week": monday.isoformat(),
        "end_exclusive": (monday + timedelta(days=7)).isoformat(),
        "sales_including_vat": total(Sale, Sale.total),
        "payments_received": total(Payment, Payment.amount),
        "expenses": total(OnlineExpense, OnlineExpense.amount),
        "pending_delivery": db.session.scalar(
            db.select(func.count())
            .select_from(OnlineOrder)
            .where(OnlineOrder.delivery_mode == "delivery", OnlineOrder.delivery_status != "delivered")
        )
        or 0,
        "payroll": payroll(monday, monday + timedelta(days=7)),
        "note": "ยอดขายรวม VAT; เงินรับอาจเป็นหนี้เก่า; ไม่ใช่กำไรสุทธิ ค่าแรงก่อนภาษี/ประกันสังคม",
    }


def payroll(start, end):
    result = []
    for driver in db.session.scalars(db.select(Driver).order_by(Driver.id)):
        amounts = dict(
            db.session.execute(
                db.select(DriverEntry.kind, func.sum(DriverEntry.amount))
                .where(DriverEntry.driver_id == driver.id, DriverEntry.day >= start, DriverEntry.day < end)
                .group_by(DriverEntry.kind)
            ).all()
        )
        gross = sum((amounts.get(k, Decimal(0)) for k in ("day", "delivery", "bonus")), Decimal(0))
        reimburse = amounts.get("reimburse", Decimal(0))
        advances = amounts.get("advance", Decimal(0))
        result.append(
            {
                "driver_id": driver.id,
                "name": driver.name,
                "gross_wages": money_json(gross),
                "reimbursement": money_json(reimburse),
                "advances": money_json(advances),
                "net_payable": money_json(gross + reimburse - advances),
            }
        )
    return result


def deliver_weekly(value=None):
    # Default is the last completed Bangkok calendar week, never a rolling 7-day window.
    day = value or (datetime.now(TZ).date() - timedelta(days=7)).isoformat()
    report = weekly_report(day)
    monday = date.fromisoformat(report["week"])
    sent = 0
    contacts = list(
        db.session.scalars(
            db.select(EmailContact)
            .join(User, User.id == EmailContact.user_id)
            .where(
                EmailContact.verified.is_(True),
                EmailContact.weekly.is_(True),
                User.active.is_(True),
                User.role == "admin",
            )
        )
    )
    if contacts and not mail_ready():
        abort(503, "Email provider is not configured")
    for contact in contacts:
        # Commit reservation before external send. An ambiguous failure must be reviewed,
        # not automatically resent and potentially duplicated.
        db.session.get(EmailContact, contact.id, with_for_update=True)
        if db.session.scalar(
            db.select(ReportDelivery.id).where(ReportDelivery.week == monday, ReportDelivery.contact_id == contact.id)
        ):
            db.session.rollback()
            continue
        delivery = ReportDelivery(week=monday, contact_id=contact.id, status="sending")
        db.session.add(delivery)
        db.session.commit()
        try:
            lines = [
                f"รายงานธนาบุณยภัทร สัปดาห์เริ่ม {report['week']}",
                f"ยอดขายรวม VAT: {report['sales_including_vat']} บาท",
                f"รับชำระเงินจริง: {report['payments_received']} บาท",
                f"รายจ่ายที่บันทึก: {report['expenses']} บาท",
                f"ออเดอร์รอส่งทั้งหมด: {report['pending_delivery']}",
                "",
                "สรุปค่าแรงขนส่ง (ก่อนภาษีและประกันสังคม)",
            ]
            for p in report["payroll"]:
                lines.append(
                    f"{p['name']}: ค่าแรง {p['gross_wages']} + คืนค่าใช้จ่าย {p['reimbursement']} - เบิกแล้ว {p['advances']} = คงจ่าย {p['net_payable']} บาท"
                )
            lines.extend(
                [
                    "",
                    report["note"],
                    "ยอดค่าแรงเฉพาะสัปดาห์นี้ ไม่ใช่ยอดยกมาหรือหลักฐานจ่ายเงินจริง",
                    origin() + "/app",
                    "หยุดรับรายงานได้ที่ อีเมลของฉัน > หยุดรับรายงานรายสัปดาห์",
                ]
            )
            send_mail(contact.email, f"ธนาบุณยภัทร รายงานสัปดาห์ {monday}", "\n".join(lines))
        except (OSError, smtplib.SMTPException):
            delivery.status = "needs_review"
        else:
            delivery.status = "sent"
            sent += 1
        db.session.commit()
    return {"sent": sent, "week": monday.isoformat()}


def install_operations(app):
    limiter = app.extensions["erp_limiter"]
    signer = URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="email-verification-v1")

    @app.get("/api/operations/status")
    @roles()
    def integration_status():
        return {
            "email_configured": bool(mail_ready()),
            "line_configured": bool(setting("LINE_CHANNEL_SECRET")),
            "scheduler_configured": bool(setting("REPORT_JOB_SECRET")),
            "report_schedule": "วันจันทร์ 09:00 เวลาไทย — ต้องเปิด scheduler",
            "attachment_limit_mb": 3,
        }

    @app.route("/api/operations/email", methods=["GET", "POST"])
    @roles("sales", "warehouse", "accountant")
    @limiter.limit("5 per hour", methods=["POST"])
    def email_contact():
        contact = db.session.scalar(db.select(EmailContact).where(EmailContact.user_id == g.user.id))
        if request.method == "GET":
            return {
                "email": contact.email if contact else "",
                "verified": bool(contact and contact.verified),
                "weekly": bool(contact and contact.weekly),
            }
        body = data()
        address = text(body, "email", 254).lower()
        if not re.fullmatch(r"[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+", address):
            abort(400, "Invalid email")
        if not check_password_hash(g.user.password_hash, text(body, "current_password", 128)):
            abort(403, "Current password required")
        weekly = body.get("weekly", False)
        if type(weekly) is not bool or (weekly and g.user.role != "admin"):
            abort(403, "Weekly financial reports are owner-only")
        if not mail_ready():
            abort(503, "Email provider is not configured")
        nonce = secrets.token_urlsafe(32)
        if not contact:
            contact = EmailContact(user_id=g.user.id)
            db.session.add(contact)
        contact.email, contact.verified, contact.weekly = address, False, weekly
        contact.nonce_hash = hashlib.sha256(nonce.encode()).hexdigest()
        db.session.flush()
        token = signer.dumps({"uid": g.user.id, "email": address, "nonce": nonce})
        link = origin() + "/app#verify-email=" + token
        try:
            send_mail(address, "ยืนยันอีเมล ธนาบุณยภัทร", "กดยืนยันภายใน 30 นาที ใช้ได้ครั้งเดียว:\n" + link)
        except (OSError, smtplib.SMTPException):
            db.session.rollback()
            abort(502, "Email delivery failed; address was not changed")
        db.session.commit()
        return {"message": "Verification email sent"}, 202

    @app.post("/auth/verify-email")
    @limiter.limit("10 per minute")
    def verify_email():
        try:
            payload = signer.loads(text(data(), "token", 2000), max_age=1800)
        except BadSignature:
            abort(400, "Expired or invalid verification link")
        contact = db.session.scalar(
            db.select(EmailContact).where(EmailContact.user_id == payload.get("uid")).with_for_update()
        )
        if (
            not contact
            or contact.verified
            or contact.email != payload.get("email")
            or not hmac.compare_digest(
                contact.nonce_hash, hashlib.sha256(str(payload.get("nonce", "")).encode()).hexdigest()
            )
        ):
            abort(400, "Expired or used verification link")
        contact.verified = True
        db.session.commit()
        return {"verified": True}

    @app.post("/api/operations/email/unsubscribe")
    @roles()
    def unsubscribe():
        contact = db.session.scalar(db.select(EmailContact).where(EmailContact.user_id == g.user.id).with_for_update())
        if contact:
            contact.weekly = False
            db.session.commit()
        return {"weekly": False}

    @app.get("/api/operations/weekly")
    @roles("accountant")
    def get_weekly():
        return weekly_report(request.args.get("week"))

    @app.get("/api/operations/report-deliveries")
    @roles()
    def report_deliveries():
        rows = db.session.scalars(db.select(ReportDelivery).order_by(ReportDelivery.id.desc()).limit(50))
        return {"items": [{"id": r.id, "week": r.week.isoformat(), "status": r.status} for r in rows]}

    @app.post("/internal/weekly-report")
    @app.extensions["csrf"].exempt
    @limiter.limit("5 per hour")
    def weekly_job():
        key = setting("REPORT_JOB_SECRET")
        if len(key) < 32 or not hmac.compare_digest(request.headers.get("Authorization", ""), "Bearer " + key):
            abort(403)
        return deliver_weekly()

    @app.cli.command("send-weekly-reports")
    def weekly_command():
        click.echo(json.dumps(deliver_weekly()))

    @app.route("/api/operations/drivers", methods=["GET", "POST"])
    @roles("accountant")
    def drivers():
        if request.method == "POST":
            body = data()
            driver = Driver(
                name=text(body, "name", 100),
                daily_rate=money(body.get("daily_rate")),
                delivery_rate=money(body.get("delivery_rate")),
            )
            db.session.add(driver)
            db.session.commit()
            return {"id": driver.id}, 201
        return {
            "items": [
                {
                    "id": d.id,
                    "name": d.name,
                    "daily_rate": money_json(d.daily_rate),
                    "delivery_rate": money_json(d.delivery_rate),
                }
                for d in db.session.scalars(db.select(Driver).order_by(Driver.id))
            ]
        }

    @app.route("/api/operations/driver-entries", methods=["GET", "POST"])
    @roles("accountant")
    def entries():
        if request.method == "GET":
            monday, _, _ = week_bounds(request.args.get("week"))
            rows = db.session.scalars(
                db.select(DriverEntry)
                .where(DriverEntry.day >= monday, DriverEntry.day < monday + timedelta(days=7))
                .order_by(DriverEntry.day, DriverEntry.id)
            )
            return {
                "items": [
                    {
                        "id": e.id,
                        "driver_id": e.driver_id,
                        "day": e.day.isoformat(),
                        "kind": e.kind,
                        "amount": money_json(e.amount),
                        "note": e.note,
                    }
                    for e in rows
                ]
            }
        body = data()
        driver = db.session.get(Driver, integer(body.get("driver_id")), with_for_update=True)
        if not driver:
            abort(404)
        day = parse_day(body.get("day"))
        if not day or day > datetime.now(TZ).date():
            abort(400, "Actual work/advance date is required; no future entries")
        kind = text(body, "kind", 20)
        if kind not in ("day", "delivery", "advance", "reimburse", "bonus"):
            abort(400, "Invalid entry kind")
        key = text(body, "request_key", 80)
        if len(key) < 16:
            abort(400, "Request key too short")
        if db.session.scalar(db.select(DriverEntry.id).where(DriverEntry.request_key == key)):
            abort(409, "Entry already recorded")
        amount = money(body.get("amount", "0.00"))
        sale_id, expense_id = None, None
        if kind == "day":
            if db.session.scalar(
                db.select(DriverEntry.id).where(
                    DriverEntry.driver_id == driver.id, DriverEntry.day == day, DriverEntry.kind == "day"
                )
            ):
                abort(409, "Work day already recorded")
            amount = driver.daily_rate
        if kind == "delivery":
            sale_id = integer(body.get("sale_id"))
            order = db.session.scalar(db.select(OnlineOrder).where(OnlineOrder.sale_id == sale_id).with_for_update())
            if (
                not order
                or order.delivery_mode != "delivery"
                or order.delivery_status != "delivered"
                or order.driver != driver.name
            ):
                abort(409, "Delivery must be completed and assigned to this driver")
            amount = driver.delivery_rate
        if kind == "reimburse":
            expense_id = integer(body.get("expense_id"))
            expense = db.session.get(OnlineExpense, expense_id, with_for_update=True)
            if not expense:
                abort(404)
            amount = expense.amount
        if amount <= 0:
            abort(400, "Amount must be positive")
        entry = DriverEntry(
            driver_id=driver.id,
            day=day,
            kind=kind,
            amount=amount,
            note=text(body, "note", 250),
            sale_id=sale_id,
            expense_id=expense_id,
            request_key=key,
            actor_id=g.user.id,
        )
        db.session.add(entry)
        db.session.commit()
        return {"id": entry.id, "amount": money_json(amount)}, 201

    @app.route("/api/operations/evidence", methods=["GET", "POST"])
    @roles("sales", "accountant")
    @limiter.limit("30 per hour", methods=["POST"])
    def evidence():
        if request.method == "GET":
            query = db.select(Evidence).order_by(Evidence.id.desc())
            if g.user.role == "sales":
                query = query.where(Evidence.actor_id == g.user.id)
            return {
                "items": [
                    {
                        "id": e.id,
                        "sale_id": e.sale_id,
                        "expense_id": e.expense_id,
                        "status": e.status,
                        "created_at": e.created_at.isoformat(),
                    }
                    for e in db.session.scalars(query.limit(100))
                ]
            }
        sale_id = request.form.get("sale_id", type=int)
        expense_id = request.form.get("expense_id", type=int)
        if bool(sale_id) == bool(expense_id):
            abort(400, "Choose one sale or expense")
        if expense_id and g.user.role not in ("admin", "accountant"):
            abort(403)
        if sale_id:
            db.get_or_404(Sale, sale_id)
        else:
            db.get_or_404(OnlineExpense, expense_id)
        upload = request.files.get("file")
        if not upload:
            abort(400, "Image required")
        raw = upload.read(3 * 1024 * 1024 + 1)
        if len(raw) > 3 * 1024 * 1024 or not raw:
            abort(413, "Image must be no more than 3 MB")
        # Validate bytes, not client extensions. Re-encode to remove EXIF/location
        # and appended executable payloads; download only, never inline.
        try:
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG") or image.width * image.height > 16000000:
                    abort(400, "Only JPEG/PNG up to 16 megapixels are accepted")
                image.load()
                clean = io.BytesIO()
                image.convert("RGB").save(clean, format="JPEG", quality=90)
                raw = clean.getvalue()
        except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
            abort(400, "Invalid image")
        if len(raw) > 3 * 1024 * 1024:
            abort(413, "Processed image exceeds 3 MB; resize and retry")
        media = "image/jpeg"
        digest = hashlib.sha256(raw).hexdigest()
        if db.session.scalar(db.select(Evidence.id).where(Evidence.digest == digest)):
            abort(409, "Image already submitted; review existing evidence")
        # Keep the small staging database bounded. Move to private object storage before scale-up.
        used = db.session.scalar(db.select(func.sum(func.length(Evidence.content)))) or 0
        if used + len(raw) > 100 * 1024 * 1024:
            abort(507, "Evidence storage limit reached; contact the owner")
        row = Evidence(
            sale_id=sale_id, expense_id=expense_id, actor_id=g.user.id, content=raw, media_type=media, digest=digest
        )
        db.session.add(row)
        db.session.commit()
        return {"id": row.id, "status": "pending", "message": "Evidence does not confirm payment"}, 201

    @app.get("/api/operations/evidence/<int:evidence_id>")
    @roles("sales", "accountant")
    def download_evidence(evidence_id):
        row = db.get_or_404(Evidence, evidence_id)
        if g.user.role == "sales" and row.actor_id != g.user.id:
            abort(403)
        suffix = "png" if row.media_type == "image/png" else "jpg"
        return send_file(
            io.BytesIO(row.content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"evidence-{row.id}.{suffix}",
            max_age=0,
        )

    @app.post("/api/operations/evidence/<int:evidence_id>/review")
    @roles("accountant")
    def review_evidence(evidence_id):
        row = db.session.get(Evidence, evidence_id, with_for_update=True)
        if not row:
            abort(404)
        if row.status != "pending":
            abort(409, "Evidence already reviewed")
        status = data().get("status")
        if status not in ("accepted", "rejected"):
            abort(400)
        row.status, row.reviewer_id = status, g.user.id
        db.session.commit()
        return {"status": status, "message": "Record verified transfer separately in Receive Payment"}

    @app.route("/api/operations/line-senders", methods=["GET", "POST"])
    @roles()
    def line_senders():
        if request.method == "POST":
            body = data()
            customer_id = integer(body.get("customer_id"))
            db.get_or_404(Customer, customer_id)
            sender = LineSender(
                line_user_id=text(body, "line_user_id", 100),
                customer_id=customer_id,
                group_id=str(body.get("group_id", ""))[:100],
            )
            db.session.add(sender)
            db.session.commit()
            return {"id": sender.id}, 201
        return {
            "items": [
                {
                    "id": s.id,
                    "customer_id": s.customer_id,
                    "line_user_id": s.line_user_id,
                    "group_id": s.group_id,
                    "enabled": s.enabled,
                }
                for s in db.session.scalars(db.select(LineSender))
            ]
        }

    @app.post("/api/operations/line-senders/<int:sender_id>/disable")
    @roles()
    def disable_sender(sender_id):
        sender = db.get_or_404(LineSender, sender_id)
        sender.enabled = False
        db.session.commit()
        return {"enabled": False}

    @app.post("/integrations/line/webhook")
    @app.extensions["csrf"].exempt
    @limiter.limit("120 per minute")
    def line_webhook():
        secret = setting("LINE_CHANNEL_SECRET")
        if not secret:
            abort(503, "LINE is not configured")
        raw = request.get_data()
        if len(raw) > 65536:
            abort(413)
        expected = base64.b64encode(hmac.new(secret.encode(), raw, hashlib.sha256).digest()).decode()
        if not hmac.compare_digest(expected, request.headers.get("X-Line-Signature", "")):
            abort(403)
        try:
            payload = json.loads(raw)
        except ValueError:
            abort(400)
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list) or len(payload["events"]) > 100:
            abort(400)
        for event in payload["events"]:
            if not isinstance(event, dict) or event.get("type") != "message":
                continue
            source, message = event.get("source", {}), event.get("message", {})
            if not isinstance(source, dict) or not isinstance(message, dict):
                continue
            eid = event.get("webhookEventId")
            if not isinstance(eid, str) or not 1 <= len(eid) <= 100:
                continue
            sender = db.session.scalar(
                db.select(LineSender)
                .where(LineSender.line_user_id == source.get("userId"), LineSender.enabled.is_(True))
                .with_for_update()
            )
            if (
                not sender
                or (source.get("type") == "group" and (not sender.group_id or sender.group_id != source.get("groupId")))
                or source.get("type") not in ("user", "group")
            ):
                continue
            if db.session.scalar(db.select(LineDraft.id).where(LineDraft.event_id == eid)):
                continue
            value = message.get("text", "")
            if (
                message.get("type") != "text"
                or not isinstance(value, str)
                or len(value) > 2000
                or not value.startswith("ORDER ")
            ):
                continue
            lines = []
            for part in value[6:].split():
                match = re.fullmatch(r"([\w.-]{1,80}):([1-9][0-9]{0,4})", part)
                if not match:
                    lines = []
                    break
                product = db.session.scalar(db.select(Product).where(Product.sku == match[1]))
                if not product or any(x["product_id"] == product.id for x in lines):
                    lines = []
                    break
                lines.append({"product_id": product.id, "quantity": int(match[2])})
            if 1 <= len(lines) <= 100:
                db.session.add(
                    LineDraft(
                        event_id=eid, sender_id=sender.id, customer_id=sender.customer_id, lines=json.dumps(lines)
                    )
                )
        db.session.commit()
        return {"received": True}

    @app.get("/api/operations/line-drafts")
    @roles("sales")
    def line_drafts():
        return {
            "items": [
                {
                    "id": d.id,
                    "customer_id": d.customer_id,
                    "lines": json.loads(d.lines),
                    "status": d.status,
                    "sale_id": d.sale_id,
                }
                for d in db.session.scalars(db.select(LineDraft).order_by(LineDraft.id.desc()).limit(100))
            ]
        }

    @app.post("/api/operations/line-drafts/<int:draft_id>/accept")
    @roles("sales")
    def accept_draft(draft_id):
        draft = db.session.get(LineDraft, draft_id, with_for_update=True)
        if not draft or draft.status != "pending":
            abort(409, "Draft already handled or missing")
        sender = db.session.get(LineSender, draft.sender_id)
        if not sender or not sender.enabled:
            abort(409, "Sender disabled")
        body = data()
        lines = json.loads(draft.lines)
        for line in lines:
            product = db.get_or_404(Product, line["product_id"])
            line["unit_price"] = money_json(product.price)
        order_body = {
            "kind": "wholesale",
            "customer_id": draft.customer_id,
            "lines": lines,
            "method": "credit",
            "delivery_mode": "delivery",
            "address": text(body, "address", 1000),
            "phone": text(body, "phone", 30),
            "driver": text(body, "driver", 100),
            "delivery_date": text(body, "delivery_date", 10),
            "idempotency_key": f"line-draft-order-{draft.id:016d}",
        }
        # Reuse the existing stock-locking and idempotent order service. Mark the
        # inbox row in that same transaction so failure leaves the draft pending.
        draft.status = "accepted"

        def link_sale(sale):
            draft.sale_id = sale.id

        result, status = create_order(order_body, link_sale)
        return result, status

    @app.post("/api/operations/line-drafts/<int:draft_id>/reject")
    @roles("sales")
    def reject_draft(draft_id):
        draft = db.session.get(LineDraft, draft_id, with_for_update=True)
        if not draft or draft.status != "pending":
            abort(409)
        draft.status = "rejected"
        db.session.commit()
        return {"status": "rejected"}
