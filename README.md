# Thanabunyapat Mini ERP

Flask + PostgreSQL **API MVP** สำหรับสินค้า ลูกค้า การขาย สต็อก การรับชำระเงิน และ VAT
พัฒนาบน `feature/secure-mini-erp` ไม่ deploy และไม่เปลี่ยน main
ยังไม่มีหน้าจอ ERP สำหรับผู้ใช้ทั่วไป และยังไม่พร้อม Production ดู [PRODUCTION_READINESS.md](PRODUCTION_READINESS.md)

## ติดตั้งสำหรับพัฒนา

ต้องใช้ Python 3.12 และ PostgreSQL 16 (ทดสอบเพิ่มเติมใน PostgreSQL ชั่วคราว)

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

กำหนด environment ผ่านระบบจัดการ secrets หรือ environment ของเครื่องพัฒนา:

| ตัวแปร | ความหมาย |
| --- | --- |
| `SECRET_KEY` | ค่าสุ่มอย่างน้อย 32 ตัวอักษร สร้างใหม่สำหรับแต่ละ environment ห้าม commit |
| `DATABASE_URL` | `postgresql+psycopg://USER:PASSWORD@HOST/DB` ใช้ฐานข้อมูลสมมติที่สร้างใหม่เท่านั้นในการพัฒนา |
| `VAT_RATE` | เปอร์เซ็นต์ VAT ค่าเริ่มต้น `7.00` (ต้องให้ผู้รับผิดชอบบัญชียืนยันก่อนใช้จริง) |
| `RATELIMIT_STORAGE_URI` | ค่าเริ่มต้น `memory://` เหมาะสำหรับพัฒนา worker เดียวเท่านั้น |
| `TEST_DATABASE_URL` | ฐานข้อมูลทดสอบแยก ชื่อต้องลงท้าย `_test` **tests ลบตารางในฐานนี้** ห้ามชี้ข้อมูลจริง |

สร้าง secret ได้ด้วย `python -c 'import secrets; print(secrets.token_urlsafe(48))'` แล้วเก็บอย่างปลอดภัย
ไม่มีบัญชี/รหัสผ่านเริ่มต้นในแอป ไม่โหลด `.env` ให้อัตโนมัติ

```sh
flask --app erp db upgrade
flask --app erp create-admin
```

คำสั่ง create-admin รับรหัสผ่านแบบซ่อนและยืนยันซ้ำ ต้องยาว 12–128 ตัวอักษร
เรียกผ่าน HTTPS ที่ตั้งค่า trust ถูกต้อง เพราะ session cookie มี Secure, HttpOnly, SameSite=Lax
สามารถรัน WSGI หลัง HTTPS reverse proxy ที่ตั้งค่าอย่างเหมาะสมได้ด้วย:

```sh
gunicorn 'erp:create_app()' --bind 127.0.0.1:8000 --workers 1
```

ไม่เปิด debug ในระบบจริง และไม่ตั้ง ProxyFix โดยไม่กำหนด trusted proxy ให้ชัดเจน
การใช้ shared rate limiter เช่น Redis ต้องติดตั้ง driver และทดสอบ integration ก่อนเพิ่ม workers

## API และสิทธิ์

ทุก POST รับ JSON และต้องมี `X-CSRFToken` รวมถึง login/logout
1. GET `/auth/csrf` เพื่อรับ token และ session cookie
2. POST `/auth/login` ด้วย username/password พร้อม token และ cookie
3. ใช้ `csrf_token` ใหม่จากผล login สำหรับ POST ถัดไป และส่ง cookie เดิมทุกครั้ง
4. POST `/auth/logout` เพื่อล้าง cookie ปัจจุบัน

