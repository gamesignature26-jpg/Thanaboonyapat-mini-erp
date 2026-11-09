"""Run explicitly in CI with Playwright; all accounts/data are disposable and synthetic."""

import io
import threading

from PIL import Image
from playwright.sync_api import sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from erp import create_app
from erp.extended import CustomerPrice
from erp.models import Customer, Product, User, db
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
        product = Product(sku="UI-WATER", name="Synthetic water pack", stock=10, price=100)
        customer = Customer(name="Synthetic POS customer", address="Synthetic address")
        db.session.add_all([product, customer])
        db.session.flush()
        db.session.add(CustomerPrice(product_id=product.id, customer_id=customer.id, price=80, updated_by=1))
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
            page.get_by_role("button", name="ขายหน้าร้าน POS", exact=True).click()
            page.get_by_role("button", name="Synthetic water pack", exact=False).click()
            page.locator('#pos-form select[name="customer_id"]').select_option(label="Synthetic POS customer")
            page.get_by_text("ราคาพิเศษลูกค้า", exact=True).wait_for()
            assert "85.60" in page.locator("#pos-form .total").inner_text()
            page.locator('#pos-form select[name="method"]').select_option("credit")
            page.get_by_role("button", name="บันทึกการขายและตัดสต๊อก", exact=True).click()
            page.get_by_role("button", name="รับชำระ", exact=True).click()
            page.get_by_role("button", name="บันทึกรับชำระ", exact=True).click()
            page.get_by_role("button", name="ออกใบเสร็จร่าง", exact=True).click()
            with page.expect_popup() as slip:
                page.get_by_role("link", name="58 มม.", exact=True).click()
            slip.value.get_by_text("ข้อมูลทดสอบเท่านั้น", exact=False).first.wait_for()
            slip.value.get_by_role("button", name="พิมพ์เอกสาร", exact=True).wait_for()
            slip.value.close()
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
        print("Mobile browser verified: POS customer price, payment, receipt preview, and operations")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
