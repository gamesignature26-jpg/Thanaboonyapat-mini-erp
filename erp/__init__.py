import hashlib
import os
import secrets
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from functools import wraps

import click
from flask import Flask, abort, g, jsonify, request, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect, generate_csrf
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

from .models import Customer, Payment, Product, Sale, SaleLine, StockMovement, User, db
from .readiness import database_is_ready

ROLES = ("admin", "sales", "warehouse", "accountant")
CENT = Decimal("0.01")


def money(value):
    if not isinstance(value, str) or len(value) > 20:
        abort(400, "Money must be a decimal string")
    try:
        result = Decimal(value)
        if not result.is_finite() or result < 0 or result > Decimal("999999999.99"):
            raise ValueError
        if result != result.quantize(CENT):
            raise ValueError
        return result.quantize(CENT)
    except (InvalidOperation, ValueError):
        abort(400, "Invalid money")


def data():
    if request.content_length and request.content_length > 65536:
        abort(413)
    body = request.get_json()
    if not isinstance(body, dict):
        abort(400, "Expected JSON object")
    return body


def text(body, key, maximum=200):
    value = body.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        abort(400, f"Invalid {key}")
    return value.strip()


def integer(value, positive=True):
    if type(value) is not int or abs(value) > 1000000 or (positive and value <= 0):
        abort(400, "Invalid integer")
    return value


