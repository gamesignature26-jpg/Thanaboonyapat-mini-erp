from werkzeug.security import generate_password_hash

from erp import create_app
from erp.models import User, db


def test_https_login_requires_same_origin_referrer():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "synthetic-https-test-key-32-characters",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "RATELIMIT_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        db.session.add(
            User(username="owner", password_hash=generate_password_hash("synthetic-password-only"), role="admin")
        )
        db.session.commit()
    client = app.test_client()
    origin = "https://erp.example.test"
    response = client.get("/auth/csrf", base_url=origin)
    assert response.headers["Referrer-Policy"] == "same-origin"
    headers = {"X-CSRFToken": response.json["csrf_token"]}
    body = {"username": "owner", "password": "synthetic-password-only"}
    assert client.post("/auth/login", base_url=origin, json=body, headers=headers).status_code == 400
    assert (
        client.post(
            "/auth/login", base_url=origin, json=body, headers={**headers, "Referer": "https://other.example/app"}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/auth/login", base_url=origin, json=body, headers={**headers, "Referer": origin + "/app"}
        ).status_code
        == 200
    )
