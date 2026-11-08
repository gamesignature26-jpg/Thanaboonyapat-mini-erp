"""Run explicitly in CI with Playwright; all accounts/data are disposable and synthetic."""

import io
import threading

from PIL import Image
from playwright.sync_api import sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from erp import create_app
from erp.models import User, db
from erp.online import OnlineExpense


def main():
    app = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "synthetic-browser-test-key-32-characters",
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "SESSION_COOKIE_SECURE": False,
            "RATELIMIT_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        db.session.add(
            User(
                username="ui-test-owner",
                password_hash=generate_password_hash("synthetic-ui-password"),
                role="admin",
                active=True,
            )
        )
        db.session.flush()
        db.session.add(
            OnlineExpense(amount=100, description="Synthetic receipt", category="Test", method="cash", actor_id=1)
        )
        db.session.commit()
    server = make_server("127.0.0.1", 8765, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://127.0.0.1:8765/app")
            page.get_by_label("ชื่อผู้ใช้", exact=True).fill("ui-test-owner")
            page.get_by_label("รหัสผ่าน", exact=True).fill("synthetic-ui-password")
            page.get_by_role("button", name="เข้าสู่ระบบ", exact=True).click()
            page.get_by_role("button", name="รายสัปดาห์ / ค่าแรง / หลักฐาน", exact=True).click()
            page.get_by_role("heading", name="ยืนยันอีเมล", exact=True).wait_for()
            page.get_by_role("button", name="รายสัปดาห์ / ค่าแรง", exact=True).click()
            page.get_by_label("ชื่อคนขับ (ตรงกับชื่อในออเดอร์)").fill("UI driver")
            page.get_by_label("ค่าแรงต่อวัน", exact=True).fill("500.00")
            page.get_by_role("button", name="บันทึกคนขับ", exact=True).click()
            page.get_by_label("พนักงาน", exact=True).select_option(label="UI driver")
            page.get_by_label("รายละเอียด / เหตุผล").fill("Synthetic work day")
            page.get_by_role("button", name="ยืนยันรายการ", exact=True).click()
            page.locator("#op-week-result").get_by_text("Synthetic work day", exact=False).wait_for(state="attached")
            page.get_by_role("button", name="รูปค่าใช้จ่าย / สลิป", exact=True).click()
            page.get_by_label("ประเภทหลักฐาน").select_option("expense_id")
            page.get_by_label("เลขบิลขาย หรือเลขรายจ่ายที่บันทึกแล้ว").fill("1")
            out = io.BytesIO()
            Image.new("RGB", (10, 10), "green").save(out, "PNG")
            page.get_by_label("รูปหลักฐาน", exact=True).set_input_files(
                {"name": "synthetic.png", "mimeType": "image/png", "buffer": out.getvalue()}
            )
            page.get_by_role("button", name="อัปโหลดหลักฐาน", exact=True).click()
            page.get_by_text("รอตรวจ", exact=True).wait_for()
            page.get_by_role("button", name="ออเดอร์ LINE", exact=True).click()
            page.get_by_role("heading", name="รับออเดอร์จาก LINE ส่วนตัวและกลุ่ม").wait_for()
            assert not errors, errors
            page.screenshot(path="ui-operations-mobile.png", full_page=True)
            browser.close()
        print("Mobile browser verified: login, email settings, wages, receipt upload, LINE inbox")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
