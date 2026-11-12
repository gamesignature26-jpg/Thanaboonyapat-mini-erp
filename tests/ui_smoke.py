"""Run explicitly in CI with Playwright; all accounts/data are disposable and synthetic."""

import io
import os
import threading

from PIL import Image
from playwright.sync_api import sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

from erp import create_app
from erp.extended import CompanyProfile, CustomerPrice
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
            CompanyProfile(legal_name="Synthetic ERP", tax_id="0123456789012", address="Synthetic Seller Address")
        )
        db.session.add(
            OnlineExpense(amount=100, description="Synthetic receipt", category="Test", method="cash", actor_id=1)
        )
        db.session.commit()
    server = make_server("127.0.0.1", 8765, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, channel=os.getenv("PLAYWRIGHT_CHROMIUM_CHANNEL"))
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.add_init_script("""
              window.blePrintChunks = [];
              const device = new EventTarget();
              device.name = 'Synthetic BLE printer';
              device.gatt = {
                connected: false,
                async connect() { this.connected = true; return this; },
                disconnect() { this.connected = false; },
                async getPrimaryService() { return this; },
                async getCharacteristic() {
                  return {properties: {write: true}, async writeValueWithResponse(bytes) {
                    window.blePrintChunks.push(Array.from(bytes));
                  }};
                },
              };
              Object.defineProperty(navigator, 'bluetooth', {value: {async requestDevice() { return device; }}});
            """)
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://127.0.0.1:8765/app")
            page.get_by_label("ชื่อผู้ใช้", exact=True).fill("ui-test-owner")
            page.get_by_label("รหัสผ่าน", exact=True).fill("synthetic-ui-password")
            page.get_by_role("button", name="เข้าสู่ระบบ", exact=True).click()
            page.get_by_role("button", name="เมนูทั้งหมด", exact=True).click()
            page.get_by_role("button", name="ลูกค้า", exact=True).click()
            page.get_by_label("ค้นหาลูกค้า", exact=True).fill("ไม่พบชื่อนี้")
            page.get_by_text("ไม่พบลูกค้า ลองใช้ชื่อหรือที่อยู่อื่น").wait_for()
            page.get_by_label("ค้นหาลูกค้า", exact=True).fill("Synthetic POS")
            page.get_by_text("Synthetic POS customer", exact=True).wait_for()
            page.get_by_role("button", name="ใบเสนอราคา", exact=True).click()
            page.locator('#quote-add-form select[name="product_id"]').select_option(index=1)
            page.locator('#quote-add-form input[name="quantity"]').fill("2")
            page.get_by_role("button", name="เพิ่มรายการเสนอราคา", exact=True).click()
            page.locator('#quote-form select[name="customer_id"]').select_option(label="Synthetic POS customer")
            page.get_by_role("button", name="บันทึกใบเสนอราคาร่าง", exact=True).click()
            page.get_by_text("QT-DRAFT-000001", exact=True).first.wait_for()
            page.get_by_role("button", name="ดูรายละเอียด", exact=True).click()
            page.get_by_text("รายละเอียด QT-DRAFT-000001", exact=True).wait_for()
            page.get_by_role("button", name="ขายส่ง / จัดส่ง", exact=True).click()
            page.get_by_role("button", name="เชื่อมต่อเครื่องพิมพ์ Bluetooth", exact=True).click()
            page.get_by_role("dialog", name="เครื่องพิมพ์ Bluetooth 58 มม.").wait_for()
            page.get_by_role("button", name="ปิด", exact=True).click()
            page.get_by_label("ที่อยู่จัดส่ง", exact=True).fill("Synthetic delivery address")
            page.locator('#wh-add-form select[name="product_id"]').select_option(index=1)
            page.get_by_role("button", name="เพิ่มสินค้าในออเดอร์", exact=True).click()
            assert page.get_by_label("ที่อยู่จัดส่ง", exact=True).input_value() == "Synthetic delivery address"
            page.get_by_role("radio", name="ราคารวม VAT", exact=False).check()
            assert "100.00" in page.locator("#wh-vat-total .total").inner_text()
            page.get_by_role("button", name="ขายหน้าร้าน POS", exact=True).click()
            page.get_by_label("ค้นหาสินค้า", exact=True).fill("unmatched product")
            page.get_by_text("ไม่พบสินค้า ลองใช้ชื่อหรือรหัสอื่น").wait_for()
            page.get_by_label("ค้นหาสินค้า", exact=True).fill("ui-water")
            page.get_by_role("button", name="Synthetic water pack", exact=False).click()
            page.get_by_role("button", name="ดูรายการขาย", exact=False).click()
            assert page.locator("#pos-cart").evaluate("element => element === document.activeElement")
            page.locator('#pos-form select[name="customer_id"]').select_option(label="Synthetic POS customer")
            page.get_by_text("ราคาพิเศษลูกค้า", exact=True).wait_for()
            assert "85.60" in page.locator("#pos-form .total").inner_text()
            page.get_by_role("radio", name="ราคารวม VAT", exact=False).check()
            assert "80.00" in page.locator("#pos-form .total").inner_text()
            page.locator('#pos-form select[name="method"]').select_option("credit")
            page.get_by_role("button", name="บันทึกการขายและตัดสต๊อก", exact=True).click()
            page.get_by_role("button", name="พิมพ์สรุปบิล #1", exact=True).wait_for()
            page.get_by_role("button", name="บิลขาย / ลูกหนี้", exact=True).click()
            with page.expect_popup() as billing:
                page.get_by_role("link", name="ใบวางบิลตัวอย่าง", exact=True).click()
            billing.value.get_by_text("ใบวางบิลตัวอย่าง", exact=False).first.wait_for()
            billing.value.get_by_text("ไม่ใช่ใบกำกับภาษี", exact=False).first.wait_for()
            billing.value.close()
            page.get_by_role("button", name="รับชำระ", exact=True).click()
            page.get_by_role("button", name="บันทึกรับชำระ", exact=True).click()
            page.get_by_role("button", name="ออกใบเสร็จร่าง", exact=True).click()
            with page.expect_popup() as slip:
                page.get_by_role("link", name="58 มม.", exact=True).click()
            slip.value.get_by_text("ข้อมูลทดสอบเท่านั้น", exact=False).first.wait_for()
            slip.value.get_by_role("button", name="พิมพ์เอกสาร", exact=True).wait_for()
            slip.value.close()
            page.get_by_text("ออกใบกำกับภาษีร่าง", exact=True).click()
            assert page.get_by_label("ชื่อผู้ซื้อ / ชื่อนิติบุคคล", exact=True).input_value() == "Synthetic POS customer"
            page.get_by_label("เลขผู้เสียภาษี 13 หลัก", exact=True).fill("0123456789012")
            page.get_by_label("รหัสสาขา (00000 สำหรับสำนักงานใหญ่)", exact=True).fill("00000")
            page.get_by_role("button", name="บันทึกใบกำกับภาษีร่าง", exact=True).click()
            invoice = page.locator(".document-actions").filter(has_text="TAX-")
            with page.expect_popup() as tax:
                invoice.get_by_role("link", name="A4", exact=True).click()
            tax.value.get_by_text("รวม VAT", exact=True).wait_for()
            tax.value.get_by_text("สำนักงานใหญ่", exact=True).wait_for()
            tax.value.close()
            printer = invoice.get_by_role("button", name="พิมพ์ Bluetooth", exact=True)
            printer.click()
            page.get_by_label("Service UUID", exact=True).fill("fff0")
            page.get_by_label("Write Characteristic UUID", exact=True).fill("fff2")
            page.get_by_role("button", name="เลือกเครื่องพิมพ์", exact=True).click()
            page.get_by_text("เชื่อมต่อแล้ว Synthetic BLE printer", exact=True).wait_for()
            page.locator("#printer-close").click()
            printer.click()
            page.get_by_text("ส่งข้อมูลไปยังเครื่องพิมพ์แล้ว", exact=True).wait_for()
            assert page.evaluate("window.blePrintChunks[0]") == [27, 64]
            assert page.evaluate("window.blePrintChunks[1].slice(0, 3)") == [29, 118, 48]
            page.get_by_role("button", name="ใบเสนอราคา", exact=True).click()
            page.get_by_role("button", name="ดูรายละเอียด", exact=True).click()
            page.locator("#quote-status-note").fill("Synthetic quotation sent to customer")
            page.get_by_role("button", name="บันทึกว่าส่งแล้ว", exact=True).click()
            page.locator("#quote-detail").get_by_text("สถานะ: ส่งให้ลูกค้าแล้ว", exact=True).wait_for()
            page.locator("#quote-status-note").fill("Synthetic customer agreed in test")
            page.get_by_role("button", name="ลูกค้ายืนยัน", exact=True).click()
            page.locator('#quote-convert-form select[name="delivery_mode"]').select_option("pickup")
            page.get_by_role("button", name="ยืนยันแปลงเป็นบิลขาย", exact=True).click()
            page.locator("#quote-detail").get_by_text("แปลงเป็นบิลขาย #2 แล้ว", exact=True).wait_for()
            page.get_by_role("button", name="รับคืนสินค้า", exact=True).click()
            page.locator("#return-sale-id").fill("1")
            page.get_by_role("button", name="โหลดสินค้าในบิล", exact=True).click()
            page.locator('#return-add-form select[name="sale_line_id"]').select_option(index=1)
            page.locator('#return-add-form input[name="quantity"]').fill("1")
            page.get_by_role("button", name="เพิ่มรายการคืน", exact=True).click()
            page.locator("#return-reason").fill("Synthetic sealed water pack returned")
            page.get_by_role("button", name="บันทึกคำขอรับคืนร่าง", exact=True).click()
            page.locator("#return-detail").get_by_text("RETURN-DRAFT-000001", exact=False).wait_for()
            page.locator('#return-inspect-form select[name="condition"]').select_option("resellable")
            page.locator('#return-inspect-form input[name="inspection_note"]').fill("Sealed packs physically verified")
            page.get_by_role("button", name="ยืนยันรับคืน", exact=True).click()
            page.locator("#return-detail").get_by_text("ตรวจรับแล้ว", exact=False).wait_for()
            page.get_by_role("button", name="เมนูทั้งหมด", exact=True).click()
            page.get_by_role("button", name="จัดซื้อและรับสินค้า", exact=True).click()
            page.locator('#supplier-form input[name="name"]').fill("Synthetic Water Supplier")
            page.get_by_role("button", name="บันทึกซัพพลายเออร์", exact=True).click()
            page.locator('#purchase-form select[name="supplier_id"] option', has_text="Synthetic Water Supplier").wait_for()
            page.locator('#purchase-add-form select[name="product_id"]').select_option(index=1)
            page.locator('#purchase-add-form input[name="quantity"]').fill("3")
            page.locator('#purchase-add-form input[name="unit_cost"]').fill("42.50")
            page.get_by_role("button", name="เพิ่มสินค้าในใบสั่งซื้อ", exact=True).click()
            page.wait_for_function("() => !!document.querySelector('#purchase-form button:not(:disabled)')")
            page.locator('#purchase-form select[name="supplier_id"]').select_option(index=1)
            page.get_by_role("button", name="บันทึกใบสั่งซื้อร่าง", exact=True).click()
            page.locator("#purchase-detail").get_by_text("PO-DRAFT-000001", exact=False).wait_for()
            page.locator('#purchase-receive-form input[name="receipt_note"]').fill("Synthetic goods physically counted")
            page.get_by_role("button", name="ยืนยันรับสินค้าเข้าสต็อก", exact=True).click()
            page.locator("#purchase-detail").get_by_text("รับสินค้าแล้ว", exact=False).first.wait_for()
            assert (
                page.evaluate(
                    "async () => (await (await fetch('/products')).json()).items.find(p => p.sku === 'UI-WATER').stock"
                )
                == 11
            )
            page.get_by_role("button", name="เมนูทั้งหมด", exact=True).click()
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
