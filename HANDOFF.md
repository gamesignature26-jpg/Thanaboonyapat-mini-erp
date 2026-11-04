# ส่งต่องาน

Branch local: `feature/secure-mini-erp` จาก main `d54b3721339a25d132682509438332c6a3826d3f`
Repository: https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp

โค้ดและ automated tests พร้อม แต่ GitHub integration ปฏิเสธการเขียนด้วย 403
ยังไม่มี remote feature branch, PR หรือผล GitHub Actions
ต้องให้บัญชี/installation ที่ใช้ส่งโค้ดมีสิทธิ์เขียน contents และ workflow ของ repository นี้ก่อน
ไม่ได้เปลี่ยนสิทธิ์ integration หรือใช้ credentials อื่นเพื่อข้ามข้อจำกัด

ถ้าทำต่อจาก checkout นี้ หลังจัดการสิทธิ์แล้ว:

```sh
git switch feature/secure-mini-erp
git push -u origin HEAD:refs/heads/feature/secure-mini-erp
```

ถ้าทำจากเครื่องใหม่ ใช้ bundle ที่แนบไว้:

```sh
git clone /path/to/thanabunyapat-mini-erp.bundle erp-review
cd erp-review
git switch feature/secure-mini-erp
git remote set-url origin https://github.com/gamesignature26-jpg/Thanaboonyapat-mini-erp.git
git push -u origin HEAD:refs/heads/feature/secure-mini-erp
```

หรือใช้ patch กับ checkout ใหม่ที่ตรงกับ main ด้านบน:

```sh
git switch -c feature/secure-mini-erp
git am /path/to/thanabunyapat-mini-erp.patch
```

ตรวจ Actions ชื่อ ERP tests หลัง push; workflow รันบน feature/** และ pull request ที่ target main
รอ PostgreSQL tests และ migration checks ผ่านก่อน review ห้ามตีความผล local เป็นผล CI
ไม่ต้อง merge main หรือ deploy เพื่อทดสอบ workflow นี้

ผล local: PostgreSQL 16.2, 25 tests ผ่าน (รวม concurrency), migration upgrade/check/downgrade/upgrade ผ่าน,
ruff lint/format ผ่าน ดู README และ PRODUCTION_READINESS สำหรับวิธีใช้/ข้อจำกัด