| API | ผู้ใช้ที่อนุญาต (admin เข้าถึงทั้งหมด) |
| --- | --- |
| GET `/health`, GET `/auth/csrf`, POST `/auth/login` | สาธารณะ; login จำกัด 5 ครั้ง/นาที/IP |
| GET `/auth/me`, POST `/auth/logout` | ผู้ใช้ที่ active |
| POST `/users` | admin; `username`, `password`, `role` |
| GET `/products` | sales, warehouse, accountant |
| POST `/products` | warehouse; `sku`, `name`, `price` |
| GET `/customers` | sales, accountant |
| POST `/customers` | sales; `name`, `address`, `tax_id` ไม่บังคับ |
| POST `/stock/adjustments` | warehouse; `product_id`, `delta`, `reason` |
| GET `/stock/movements` | warehouse, accountant |
| POST `/sales` | sales; `customer_id`, `lines` |
| GET `/sales/{id}` | sales, accountant |
| POST `/sales/{id}/payments` | accountant; `amount`, `reference` |

รายการ GET จำกัด 100 รายการ ยังไม่มี pagination/search (ข้อจำกัด MVP)
roles เป็นสิทธิ์ระดับบริษัทเดียว ไม่รองรับหลาย tenant/สาขา หรือแยกเจ้าของเอกสาร

ตัวอย่าง body โดยใช้เฉพาะข้อมูลสมมติ:

```json
{"sku":"TEST-001","name":"สินค้าทดสอบ","price":"100.00"}
```
```json
{"name":"ลูกค้าทดสอบ","address":"ที่อยู่สมมติ"}
```
```json
{"product_id":1,"delta":10,"reason":"รับเข้าสำหรับทดสอบ"}
```
```json
{"customer_id":1,"lines":[{"product_id":1,"quantity":2}]}
```
```json
{"amount":"214.00","reference":"synthetic-transfer-001"}
```

จำนวนเงินต้องเป็น decimal string ไม่เกิน 2 ตำแหน่ง จำนวนสินค้าต้องเป็น integer > 0
ราคาขายอ่านจากฐานข้อมูล ไม่รับราคาที่ client ส่งมา สินค้ามี stock เริ่มต้น 0
การขายบันทึกข้อมูลสินค้า/ลูกค้า/ราคา/อัตรา VAT เป็น snapshot
VAT แบบราคาไม่รวมภาษี: ยอดรวมก่อนภาษี × อัตรา ปัด HALF_UP ที่ระดับเอกสาร 2 ตำแหน่ง
เช่น 2 × 100.00 = 200.00 + VAT 14.00 = 214.00
ไม่รองรับส่วนลด VAT แบบรวมราคา หรือสินค้าหลายอัตราในเอกสารเดียว

ตัด stock และสร้าง sale/lines/movements ใน transaction เดียว ใช้ PostgreSQL row locks ตามลำดับ id
รับชำระเงินโดยล็อก sale ป้องกันยอดเกิน outstanding และใช้ reference ที่ unique ทั้งระบบ
ส่ง reference ซ้ำตอบ 409 และ rollback ไม่บันทึกซ้ำ; ไม่ใช่ payment gateway integration
stock adjustment เก็บ actor/reason/time และ sale movement เก็บ sale_id

## ตรวจสอบ

```sh
ruff check erp tests migrations
ruff format --check erp tests migrations
flask --app erp db upgrade
flask --app erp db check
python -m pytest -q
```

ถ้าไม่กำหนด TEST_DATABASE_URL tests ใช้ SQLite ใน memory และข้าม concurrency test
ต้องทดสอบ PostgreSQL เพื่อยืนยัน row locking; CI ใช้ PostgreSQL 16 พร้อมข้อมูลสมมติเท่านั้น
GitHub Actions ทดสอบ migrations upgrade/check/downgrade/upgrade และ pytest พร้อม artifact JUnit
ไม่ deploy ไม่มี Render configuration และ workflow มีสิทธิ์ contents:read เท่านั้น

ทดสอบครอบคลุม CSRF, login/logout, rate limit, role denials, password hash,
configuration fail-closed, invalid amounts/quantities, transaction rollback, VAT rounding,
snapshot, duplicate payment/overpayment, และ concurrent sales/payments ใน PostgreSQL
