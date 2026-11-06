/* Thanabunyapat One: server-backed web app. No localStorage for business data. */
(() => {
'use strict';
const root = document.getElementById('root');
const toast = document.getElementById('toast');
const state = {user:null,csrf:null,view:'dashboard',products:[],customers:[],sales:[],orders:[],expenses:[],summary:null,cart:new Map(),wh:[],vatRate:7,busy:false};
const labels = {dashboard:'ภาพรวมธุรกิจ',pos:'ขายหน้าร้าน POS',wholesale:'ขายส่ง / จัดส่ง',sales:'บิลขาย / ลูกหนี้',inventory:'สินค้าและสต๊อก',customers:'ลูกค้า',expenses:'ค่าใช้จ่าย',reports:'รายงาน'};
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>x===null||x===undefined?'—':new Intl.NumberFormat('th-TH',{style:'currency',currency:'THB'}).format(Number(x||0));
const num=x=>Number(x||0);
const moneyInput=x=>num(x).toFixed(2);
const uuid=()=>crypto.randomUUID();
const f=form=>Object.fromEntries(new FormData(form));
function warn(msg){toast.textContent=msg;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),4000);}
function formatDate(x){if(!x)return '—';const d=new Date(x);return Number.isNaN(d.getTime())?'—':new Intl.DateTimeFormat('th-TH',{dateStyle:'short',timeZone:'Asia/Bangkok'}).format(d);}
function opt(v,t,selected=''){return `<option value="${esc(v)}" ${String(v)===String(selected)?'selected':''}>${esc(t)}</option>`;}
function field(label,name,type='text',value='',more=''){return `<div class="field"><label for="${esc(name)}">${esc(label)}</label><input id="${esc(name)}" name="${esc(name)}" type="${esc(type)}" value="${esc(value)}" ${more}></div>`;}
function customerSelect(name='customer_id'){return `<div class="field"><label>ลูกค้า</label><select name="${esc(name)}" required><option value="">— เลือกลูกค้า —</option>${state.customers.map(c=>opt(c.id,c.name)).join('')}</select><small>หากไม่มีลูกค้า ให้เพิ่มในเมนูลูกค้าก่อน</small></div>`;}
function methodSelect(){return `<div class="field"><label>การชำระ</label><select name="method">${opt('cash','เงินสด')}${opt('transfer','โอนเงิน')}${opt('credit','ขายเชื่อ / ค้างชำระ')}</select></div>`;}
function productSelect(name='product_id'){return `<select name="${name}" required><option value="">เลือกสินค้า</option>${state.products.map(p=>opt(p.id,`${p.name} • เหลือ ${p.stock}`)).join('')}</select>`;}
async function api(path,options={}){
 const method=options.method||'GET';const headers={'Accept':'application/json'};
 if(method!=='GET'){headers['Content-Type']='application/json';if(!state.csrf)await getCsrf();headers['X-CSRFToken']=state.csrf;}
 const r=await fetch(path,{method,headers,credentials:'same-origin',body:options.body?JSON.stringify(options.body):undefined});
 const json=r.status===204?{}:await r.json().catch(()=>({}));
 if(!r.ok){if(r.status===401){state.user=null;showLogin();}throw Error(json.error||`เซิร์ฟเวอร์แจ้งข้อผิดพลาด ${r.status}`);}
 return json;
}
async function getCsrf(){const r=await fetch('/auth/csrf',{credentials:'same-origin'});if(!r.ok)throw Error('ไม่สามารถขอ CSRF token');state.csrf=(await r.json()).csrf_token;}
function showLogin(){root.innerHTML=`<div class="login-page"><div class="card login"><div class="row"><div class="logo">TB</div><h1>Thanabunyapat One</h1></div><p>ระบบขายและจัดส่งออนไลน์ · หจก. ธนาบุณยภัทร</p><form id="login-form">${field('ชื่อผู้ใช้','username','text','', 'autocomplete="username" required maxlength="80"')}${field('รหัสผ่าน','password','password','','autocomplete="current-password" required')}<button class="btn block">เข้าสู่ระบบ</button></form><div class="small-note">ระบบทดสอบที่เชื่อมฐานข้อมูลกลาง ไม่ใช่ระบบบัญชีคู่หรือใบกำกับภาษีที่ใช้ตามกฎหมาย</div></div></div>`;}
function navItems(){const role=state.user.role;const allowed={admin:Object.keys(labels),sales:['dashboard','pos','wholesale','sales','inventory','customers','reports'],warehouse:['dashboard','wholesale','inventory','reports'],accountant:['dashboard','wholesale','sales','inventory','customers','expenses','reports']}[role]||['dashboard'];return Object.entries(labels).filter(([v])=>allowed.includes(v)).map(([v,t])=>`<button type="button" data-nav="${v}" class="${state.view===v?'active':''}">${esc(t)}</button>`).join('');}
function shell(){root.innerHTML=`<div class="layout"><aside><div class="brand"><div class="logo">TB</div><div><strong>THANABUNYAPAT</strong><small>ONE · ออนไลน์</small></div></div><div class="nav" id="nav">${navItems()}</div><div class="foot">ข้อมูลกลางบนเซิร์ฟเวอร์<br>ใช้เฉพาะบัญชีพนักงานที่ได้รับอนุญาต</div></aside><main><header><div><div class="muted">SMART BUSINESS WORKSPACE</div><h1 id="title">${labels[state.view]}</h1></div><div class="row"><span class="pill">● SERVER MODE</span><button class="btn secondary slim" id="logout">ออกจากระบบ</button></div></header><div class="alert"><b>ระบบทดลองก่อนเปิดจริง</b> — ห้ามใช้ใบสรุปการขายแทนใบกำกับภาษี และต้องตรวจสอบการตั้งค่า HTTPS ฐานข้อมูล การสำรองข้อมูล และสิทธิ์พนักงานก่อนใช้งานจริง</div><div id="view"></div></main></div>`;}
async function refresh(){
 if(!state.user)return;
 try{
  const needs=state.view;
  const base=['dashboard','reports','pos','wholesale','sales','inventory','customers'].includes(needs);
  if(base){
   const results=await Promise.allSettled([api('/products'),api('/customers'),api('/api/online/dashboard'),api('/api/online/sales'),api('/api/online/orders'),api('/api/online/config')]);
   const keys=['products','customers','summary','sales','orders','vatRate'];
   results.forEach((res,i)=>{if(res.status==='fulfilled')state[keys[i]]=i===2?res.value:i===5?Number(res.value.vat_rate):res.value.items;else if(!String(res.reason).includes('401'))console.warn(keys[i],res.reason);});
  }
  if(needs==='expenses')state.expenses=(await api('/api/online/expenses')).items;
  render();
 }catch(err){warn(err.message);}
}
function navigate(v){state.view=v;shell();refresh();}
function card(label,val,sub){return `<div class="card metric"><small>${esc(label)}</small><strong>${esc(val)}</strong><small>${esc(sub)}</small></div>`;}
function summary(){const s=state.summary||{};return `<div class="grid g4">${card('ยอดขายวันนี้',fmt(s.today_total),'รวม VAT ตามรายการขาย')}${card('ยอดขายสะสม',fmt(s.sales_total),'ยอดการขาย ไม่ใช่ยอดรับเงิน')}${card('ลูกหนี้คงเหลือ',fmt(s.receivable),'ยังไม่ได้รับชำระ')}${card('ยอดสินค้าคงเหลือ',String(s.stock_units??0),'จำนวนหน่วยทุกสินค้า')}</div>`;}
function dashboard(){const s=state.summary||{};return `${summary()}<div class="grid g2"><div class="card"><h2>งานจัดส่งที่ยังไม่เสร็จ</h2><div class="row space"><strong>${esc(s.pending_delivery||0)} ออเดอร์</strong><button data-nav="wholesale" class="btn slim">จัดการจัดส่ง</button></div></div><div class="card"><h2>ค่าใช้จ่ายที่บันทึก</h2><strong>${fmt(s.expenses_total)}</strong><p>ไม่ใช่ตัวเลขกำไรสุทธิ เพราะยังไม่มีต้นทุนสินค้าขายและบัญชีคู่</p></div></div><div class="card"><h2>ยอดขายล่าสุด</h2>${tableSales(state.sales.slice(0,7),false)}</div>`;}
function pos(){const entries=[...state.cart].map(([id,q])=>({p:state.products.find(x=>x.id===id),q})).filter(x=>x.p&&x.q>0);const total=entries.reduce((a,{p,q})=>a+num(p.price)*q,0);const tax=Math.round(total*state.vatRate)/100;return `<div class="grid g2"><div class="card"><h2>เลือกสินค้า</h2><div class="products">${state.products.map(p=>`<button class="product" data-add="${p.id}" ${p.stock<=0?'disabled':''}><b>${esc(p.name)}</b><small>${esc(p.sku)} · สต๊อก ${p.stock}</small><strong>${fmt(p.price)}</strong></button>`).join('')||'<div class="empty">ยังไม่มีสินค้า ให้เพิ่มในเมนูสินค้า</div>'}</div></div><div class="card"><h2>ตะกร้าขายหน้าร้าน</h2>${entries.map(({p,q})=>`<div class="line"><div><b>${esc(p.name)}</b><small> ${fmt(p.price)} × ${q}</small></div><div class="row"><button class="btn secondary slim" data-dec="${p.id}">−</button><b>${q}</b><button class="btn secondary slim" data-add="${p.id}">+</button></div></div>`).join('')||'<div class="empty">ยังไม่มีสินค้าในตะกร้า</div>'}<div class="summary"><div><span>ยอดสินค้า</span><b>${fmt(total)}</b></div><div><span>VAT ประมาณการ ${state.vatRate}%</span><b>${fmt(tax)}</b></div><div class="total"><span>ยอดประมาณการ</span><b>${fmt(total+tax)}</b></div></div><form id="pos-form">${customerSelect()}${methodSelect()}<button class="btn block" ${!entries.length?'disabled':''}>บันทึกการขายและตัดสต๊อก</button></form><div class="small-note">ราคาและ VAT คำนวณยืนยันบนเซิร์ฟเวอร์อีกครั้งก่อนบันทึก</div></div></div>`;}
function whTotal(){const subtotal=state.wh.reduce((t,x)=>t+x.quantity*num(x.unit_price),0);return fmt(subtotal);}
function wholesale(){if(!['admin','sales'].includes(state.user.role))return `<div class="card"><h2>ติดตามออเดอร์ขายส่ง / จัดส่ง</h2>${orderTable()}</div>`;const rows=state.wh.map((x,i)=>{const p=state.products.find(p=>p.id===x.product_id);return `<tr><td>${esc(p?.name||'?')}</td><td class="num">${x.quantity}</td><td class="num">${fmt(x.unit_price)}</td><td class="num">${fmt(x.quantity*num(x.unit_price))}</td><td><button class="btn secondary slim" data-whdel="${i}">ลบ</button></td></tr>`;}).join('');return `<div class="grid g2"><div class="card"><h2>สร้างออเดอร์ขายส่ง / จัดส่ง</h2><form id="wh-add-form"><div class="field"><label>สินค้า</label>${productSelect('product_id')}</div><div class="grid g2">${field('จำนวนแพ็ค / หน่วย','quantity','number','1','min="1" step="1" required')}${field('ราคาส่งต่อหน่วย ก่อน VAT','unit_price','number','','min="0.01" step="0.01" required')}</div><button class="btn secondary block">เพิ่มสินค้าในออเดอร์</button></form><div class="tablewrap desktop-table"><table><thead><tr><th>สินค้า</th><th class="num">จำนวน</th><th class="num">ราคาส่ง</th><th class="num">รวม</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="5" class="empty">ยังไม่มีสินค้า</td></tr>'}</tbody></table></div><div class="summary"><div><b>ยอดสินค้าก่อนส่วนลด / VAT</b><strong>${whTotal()}</strong></div></div></div><div class="card"><h2>ข้อมูลลูกค้าและการจัดส่ง</h2><form id="wh-form">${customerSelect()}<div class="field"><label>รูปแบบรับสินค้า</label><select name="delivery_mode">${opt('delivery','จัดส่งถึงร้าน')}${opt('pickup','รับเองที่โกดัง')}</select></div>${field('วันนัดส่ง','delivery_date','date',new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()))}${field('ที่อยู่จัดส่ง','address','text','','maxlength="1000"')}${field('โทรศัพท์ติดต่อ','phone','tel','','maxlength="30"')}${field('ชื่อคนขับรถ','driver','text','','maxlength="100"')}<div class="grid g2">${field('ส่วนลด (บาท)','discount','number','0.00','min="0" step="0.01" required')}${field('ค่าจัดส่ง (บาท)','shipping_fee','number','0.00','min="0" step="0.01" required')}</div>${methodSelect()}${field('หมายเหตุ','note','text','','maxlength="600"')}<button class="btn block" ${!state.wh.length?'disabled':''}>ยืนยันออเดอร์ขายส่ง</button></form><div class="small-note">ยืนยันแล้วตัดสต๊อกทันที และสถานะจัดส่งสามารถติดตามต่อด้านล่าง</div></div></div><div class="card"><h2>สถานะออเดอร์จัดส่ง</h2>${orderTable()}</div>`;}
const statusName={pending:'รอเตรียม',packing:'กำลังจัดสินค้า',out_for_delivery:'กำลังนำส่ง',delivered:'ส่งสำเร็จ',ready:'พร้อมรับ',picked_up:'รับสินค้าแล้ว'};
function orderTable(){if(!state.orders.length)return '<div class="empty">ยังไม่มีออเดอร์ขายส่ง</div>';return `<div class="tablewrap"><table><thead><tr><th>เลขบิล</th><th>ลูกค้า</th><th>วิธีรับ</th><th>ยอด</th><th>สถานะ</th><th></th></tr></thead><tbody>${state.orders.map(o=>{const done=['delivered','picked_up'].includes(o.status);return `<tr><td>#${o.id}</td><td>${esc(o.customer)}</td><td>${o.mode==='pickup'?'รับเอง':'จัดส่ง'}</td><td>${fmt(o.total)}</td><td><span class="status ${esc(o.status)}">${esc(statusName[o.status]||o.status)}</span></td><td><div class="row">${done?'':`<button class="btn slim" data-next="${o.id}">อัปเดตขั้นต่อไป</button>`}<button class="btn secondary slim" data-note="${o.id}">พิมพ์ใบส่งสินค้า</button></div></td></tr>`;}).join('')}</tbody></table></div>`;}
function tableSales(items,allowPay=true){if(!items.length)return '<div class="empty">ยังไม่มีรายการขาย</div>';return `<div class="tablewrap"><table><thead><tr><th>เลข</th><th>วันที่</th><th>ลูกค้า</th><th class="num">รวม</th><th class="num">ค้างชำระ</th><th>ดำเนินการ</th></tr></thead><tbody>${items.map(s=>`<tr><td>#${s.id}</td><td>${formatDate(s.date)}</td><td>${esc(s.customer)}</td><td class="num">${fmt(s.total)}</td><td class="num">${fmt(s.balance)}</td><td><div class="row"><button class="btn secondary slim" data-print="${s.id}">พิมพ์สรุป</button>${allowPay&&num(s.balance)>0&&['admin','accountant'].includes(state.user.role)?`<button class="btn slim" data-pay="${s.id}">รับชำระ</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>`;}
function sales(){return `<div class="card"><h2>บิลขายและลูกหนี้</h2><p>ทุกบิลมาจากฐานข้อมูลกลาง · รับชำระบางส่วนได้</p>${tableSales(state.sales)}</div>`;}
function inventory(){const canWrite=['admin','warehouse'].includes(state.user.role);return `<div class="grid g2">${canWrite?`<div class="card"><h2>เพิ่มสินค้า</h2><form id="product-form">${field('รหัสสินค้า SKU','sku','text','','required maxlength="80"')}${field('ชื่อสินค้า','name','text','','required maxlength="200"')}${field('ราคาขายก่อน VAT (บาท)','price','number','','required min="0" step="0.01"')}<button class="btn">บันทึกสินค้า</button></form></div><div class="card"><h2>รับเข้า / ปรับสต๊อก</h2><form id="stock-form"><div class="field"><label>สินค้า</label>${productSelect()}</div>${field('จำนวนเพิ่ม (+) หรือลด (−)','delta','number','1','step="1" required')}${field('เหตุผลปรับสต๊อก','reason','text','','required maxlength="200"')}<button class="btn">บันทึกสต๊อก</button></form></div>`:''}</div><div class="card"><h2>สินค้าคงเหลือ</h2><div class="tablewrap"><table><thead><tr><th>SKU</th><th>สินค้า</th><th class="num">ราคา</th><th class="num">คงเหลือ</th></tr></thead><tbody>${state.products.map(p=>`<tr><td>${esc(p.sku)}</td><td>${esc(p.name)}</td><td class="num">${fmt(p.price)}</td><td class="num">${p.stock}</td></tr>`).join('')}</tbody></table></div></div>`;}
function customers(){return `<div class="grid g2"><div class="card"><h2>เพิ่มลูกค้า</h2><form id="customer-form">${field('ชื่อร้านค้า / ลูกค้า','name','text','','required maxlength="200"')}${field('ที่อยู่','address','text','','required maxlength="1000"')}${field('เลขผู้เสียภาษี 13 หลัก (ถ้ามี)','tax_id','text','','pattern="[0-9]{13}" maxlength="13"')}<button class="btn">บันทึกลูกค้า</button></form></div><div class="card"><h2>ลูกค้าทั้งหมด</h2><div class="tablewrap"><table><tbody>${state.customers.map(c=>`<tr><td><b>${esc(c.name)}</b><div class="muted">${esc(c.address)}</div></td></tr>`).join('')}</tbody></table></div></div></div>`;}
function expenses(){return `<div class="grid g2"><div class="card"><h2>บันทึกค่าใช้จ่าย</h2><p>ใช้ติดตามรายจ่าย ไม่ใช่ลงบัญชีคู่</p><form id="expense-form">${field('หมวดหมู่','category','text','ขนส่ง','required maxlength="80"')}${field('รายละเอียด','description','text','','required maxlength="250"')}${field('จำนวนเงิน (บาท)','amount','number','','min="0.01" step="0.01" required')}<div class="field"><label>ชำระโดย</label><select name="method">${opt('cash','เงินสด')}${opt('transfer','โอนเงิน')}</select></div><button class="btn">บันทึกรายจ่าย</button></form></div><div class="card"><h2>รายจ่ายล่าสุด</h2><div class="tablewrap"><table><tbody>${state.expenses.map(x=>`<tr><td>${esc(x.category)}<div class="muted">${esc(x.description)}</div></td><td class="num">${fmt(x.amount)}</td></tr>`).join('')}</tbody></table></div></div></div>`;}
function reports(){const s=state.summary||{};return `${summary()}<div class="card"><h2>รายงานการจัดส่งและค่าใช้จ่าย</h2><div class="grid g2">${card('รอส่งสินค้า',String(s.pending_delivery||0),'สถานะยังไม่สิ้นสุด')}${card('รายจ่ายที่บันทึก',fmt(s.expenses_total),'ไม่รวมต้นทุนสินค้าขาย')}</div><div class="alert">ยังไม่มีระบบต้นทุนสินค้า กำไรขาดทุนบัญชีคู่ งบการเงิน และรายงานภาษีที่ผ่านการรับรอง ห้ามนำยอดรวมนี้ไปอ้างว่าเป็นกำไรสุทธิ</div></div>`;}
function render(){if(!state.user)return;const view=$('view');if(!view)return;const map={dashboard,pos,wholesale,sales,inventory,customers,expenses,reports};view.innerHTML=(map[state.view]||dashboard)();const t=$('title');if(t)t.textContent=labels[state.view];const nav=$('nav');if(nav)nav.innerHTML=navItems();}
async function doLogin(form){const values=f(form);await getCsrf();const r=await api('/auth/login',{method:'POST',body:{username:values.username,password:values.password}});state.csrf=r.csrf_token;state.user=await api('/auth/me');shell();await refresh();}
async function confirmSale(kind,form){
 const v=f(form);
 const lines=kind==='pos'?[...state.cart].filter(([id,q])=>q>0).map(([id,q])=>({product_id:Number(id),quantity:q})):state.wh.map(x=>({...x}));
 if(!lines.length)throw Error('กรุณาเลือกสินค้าก่อน');
 const body={kind,customer_id:Number(v.customer_id),lines,method:v.method,delivery_mode:kind==='pos'?'pickup':v.delivery_mode};
 if(kind==='wholesale')Object.assign(body,{delivery_date:v.delivery_date,address:v.address,phone:v.phone,driver:v.driver,discount:moneyInput(v.discount),shipping_fee:moneyInput(v.shipping_fee),note:v.note});
 if(kind==='wholesale'&&body.delivery_mode==='pickup')body.shipping_fee='0.00';
 // Keep only a SHA-256 fingerprint + idempotency key in session storage, never the order or PII.
 // A retry after a lost HTTP response uses the SAME key and cannot decrease stock twice.
 const bytes=new TextEncoder().encode(JSON.stringify(body));
 const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
 const slot='tb-online-pending-order-v1';
 let last=null;try{last=JSON.parse(sessionStorage.getItem(slot)||'null');}catch(_){/* ignore corrupted browser metadata */}
 const idempotency_key=last?.hash===hash?last.id:uuid();
 sessionStorage.setItem(slot,JSON.stringify({id:idempotency_key,hash}));
 const x=await api('/api/online/orders',{method:'POST',body:{...body,idempotency_key}});
 sessionStorage.removeItem(slot);
 state.cart.clear();state.wh=[];
 warn(`บันทึกบิล #${x.id} สำเร็จ`);navigate('sales');
}
async function send(form){if(state.busy)return;state.busy=true;const submit=form.querySelector('button[type=submit],button:not([type])');if(submit)submit.disabled=true;try{
 const id=form.id,v=f(form);
 if(id==='login-form')await doLogin(form);
 else if(id==='pos-form')await confirmSale('pos',form);
 else if(id==='wh-form')await confirmSale('wholesale',form);
 else if(id==='wh-add-form'){const p=state.products.find(x=>x.id===Number(v.product_id));const qty=Number(v.quantity);const price=Number(v.unit_price);if(!p||!Number.isInteger(qty)||qty<1||qty>p.stock||!Number.isFinite(price)||price<=0)throw Error('ตรวจสอบสินค้า จำนวนและราคาขายส่ง');const found=state.wh.find(x=>x.product_id===p.id);if(found)throw Error('รายการสินค้าซ้ำ โปรดลบรายการเดิมก่อน');state.wh.push({product_id:p.id,quantity:qty,unit_price:moneyInput(price)});render();}
 else if(id==='product-form'){await api('/products',{method:'POST',body:{sku:v.sku,name:v.name,price:moneyInput(v.price)}});warn('เพิ่มสินค้าแล้ว');await refresh();}
 else if(id==='stock-form'){await api('/stock/adjustments',{method:'POST',body:{product_id:Number(v.product_id),delta:Number(v.delta),reason:v.reason}});warn('ปรับสต๊อกแล้ว');await refresh();}
 else if(id==='customer-form'){await api('/customers',{method:'POST',body:{name:v.name,address:v.address,tax_id:v.tax_id||null}});warn('เพิ่มลูกค้าแล้ว');await refresh();}
 else if(id==='expense-form'){await api('/api/online/expenses',{method:'POST',body:{category:v.category,description:v.description,amount:moneyInput(v.amount),method:v.method}});warn('บันทึกรายจ่ายแล้ว');await refresh();}
 else if(id==='pay-form'){await api(`/api/online/sales/${Number(v.sale_id)}/payments`,{method:'POST',body:{amount:moneyInput(v.amount),method:v.method,reference:`webpay-${uuid()}`}});warn('บันทึกรับชำระแล้ว');await refresh();}
 }catch(err){warn(`ไม่สำเร็จ: ${err.message}`);}finally{state.busy=false;if(submit?.isConnected)submit.disabled=false;}}
function showPayment(id){const item=state.sales.find(s=>s.id===Number(id));if(!item)return;const el=$('view');el.insertAdjacentHTML('afterbegin',`<div class="card"><h2>รับชำระบิล #${id}</h2><p>ยอดค้าง ${fmt(item.balance)}</p><form id="pay-form"><input type="hidden" name="sale_id" value="${id}"><div class="grid g2">${field('จำนวนรับชำระ (บาท)','amount','number',item.balance,'min="0.01" step="0.01" required')}<div class="field"><label>รับชำระโดย</label><select name="method">${opt('cash','เงินสด')}${opt('transfer','โอนเงิน')}</select></div></div><button class="btn">บันทึกรับชำระ</button></form></div>`);window.scrollTo({top:0,behavior:'smooth'});}
async function printSale(id){const s=state.sales.find(x=>x.id===Number(id));if(!s)throw Error('ไม่พบบิล');const details=await api(`/sales/${Number(id)}`);const rows=(details.lines||[]).map(x=>`<tr><td>${esc(x.name)} × ${x.quantity}</td><td>${fmt(x.quantity*num(x.price))}</td></tr>`).join('');$('print-root').innerHTML=`<h2>หจก. ธนาบุณยภัทร</h2><p>ใบสรุปการขายตัวอย่าง<br>ไม่ใช่ใบกำกับภาษี<br>บิล #${s.id} วันที่ ${formatDate(s.date)}<br>ลูกค้า ${esc(s.customer)}</p><table>${rows}<tr><td>ยอดก่อน VAT</td><td>${fmt(s.subtotal)}</td></tr><tr><td>VAT</td><td>${fmt(s.vat)}</td></tr><tr><td><b>ยอดรวม</b></td><td><b>${fmt(s.total)}</b></td></tr><tr><td>รับชำระแล้ว</td><td>${fmt(s.paid)}</td></tr><tr><td>ค้างรับ</td><td>${fmt(s.balance)}</td></tr></table><p>เอกสารประกอบการตรวจสอบภายใน</p>`;window.print();}
async function printDelivery(id){
 const o=await api(`/api/online/orders/${Number(id)}`);
 const rows=(o.lines||[]).map(x=>`<tr><td>${esc(x.name)}<br><small>${esc(x.sku)}</small></td><td>${x.quantity}</td></tr>`).join('');
 $('print-root').innerHTML=`<h2>หจก. ธนาบุณยภัทร</h2><p><b>ใบส่งสินค้า (ตัวอย่าง)</b><br>ไม่ใช่ใบกำกับภาษี<br>เลขที่บิล #${o.id}<br>วันที่จัดส่ง ${esc(o.delivery_date||'—')}<br>ลูกค้า ${esc(o.customer)}<br>สถานที่ ${esc(o.address)}<br>ผู้ติดต่อ ${esc(o.phone)}<br>คนขับ ${esc(o.driver)}</p><table><thead><tr><th>สินค้า</th><th>จำนวน</th></tr></thead><tbody>${rows}</tbody></table><p>รับสินค้าครบถ้วน: __________________<br>วันที่รับ: __________________</p>`;
 window.print();
}
document.addEventListener('submit',event=>{if(!event.target.matches('form'))return;event.preventDefault();send(event.target);});
document.addEventListener('click',async event=>{
 const btn=event.target.closest('button');if(!btn)return;
 try{
 if(btn.dataset.nav){navigate(btn.dataset.nav);return;}
 if(btn.id==='logout'){await api('/auth/logout',{method:'POST',body:{}});state.user=null;state.csrf=null;showLogin();return;}
 if(btn.dataset.add){const id=Number(btn.dataset.add);const p=state.products.find(p=>p.id===id);if(!p)return;const qty=state.cart.get(id)||0;if(qty>=p.stock)throw Error('สินค้าไม่พอ');state.cart.set(id,qty+1);render();return;}
 if(btn.dataset.dec){const id=Number(btn.dataset.dec),qty=(state.cart.get(id)||0)-1;if(qty<=0)state.cart.delete(id);else state.cart.set(id,qty);render();return;}
 if(btn.dataset.whdel!==undefined){state.wh.splice(Number(btn.dataset.whdel),1);render();return;}
 if(btn.dataset.next){await api(`/api/online/orders/${Number(btn.dataset.next)}/advance`,{method:'POST',body:{}});warn('อัปเดตสถานะจัดส่งแล้ว');await refresh();return;}
 if(btn.dataset.pay){showPayment(btn.dataset.pay);return;}
 if(btn.dataset.print){await printSale(btn.dataset.print);return;}
 if(btn.dataset.note){await printDelivery(btn.dataset.note);return;}
 }catch(err){warn(err.message);}
});
document.addEventListener('change',evt=>{if(evt.target.name==='product_id'&&evt.target.closest('#wh-add-form')){const p=state.products.find(p=>p.id===Number(evt.target.value));const price=document.querySelector('#wh-add-form [name="unit_price"]');if(price)price.value=p?moneyInput(p.price):'';}});
(async()=>{try{state.user=await api('/auth/me');await getCsrf();shell();await refresh();}catch(_){showLogin();}})();
})();
