# Thanabunyapat ERP Android APK — รุ่นทดสอบ

แอป Android นี้เปิดเฉพาะ Staging ของ Thanabunyapat Mini ERP และมีตัวทดสอบพิมพ์ผ่าน Bluetooth Classic SPP สำหรับเครื่องพิมพ์ 58 มม. ที่รองรับ ESC/POS เช่น PT-280 ที่จับคู่กับ Android แล้ว

## ขอบเขตรุ่น 0.1.0

- เปิดใช้งาน ERP Staging ผ่าน WebView ที่จำกัดไว้เฉพาะโดเมน Staging
- ขอสิทธิ์ Bluetooth ตอนผู้ใช้กดเลือกเครื่องพิมพ์เท่านั้น
- แสดงเฉพาะเครื่องที่จับคู่ไว้ใน Android แล้ว และส่งหน้าทดสอบแบบ raster ESC/POS
- ไม่มีบัญชีผู้ใช้ รหัสผ่าน หรือข้อมูลลูกค้าฝังอยู่ใน APK
- ไม่มีการเชื่อมต่อ Production

## สร้าง APK ทดสอบ

ติดตั้ง Android Studio รุ่นล่าสุดพร้อม Android SDK Platform 35 แล้วเปิดโฟลเดอร์ `android-app` จากนั้นเลือก **Build > Build APK(s)** หรือรัน:

```sh
./gradlew :app:assembleDebug
```

ไฟล์ที่ได้คือ `app/build/outputs/apk/debug/app-debug.apk` ใช้ติดตั้งเพื่อทดสอบภายในเท่านั้น ยังไม่ใช่ APK ที่เซ็นสำหรับปล่อยใช้งานจริง

## ทดสอบ PT-280

1. เปิด Bluetooth และจับคู่ `PT-280_7AA9` ในการตั้งค่า Android ก่อน
2. ติดตั้ง APK และกดปุ่ม **เครื่องพิมพ์ 58 มม.**
3. อนุญาต Bluetooth เมื่อระบบถาม เลือกชื่อเครื่อง แล้วแอปจะส่งหน้าทดสอบทันที

หากไม่พบชื่อเครื่อง แปลว่ายังไม่ได้จับคู่ในระดับ Android หรือเครื่องใช้โหมด Bluetooth Low Energy ที่ไม่ใช่ Classic SPP ต้องตรวจคู่มือหรือรุ่นจริงก่อนเพิ่มโปรไฟล์
