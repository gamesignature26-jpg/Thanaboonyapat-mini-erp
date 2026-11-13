/* 58 mm ESC/POS raster printing over a user-selected BLE GATT connection. */
(() => {
'use strict';

const dialog = document.getElementById('printer-dialog');
const form = document.getElementById('printer-form');
const status = document.getElementById('printer-status');
let device;
let characteristic;
let printing = false;

const profiles = [
    {id: 'generic-ble-58', name: 'เครื่อง 58 มม. ทั่วไป (BLE / ESC-POS)', mode: 'ble', guide: 'เชื่อมต่อจาก Chrome/Android ได้ หากเครื่องรองรับ Bluetooth Low Energy (BLE) และ ESC/POS; ใส่ UUID จากคู่มือหรือผู้ขาย'},
    {id: 'generic-classic-58', name: 'เครื่อง 58 มม. ทั่วไป (Bluetooth Classic)', mode: 'bridge', guide: 'Bluetooth Classic (SPP) ต้องใช้ Print Bridge หรือแอป Android ของผู้ผลิต เว็บเบราว์เซอร์เชื่อมต่อโดยตรงไม่ได้'},
    {id: 'star-tsp654iibi', name: 'Star TSP654IIBI', mode: 'bridge', guide: 'ใช้ StarPRNT/Print Bridge ตามวิธีเชื่อมต่อของเครื่อง; เลือก BLE ได้เมื่อคู่มือของรุ่นย่อยรองรับ GATT ESC/POS'},
    {id: 'star-tsp143iiilan', name: 'Star TSP143IIILAN (Ethernet)', mode: 'bridge', guide: 'Ethernet ต้องส่งผ่าน Print Bridge ในเครือข่ายร้าน ไม่สามารถเปิด TCP ไปที่เครื่องพิมพ์จากเว็บโดยตรง'},
    {id: 'star-mpop', name: 'Star mPOP', mode: 'bridge', guide: 'ใช้ StarPRNT/Print Bridge หรือแอปผู้ผลิตตามรุ่นและระบบปฏิบัติการ'},
    {id: 'star-mc-print3', name: 'Star mC-Print3', mode: 'bridge', guide: 'แนะนำ StarPRNT/Print Bridge สำหรับ LAN หรือ Bluetooth Classic'},
    {id: 'epson-tm-t20ii', name: 'Epson TM-T20II (Ethernet)', mode: 'bridge', guide: 'Ethernet ต้องใช้ Print Bridge หรือ Epson ePOS/ไดรเวอร์ที่ติดตั้งในเครือข่ายร้าน'},
    {id: 'epson-tm-t88v', name: 'Epson TM-T88V (Ethernet)', mode: 'bridge', guide: 'Ethernet ต้องใช้ Print Bridge หรือ Epson ePOS/ไดรเวอร์ที่ติดตั้งในเครือข่ายร้าน'},
    {id: 'epson-tm-m30', name: 'Epson TM-m30', mode: 'bridge', guide: 'เลือกรูปแบบเชื่อมต่อให้ตรงรุ่นย่อย; BLE ต้องยืนยัน UUID และ ESC/POS ก่อนใช้งานจริง'},
    {id: 'sunmi', name: 'Sunmi', mode: 'bridge', guide: 'ใช้แอป Android/Print Bridge ของ Sunmi; เว็บไม่สามารถเข้าถึง Bluetooth Classic หรือเครื่องพิมพ์ในตัวโดยตรง'},
    {id: 'posiflex-6900', name: 'Posiflex 6900', mode: 'bridge', guide: 'เชื่อมต่อผ่าน Print Bridge/ไดรเวอร์ของ Posiflex ตามพอร์ตที่ติดตั้ง'},
    {id: 'xprinter-xp-q800', name: 'XPrinter XP-Q800', mode: 'bridge', guide: 'ใช้ Print Bridge สำหรับ USB, LAN หรือ Bluetooth Classic; ตรวจคำสั่ง ESC/POS กับตัวแทนจำหน่าย'},
    {id: 'gp-58130iic', name: 'GP-58130IIC', mode: 'bridge', guide: 'รุ่นทั่วไปมักเป็น Bluetooth Classic จึงต้องใช้ Print Bridge หรือแอปผู้ผลิต'},
    {id: 'gp-u80300i', name: 'GP-U80300I', mode: 'bridge', guide: 'ต้องตรวจพอร์ตของรุ่นจริงและใช้ Print Bridge หากเป็น USB, LAN หรือ Bluetooth Classic'},
    {id: 'gp-l80250i', name: 'GP-L80250I', mode: 'bridge', guide: 'ต้องตรวจพอร์ตของรุ่นจริงและใช้ Print Bridge หากเป็น USB, LAN หรือ Bluetooth Classic'},
    {id: 'a4-browser', name: 'เครื่องพิมพ์ A4 ผ่านหน้าต่างพิมพ์', mode: 'browser', guide: 'ใช้ปุ่ม A4 ในเอกสาร แล้วเลือกเครื่องพิมพ์จากหน้าต่างพิมพ์ของเบราว์เซอร์'},
    {id: 'custom', name: 'รุ่นอื่น ๆ / กำหนดเอง', mode: 'ble', guide: 'ใช้เมื่อยืนยันแล้วว่าเครื่องรองรับ BLE GATT และ ESC/POS; หากเป็น Bluetooth Classic, USB หรือ LAN ให้ใช้ Print Bridge'},
];
const model = document.getElementById('printer-model');
const nameInput = document.getElementById('printer-name');
const autoPrint = document.getElementById('printer-auto-print');
const guide = document.getElementById('printer-connection-guide');
const serviceInput = document.getElementById('printer-service');
const writeInput = document.getElementById('printer-write');
const settingsKey = 'thanabunyapat-printer-preferences-v1';

function selectedProfile() {
    return profiles.find(profile => profile.id === model.value) || profiles[0];
}

function savePreferences() {
    try {
        localStorage.setItem(settingsKey, JSON.stringify({
            name: nameInput.value.trim(), model: model.value, autoPrint: autoPrint.checked,
            serviceUuid: serviceInput.value.trim(), writeUuid: writeInput.value.trim(),
        }));
    } catch (_) { /* Printer preferences are optional per browser/device. */ }
}

function updateProfile() {
    const profile = selectedProfile();
    const usesBle = profile.mode === 'ble';
    guide.textContent = profile.guide;
    serviceInput.disabled = !usesBle;
    writeInput.disabled = !usesBle;
    serviceInput.closest('.field').hidden = !usesBle;
    writeInput.closest('.field').hidden = !usesBle;
    form.querySelector('button[type="submit"]').disabled = !usesBle || !navigator.bluetooth || printing;
    savePreferences();
}

function loadPreferences() {
    model.replaceChildren(...profiles.map(profile => {
        const option = document.createElement('option');
        option.value = profile.id;
        option.textContent = profile.name;
        return option;
    }));
    try {
        const stored = JSON.parse(localStorage.getItem(settingsKey) || '{}');
        nameInput.value = stored.name || '';
        model.value = profiles.some(profile => profile.id === stored.model) ? stored.model : 'generic-ble-58';
        autoPrint.checked = stored.autoPrint !== false;
        serviceInput.value = stored.serviceUuid || '';
        writeInput.value = stored.writeUuid || '';
    } catch (_) {
        model.value = 'generic-ble-58';
    }
    updateProfile();
}

loadPreferences();
model.addEventListener('change', updateProfile);
[nameInput, autoPrint, serviceInput, writeInput].forEach(element => element.addEventListener('change', savePreferences));

function connected() {
    return Boolean(device?.gatt.connected && characteristic);
}

function disconnect() {
    const previous = device;
    device = undefined;
    characteristic = undefined;
    previous?.gatt.disconnect();
    status.textContent = 'ยังไม่ได้เชื่อมต่อ';
}

function open() {
    if (connected()) {
        status.textContent = 'เชื่อมต่อแล้ว ' + (device.name || 'เครื่องพิมพ์');
    } else {
        status.textContent = navigator.bluetooth
            ? 'ใช้ UUID จากคู่มือเครื่องพิมพ์ BLE ที่รองรับ ESC/POS'
            : 'เบราว์เซอร์นี้ไม่มี Web Bluetooth ให้ใช้ปุ่มพิมพ์ 58 มม. หรือ A4';
    }
    updateProfile();
    if (!dialog.open) dialog.showModal();
}

function uuid(value) {
    const id = value.trim().toLowerCase();
    if (/^[0-9a-f]{4}$/.test(id)) return Number.parseInt(id, 16);
    if (/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(id)) return id;
    throw Error('UUID ต้องเป็นเลขฐานสิบหก 4 หลัก หรือ UUID แบบเต็ม');
}

form.addEventListener('submit', async event => {
    event.preventDefault();
    event.stopImmediatePropagation();
    const button = event.submitter;
    if (selectedProfile().mode !== 'ble' || !navigator.bluetooth || printing || button.disabled) return;
    button.disabled = true;
    let selected;
    try {
        const serviceId = uuid(form.elements.service_uuid.value);
        const characteristicId = uuid(form.elements.write_uuid.value);
        status.textContent = 'เลือกเครื่องพิมพ์ในหน้าต่าง Bluetooth';
        selected = await navigator.bluetooth.requestDevice({acceptAllDevices: true, optionalServices: [serviceId]});
        if (!dialog.open) return;
        disconnect();
        const server = await selected.gatt.connect();
        const service = await server.getPrimaryService(serviceId);
        const writable = await service.getCharacteristic(characteristicId);
        if (!writable.properties.write && !writable.properties.writeWithoutResponse) {
            throw Error('ช่องทาง BLE นี้ไม่รองรับการส่งข้อมูล');
        }
        if (!dialog.open) {
            selected.gatt.disconnect();
            return;
        }
        device = selected;
        characteristic = writable;
        savePreferences();
        selected.addEventListener('gattserverdisconnected', () => {
            if (device === selected) disconnect();
        }, {once: true});
        status.textContent = 'เชื่อมต่อแล้ว ' + (device.name || 'เครื่องพิมพ์');
    } catch (error) {
        if (selected && selected !== device) selected.gatt.disconnect();
        status.textContent = error.name === 'NotFoundError'
            ? 'ยังไม่ได้เลือกเครื่องพิมพ์'
            : 'เชื่อมต่อไม่สำเร็จ: ' + error.message;
    } finally {
        button.disabled = false;
    }
});

document.getElementById('printer-close').addEventListener('click', () => dialog.close());
document.getElementById('printer-disconnect').addEventListener('click', disconnect);
document.getElementById('printer-test').addEventListener('click', async () => {
    if (!connected()) {
        open();
        status.textContent = 'เชื่อมต่อเครื่องพิมพ์ BLE ก่อน แล้วจึงทดสอบพิมพ์';
        return;
    }
    try {
        await print({number: 'TEST-58MM', kind: 'receipt', issued: new Date().toLocaleString('th-TH'), snapshot: {
            company: {legal_name: 'Thanabunyapat ERP', address: 'ข้อมูลทดสอบเท่านั้น', branch: '', phone: '', receipt_footer: 'หน้าทดสอบพิมพ์'},
            sale: {id: '-', vat_price_mode: 'inclusive', customer_name: 'ทดสอบเครื่องพิมพ์', customer_address: '', vat_rate: '7', vat: '0.00', subtotal: '0.00', total: '0.00', lines: []},
        }});
        status.textContent = 'ส่งหน้าทดสอบไปยังเครื่องพิมพ์แล้ว';
    } catch (error) {
        status.textContent = 'ทดสอบพิมพ์ไม่สำเร็จ: ' + error.message;
    }
});

function documentLines({number, kind, issued, snapshot}) {
    const {company, sale, order, payment} = snapshot;
    const inclusive = sale.vat_price_mode === 'inclusive';
    return [
        kind === 'tax_invoice' ? 'ใบกำกับภาษี (ร่างทดสอบ)' : 'ใบเสร็จรับเงิน (ร่างทดสอบ)',
        'ข้อมูลทดสอบเท่านั้น', number + ' · ' + issued, 'อ้างอิงบิล #' + sale.id,
        company.legal_name, company.address,
        company.tax_id ? 'เลขผู้เสียภาษีผู้ขาย ' + company.tax_id : '',
        company.branch, company.phone ? 'โทร ' + company.phone : '',
        'ผู้ซื้อ ' + sale.customer_name, sale.customer_address,
        sale.customer_tax_id ? 'เลขผู้เสียภาษีผู้ซื้อ ' + sale.customer_tax_id : '',
        sale.customer_branch ? (sale.customer_branch === '00000' ? 'สำนักงานใหญ่' : 'สาขา ' + sale.customer_branch) : '',
        inclusive ? 'ราคาต่อหน่วยรวม VAT' : 'ราคาต่อหน่วยก่อน VAT',
        ...sale.lines.flatMap(line => [line.name, line.quantity + ' × ' + line.price + ' = ' + line.total]),
        ...(order ? ['ส่วนลด ' + order.discount, 'ค่าจัดส่ง ' + order.shipping_fee] : []),
        'ยอดก่อน VAT ' + sale.subtotal, 'VAT ' + sale.vat_rate + '%  ' + sale.vat,
        'ยอดรวม ' + sale.total + ' บาท',
        ...(payment ? ['รับชำระ ' + payment.amount + ' บาท', payment.method + ' · ' + payment.reference] : []),
        company.receipt_footer,
    ].filter(Boolean);
}

function rasterize(lines) {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d', {willReadFrequently: true});
    const width = 384;
    const lineHeight = 25;
    const font = '18px Tahoma, "Noto Sans Thai", sans-serif';
    ctx.font = font;
    const rows = [];
    const segmenter = new Intl.Segmenter('th', {granularity: 'grapheme'});
    for (const line of lines) {
        let row = '';
        for (const {segment} of segmenter.segment(line)) {
            if (row && ctx.measureText(row + segment).width > width - 16) {
                rows.push(row);
                row = '';
            }
            row += segment;
        }
        rows.push(row);
    }
    canvas.width = width;
    canvas.height = rows.length * lineHeight + 16;
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#000';
    ctx.font = font;
    rows.forEach((row, i) => ctx.fillText(row, 8, 22 + i * lineHeight));
    return ctx.getImageData(0, 0, canvas.width, canvas.height);
}

async function print(documentData) {
    if (!connected()) throw Error('กรุณาเชื่อมต่อเครื่องพิมพ์ก่อน');
    if (printing) throw Error('กำลังส่งงานพิมพ์อยู่');
    printing = true;
    const target = characteristic;
    const write = target.properties.write
        ? bytes => target.writeValueWithResponse(bytes)
        : async bytes => {
            await target.writeValueWithoutResponse(bytes);
            await new Promise(resolve => setTimeout(resolve, 12));
        };
    try {
        const {data, width, height} = rasterize(documentLines(documentData));
        const stride = width / 8;
        await write(Uint8Array.of(0x1b, 0x40));
        for (let y = 0; y < height; y += 96) {
            const rows = Math.min(96, height - y);
            const packet = new Uint8Array(8 + stride * rows);
            packet.set([0x1d, 0x76, 0x30, 0, stride, 0, rows, 0]);
            for (let row = 0; row < rows; row++) {
                for (let x = 0; x < width; x++) {
                    if (data[((y + row) * width + x) * 4] < 180) {
                        packet[8 + row * stride + (x >> 3)] |= 0x80 >> (x % 8);
                    }
                }
            }
            for (let offset = 0; offset < packet.length; offset += 20) {
                await write(packet.subarray(offset, offset + 20));
            }
        }
        await write(Uint8Array.of(10, 10, 10));
    } finally {
        printing = false;
    }
}

window.erpPrinter = {open, connected, disconnect, print};
})();
