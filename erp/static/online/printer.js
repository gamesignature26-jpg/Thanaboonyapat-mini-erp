/* 58 mm ESC/POS raster printing over a user-selected BLE GATT connection. */
(() => {
'use strict';

const dialog = document.getElementById('printer-dialog');
const form = document.getElementById('printer-form');
const status = document.getElementById('printer-status');
let device;
let characteristic;
let printing = false;

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
    form.querySelector('button[type="submit"]').disabled = !navigator.bluetooth || printing;
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
    if (!navigator.bluetooth || printing || button.disabled) return;
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
