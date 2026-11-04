# ข้อจำกัดก่อน Production

สถานะ: API MVP สำหรับ review และทดสอบด้วยข้อมูลสมมติ ยังไม่อนุมัติใช้งานจริง

## ต้องเสร็จก่อนใช้งานจริง

- ทำหน้าจอ ERP, UAT กับผู้ใช้จริงโดยเริ่มจากข้อมูลจำลอง, pagination/search, แก้ไขสินค้า/ลูกค้า และกระบวนการบริหารข้อมูลหลัก
- ยืนยันข้อกำหนดบัญชี/ภาษีกับผู้รับผิดชอบ: เลขที่เอกสารตามกฎหมาย, ข้อมูลผู้ขาย/สาขา, ใบกำกับภาษี/ใบเสร็จ, VAT รวมราคา/ยกเว้น/หลายอัตรา, ส่วนลด, รายงานภาษี, การคืนสินค้า/ใบลดหนี้/ยกเลิกเอกสาร ปัจจุบันตรวจ tax_id เพียงรูปแบบ 13 หลัก ไม่ตรวจ checksum หรือทะเบียนผู้เสียภาษี
- เพิ่ม sale idempotency key เพื่อป้องกันการสร้างยอดขายซ้ำเมื่อ client retry การรับเงินปัจจุบันใช้ reference unique และคืน 409 เมื่อซ้ำ ต้องกำหนดการ reconcile และวิธีแก้รายการรับเงินผิด
- ระบบบัญชีผู้ใช้ยังไม่มี password reset/change, MFA, admin UI สำหรับเปลี่ยนสิทธิ์/ปิดผู้ใช้, session revocation และ audit trail สำหรับการเปลี่ยนสิทธิ์ ปัจจุบันตรวจ active และ role ทุก request แต่ cookie ที่คัดลอกก่อน logout อาจใช้ได้จนหมดอายุ
- ใช้ shared persistent rate limiter ที่ทดสอบแล้วก่อนหลาย workers/instances; memory limiter รีเซ็ตเมื่อ restart และไม่แชร์ระหว่าง workers ต้องยืนยัน client IP หลัง trusted proxy และเพิ่มการป้องกัน brute force ระดับบัญชี
- กำหนด HTTPS reverse proxy, trusted forwarded headers, trusted host policy, PostgreSQL TLS, connection pooling/limits/timeouts, least-privilege DB role, secret manager และ rotation ไม่ใช้ค่าทดสอบในระบบจริง
- จัดทำ encrypted backups/PITR และทดลอง restore, migration rollback/forward และ disaster recovery; downgrade ที่มีใน repo ลบข้อมูล ไม่ใช่วิธีกู้ข้อมูลจริง
- เพิ่ม monitoring, readiness ที่ตรวจ DB, error alerts, audit trail ครบทุก mutation, retention/PDPA และการตรวจสอบ log ว่าไม่บันทึก credentials/ข้อมูลส่วนบุคคล
- ทดสอบ load, deadlock/retry policy, database failure และ browser end-to-end; ทบทวน dependency vulnerabilities และ security review พร้อม pin Actions ด้วย commit SHA ตามนโยบายองค์กร
- โมเดลปัจจุบันเป็นบริษัทเดียว stock หน่วยเต็ม คลังเดียว สกุลเงินเดียว ไม่มี purchasing, cost/COGS, FIFO, inventory valuation, multi-branch หรือ row-level ownership ต้องยืนยันว่าเพียงพอหรือขยายก่อนใช้

## สิ่งที่มีแล้ว

Password hashing (Werkzeug scrypt), CSRF ทุก POST, Secure/HttpOnly/SameSite cookies,
session timeout, login throttling, role checks, request size limits, security headers,
ORM queries, database constraints, transactional stock/payments, PostgreSQL row locks,
Decimal HALF_UP VAT, immutable sale snapshots ผ่าน API, stock/payment actor และ timestamp,
Alembic migrations และ automated tests/CI

ไม่มีการ deploy บน Render หรือบริการอื่น ไม่แก้ main และไม่ใช้ข้อมูลหรือรหัสผ่านจริง

## ผลตรวจใน workspace (2026-11-04)

- PostgreSQL 16.2 ชั่วคราวที่มีเฉพาะข้อมูลสมมติ: **25 passed** รวม concurrent sale/payment
- Alembic: upgrade → schema check ไม่มี drift → downgrade base → upgrade ผ่าน
- Ruff lint / format check และ git diff --check ผ่าน
- ผล GitHub Actions ให้ดู run บน branch/PR โดยตรง; ผล local ข้างต้นไม่ใช่การรับรอง Production

- GitHub ปฏิเสธ git push และ connector create_branch ด้วย 403 Resource not accessible by integration; branch/commits ยังอยู่ local เท่านั้น ยังไม่ได้รัน GitHub Actions หรือเปิด PR
- ตรวจ remote main แล้วยังคงเป็น `d54b3721339a25d132682509438332c6a3826d3f` ตรงกับก่อนเริ่มงาน