def roles(*allowed):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            user = db.session.get(User, session.get("uid")) if session.get("uid") else None
            if (
                not user
                or not user.active
                or session.get("password_version") != hashlib.sha256(user.password_hash.encode()).hexdigest()
                or session.get("session_version") != user.session_version
            ):
                abort(401)
            if user.role != "admin" and user.role not in allowed:
                abort(403)
            g.user = user
            return fn(*args, **kwargs)

        return wrapped

    return decorate


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.getenv("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,
        RATELIMIT_STORAGE_URI=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
        VAT_RATE=os.getenv("VAT_RATE", "7.00"),
    )
    if config:
        app.config.update(config)
    if not app.config["SECRET_KEY"] or len(app.config["SECRET_KEY"]) < 32:
        raise RuntimeError("Set a random SECRET_KEY of at least 32 characters")
    uri = app.config["SQLALCHEMY_DATABASE_URI"] or ""
    if not app.testing and not uri.startswith("postgresql+psycopg://"):
        raise RuntimeError("DATABASE_URL must use postgresql+psycopg://")
    rate = money(str(app.config["VAT_RATE"]))
    if rate > 100:
        raise RuntimeError("Invalid VAT_RATE")
    db.init_app(app)
    Migrate(app, db)
    CSRFProtect(app)
    limiter = Limiter(get_remote_address, app=app, default_limits=["300 per minute"])
    app.extensions["erp_limiter"] = limiter

    @app.after_request
    def headers(response):
        response.headers.update(
            {
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self'; "
                    "connect-src 'self'; img-src 'self' data:; "
                    "base-uri 'none'; object-src 'none'; frame-ancestors 'none'"
                    if request.path == "/app"
                    else (
                        "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; "
                        "base-uri 'none'; frame-ancestors 'none'"
                        if request.path.startswith("/api/extended/documents/") and request.path.endswith("/print")
                        else "default-src 'none'; frame-ancestors 'none'"
                    )
                ),
                "Cache-Control": "no-store",
                "Referrer-Policy": "same-origin",
            }
        )
        if request.is_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @app.errorhandler(HTTPException)
    def http_error(error):
        db.session.rollback()
        return jsonify(error=error.description), error.code

    @app.errorhandler(IntegrityError)
    def conflict(error):
        db.session.rollback()
        return jsonify(error="Conflicting record"), 409

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        if database_is_ready(db.engine):
            return {"status": "ok"}, 200
        return {"status": "unavailable"}, 503

    @app.get("/auth/csrf")
    def csrf():
        return {"csrf_token": generate_csrf()}

    @app.post("/auth/login")
    @limiter.limit("5 per minute")
    def login():
        body = data()
        username = text(body, "username", 80)
        password = body.get("password")
        if not isinstance(password, str) or not 1 <= len(password) <= 128:
            abort(400, "Invalid password")
        user = db.session.scalar(db.select(User).where(User.username == username))
        # Always run a password hash check to reduce username timing disclosure.
        valid = check_password_hash(user.password_hash if user else app.config["DUMMY_HASH"], password)
        if not valid or not user or not user.active:
            abort(401, "Invalid credentials")
        session.clear()
        session["uid"] = user.id
        session["session_version"] = user.session_version
        session["password_version"] = hashlib.sha256(user.password_hash.encode()).hexdigest()
        session.permanent = True
        return {"role": user.role, "csrf_token": generate_csrf()}

    app.config["DUMMY_HASH"] = generate_password_hash(secrets.token_urlsafe(32))

    @app.post("/auth/logout")
    @roles(*ROLES)
    def logout():
        session.clear()
        return "", 204

    @app.get("/auth/me")
    @roles(*ROLES)
    def me():
        return {"id": g.user.id, "username": g.user.username, "role": g.user.role}

    def add_user(username, password, role):
        if (
            role not in ("sales", "warehouse", "accountant")
            or not isinstance(password, str)
            or not 12 <= len(password) <= 128
        ):
            abort(400, "Role or password invalid (12–128 characters required)")
        user = User(username=username, password_hash=generate_password_hash(password), role=role)
        db.session.add(user)
        db.session.commit()
        return user

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.password_option()
    def create_admin(username, password):
        """Bootstrap an admin with an interactive, hidden password prompt."""
        if not username.strip() or len(username) > 80:
            raise click.ClickException("Invalid username")
        db.session.add(User(username=username.strip(), password_hash=generate_password_hash(password), role="admin"))
        db.session.commit()
        click.echo("Admin created")

    @app.cli.command("bootstrap-admin")
    def bootstrap_admin():
        """Create a configured admin once, without changing an existing account."""
        username = os.getenv("BOOTSTRAP_ADMIN_USERNAME")
        password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
        if not username and not password:
            return
        if not username or not password:
            raise click.ClickException("Set both bootstrap credentials or neither")
        username = username.strip()
        if not username or len(username) > 80:
            raise click.ClickException("Invalid username")
        if not 12 <= len(password) <= 128:
            raise click.ClickException("Invalid password")
        if db.session.scalar(db.select(User).where(User.username == username)):
            click.echo("Admin bootstrap complete")
            return
        db.session.add(User(username=username, password_hash=generate_password_hash(password), role="admin"))
        db.session.commit()
        click.echo("Admin bootstrap complete")

    @app.route("/users", methods=["GET", "POST"])
    @roles()
    def users():
        if request.method == "GET":
            return {
                "items": [
                    {"id": user.id, "username": user.username, "role": user.role, "active": user.active}
                    for user in db.session.scalars(db.select(User).order_by(User.active, User.username).limit(200))
                ]
            }
        body = data()
        user = add_user(text(body, "username", 80), body.get("password"), body.get("role"))
        return {"id": user.id}, 201

    @app.patch("/users/<int:user_id>")
    @roles()
    def update_staff(user_id):
        """Owner-only staff role and activation changes with session revocation."""
        body = data()
        user = db.get_or_404(User, user_id)
        if user.role == "admin" or user.id == g.user.id:
            abort(403, "Owner account cannot be altered here")
        if not body or set(body) - {"role", "active"}:
            abort(400, "Invalid staff update")
        if "role" in body:
            if body["role"] not in ("sales", "warehouse", "accountant"):
                abort(400, "Invalid staff role")
            user.role = body["role"]
        if "active" in body:
            if type(body["active"]) is not bool:
                abort(400, "active must be boolean")
            user.active = body["active"]
        user.session_version += 1
        db.session.commit()
        return {"id": user.id, "role": user.role, "active": user.active}

    @app.post("/users/<int:user_id>/activate")
    @roles()
    def activate_user(user_id):
        user = db.get_or_404(User, user_id)
        user.active = True
        db.session.commit()
        return {"id": user.id, "active": user.active}

    @app.post("/users/<int:user_id>/password")
    @roles()
    def reset_user_password(user_id):
        """Let the owner reset a staff password without exposing the old one."""
        body = data()
        password = body.get("password")
        if not isinstance(password, str) or not 12 <= len(password) <= 128:
            abort(400, "Password must be 12–128 characters")
        user = db.get_or_404(User, user_id)
        user.password_hash = generate_password_hash(password)
        user.session_version += 1
        if user.id == g.user.id:
            session["session_version"] = user.session_version
            session["password_version"] = hashlib.sha256(user.password_hash.encode()).hexdigest()
        db.session.commit()
        return "", 204

    @app.route("/products", methods=["GET", "POST"])
    @roles("sales", "warehouse", "accountant")
    def products():
        if request.method == "GET":
            return {
                "items": [
                    {"id": p.id, "sku": p.sku, "name": p.name, "price": str(p.price), "stock": p.stock}
                    for p in db.session.scalars(db.select(Product).order_by(Product.id).limit(100))
                ]
            }
        if g.user.role not in ("admin", "warehouse"):
            abort(403)
        body = data()
        product = Product(sku=text(body, "sku", 80), name=text(body, "name"), price=money(body.get("price")))
        db.session.add(product)
        db.session.commit()
        return {"id": product.id}, 201

    @app.route("/customers", methods=["GET", "POST"])
    @roles("sales", "accountant")
    def customers():
        if request.method == "GET":
            return {
                "items": [
                    {"id": c.id, "name": c.name, "tax_id": c.tax_id, "address": c.address}
                    for c in db.session.scalars(db.select(Customer).order_by(Customer.id).limit(100))
                ]
            }
        if g.user.role not in ("admin", "sales"):
            abort(403)
        body = data()
        tax_id = body.get("tax_id")
        if tax_id is not None and (
            not isinstance(tax_id, str) or len(tax_id) != 13 or not tax_id.isascii() or not tax_id.isdigit()
        ):
            abort(400, "Tax ID must contain 13 digits")
        customer = Customer(name=text(body, "name"), address=text(body, "address", 1000), tax_id=tax_id)
        db.session.add(customer)
        db.session.commit()
        return {"id": customer.id}, 201

    @app.post("/stock/adjustments")
    @roles("warehouse")
    def stock():
        body = data()
        product = db.session.get(Product, integer(body.get("product_id")), with_for_update=True)
        if not product:
            abort(404)
        delta = integer(body.get("delta"), False)
        if delta == 0 or product.stock + delta < 0:
            abort(409, "Invalid stock adjustment")
        product.stock += delta
        db.session.add(
            StockMovement(product_id=product.id, delta=delta, reason=text(body, "reason"), actor_id=g.user.id)
        )
        db.session.commit()
        return {"stock": product.stock}

    @app.get("/stock/movements")
    @roles("warehouse", "accountant")
    def movements():
        return {
            "items": [
                {"id": m.id, "product_id": m.product_id, "delta": m.delta, "reason": m.reason, "actor_id": m.actor_id}
                for m in db.session.scalars(db.select(StockMovement).order_by(StockMovement.id.desc()).limit(100))
            ]
        }

    @app.post("/sales")
    @roles("sales")
    def sales():
        body = data()
        customer = db.session.get(Customer, integer(body.get("customer_id")))
        if not customer:
            abort(404)
        lines = body.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= 100:
            abort(400, "Expected 1–100 lines")
        quantities = {}
        for line in lines:
            if not isinstance(line, dict):
                abort(400)
            pid, qty = integer(line.get("product_id")), integer(line.get("quantity"))
            if pid in quantities:
                abort(400, "Duplicate product")
            quantities[pid] = qty
        # Stable row locking order avoids overselling and reduces deadlocks.
        products = list(
            db.session.scalars(
                db.select(Product).where(Product.id.in_(quantities)).order_by(Product.id).with_for_update()
            )
        )
        if len(products) != len(quantities):
            abort(404)
        from .extended import CustomerPrice

        special = {
            row.product_id: row.price
            for row in db.session.scalars(
                db.select(CustomerPrice).where(
                    CustomerPrice.customer_id == customer.id,
                    CustomerPrice.product_id.in_(quantities),
                )
            )
        }
        subtotal = sum((special.get(p.id, p.price) * quantities[p.id] for p in products), Decimal("0.00"))
        vat = (subtotal * rate / 100).quantize(CENT, rounding=ROUND_HALF_UP)
        if subtotal + vat > Decimal("999999999.99"):
            abort(400, "Sale exceeds amount limit")
        sale = Sale(
            customer_id=customer.id,
            customer_name=customer.name,
            customer_tax_id=customer.tax_id,
            customer_address=customer.address,
            subtotal=subtotal,
            vat_rate=rate,
            vat=vat,
            total=subtotal + vat,
        )
        db.session.add(sale)
        db.session.flush()
        for p in products:
            qty = quantities[p.id]
            if p.stock < qty:
                abort(409, "Insufficient stock")
            p.stock -= qty
            db.session.add(
                SaleLine(
                    sale_id=sale.id,
                    product_id=p.id,
                    sku=p.sku,
                    name=p.name,
                    quantity=qty,
                    price=special.get(p.id, p.price),
                )
            )
            db.session.add(
                StockMovement(product_id=p.id, delta=-qty, reason="Sale", sale_id=sale.id, actor_id=g.user.id)
            )
        db.session.commit()
        return {"id": sale.id, "subtotal": str(sale.subtotal), "vat": str(sale.vat), "total": str(sale.total)}, 201

    @app.get("/sales/<int:sale_id>")
    @roles("sales", "accountant")
    def sale_detail(sale_id):
        sale = db.get_or_404(Sale, sale_id)
        return {
            "id": sale.id,
            "customer_name": sale.customer_name,
            "customer_tax_id": sale.customer_tax_id,
            "customer_address": sale.customer_address,
            "subtotal": str(sale.subtotal),
            "vat_rate": str(sale.vat_rate),
            "vat": str(sale.vat),
            "total": str(sale.total),
            "paid": str(sale.paid),
            "balance": str(sale.total - sale.paid),
            "lines": [
                {"sku": line.sku, "name": line.name, "quantity": line.quantity, "price": str(line.price)}
                for line in db.session.scalars(db.select(SaleLine).where(SaleLine.sale_id == sale_id))
            ],
        }

    @app.post("/sales/<int:sale_id>/payments")
    @roles("accountant")
    def payments(sale_id):
        body = data()
        sale = db.session.get(Sale, sale_id, with_for_update=True)
        if not sale:
            abort(404)
        amount = money(body.get("amount"))
        if amount <= 0 or amount > sale.total - sale.paid:
            abort(409, "Payment exceeds outstanding balance or is zero")
        db.session.add(
            Payment(sale_id=sale.id, amount=amount, reference=text(body, "reference", 100), actor_id=g.user.id)
        )
        sale.paid += amount
        db.session.commit()
        return {"paid": str(sale.paid), "balance": str(sale.total - sale.paid)}, 201

    from .online import install_online

    install_online(app)
    from .recovery import install_recovery

    install_recovery(app)

    from .operations import install_operations

    install_operations(app)

    from .extended import install_extended

    install_extended(app)

    # Add-on report: read-only; existing sales, documents and stock routes are unchanged.
    from .receivables_report import bp as receivables_report_bp

    app.register_blueprint(receivables_report_bp)

    from .customer_lookup import bp as customer_lookup_bp

    app.register_blueprint(customer_lookup_bp)

    from .quotations import bp as quotation_bp

    app.register_blueprint(quotation_bp)

    from .billing_previews import bp as billing_previews_bp

    app.register_blueprint(billing_previews_bp)

    from .billing_batches import bp as billing_batches_bp

    app.register_blueprint(billing_batches_bp)

    from .return_intake import bp as return_intake_bp

    app.register_blueprint(return_intake_bp)

    from .purchasing import bp as purchasing_bp

    app.register_blueprint(purchasing_bp)

    # Trace purchase-cost evidence without inventing historical COGS or profit.
    from .cost_evidence import bp as cost_evidence_bp

    app.register_blueprint(cost_evidence_bp)

    return app
