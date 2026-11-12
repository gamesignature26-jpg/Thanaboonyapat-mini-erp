/* Thanabunyapat One: server-backed web app. No localStorage for business data. */
(() => {
'use strict';
const root = document.getElementById('root');
const toast = document.getElementById('toast');
const state = {user:null,csrf:null,view:'dashboard',products:[],customers:[],sales:[],orders:[],expenses:[],users:[],summary:null,cart:new Map(),wh:[],quoteLines:[],quotations:[],quoteSelected:null,returns:[],returnsCursor:null,returnEligible:null,returnLines:[],returnSelected:null,returnReason:'',vatRate:7,busy:false,company:{},specialPrices:[],selectedCustomer:0,imageIds:[],posCustomer:0,posPrices:new Map(),posPriceReady:false,posMethod:"cash",customerLookupResults:null,customerHistory:null,salesOutstanding:false,salesCursor:null,search:{},posVatMode:'exclusive',lastSale:null};
const labels = {dashboard:'ภาพรวมธุรกิจ',pos:'ขายหน้าร้าน POS',wholesale:'ขายส่ง / จัดส่ง',sales:'บิลขาย / ลูกหนี้',quotations:'ใบเสนอราคา',returns:'รับคืนสินค้า',inventory:'สินค้าและสต๊อก',customers:'ลูกค้า',expenses:'ค่าใช้จ่าย',reports:'รายงาน',users:'ผู้ใช้งาน',prices:'ราคาพิเศษ',settings:'ตั้งค่าบริษัท'};
const roleLabels = {admin:'เจ้าของระบบ',sales:'พนักงานขาย',warehouse:'พนักงานคลัง',accountant:'พนักงานบัญชี'};
const navGroups = [
 ['งานขาย',['dashboard','pos','wholesale','sales','quotations','returns']],
 ['ข้อมูลร้าน',['inventory','customers','prices']],
 ['หลังร้าน',['expenses','reports','users','settings','operations']],
];
const roleViews = {
 admin:Object.keys(labels), sales:['dashboard','pos','wholesale','sales','quotations','returns','inventory','customers','prices'],
 warehouse:['dashboard','wholesale','inventory','returns'], accountant:['dashboard','wholesale','sales','quotations','returns','inventory','customers','expenses','reports'],
};
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
function customerSelect(name='customer_id',selected=''){return `<div class="field"><label>ลูกค้า<select name="${esc(name)}" required><option value="">เลือกลูกค้า</option>${state.customers.map(c=>opt(c.id,c.name,selected)).join('')}</select></label>${state.customers.length?'':'<small>เพิ่มลูกค้าจากเมนู “ลูกค้า” ก่อนบันทึกการขาย</small>'}</div>`;}
function methodSelect(selected='cash'){return `<div class="field"><label>วิธีชำระเงิน<select name="method">${opt('cash','เงินสด',selected)}${opt('transfer','โอนเงิน',selected)}${opt('credit','ขายเชื่อ / ค้างชำระ',selected)}</select></label></div>`;}
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
function showLogin(){delete root.dataset.operations;root.innerHTML=`<div class="login-page"><div class="card login"><div class="row"><div class="logo">TB</div><h1>Thanabunyapat One</h1></div><p>ระบบขายและจัดส่งออนไลน์ · หจก. ธนาบุณยภัทร</p><form id="login-form">${field('ชื่อผู้ใช้','username','text','', 'autocomplete="username" required maxlength="80"')}${field('รหัสผ่าน','password','password','','autocomplete="current-password" required')}<button class="btn block">เข้าสู่ระบบ</button></form><button class="btn secondary block" id="show-forgot" type="button">ลืมรหัสผ่าน</button><div class="small-note">เฉพาะเจ้าของระบบเท่านั้นที่สร้างบัญชีพนักงานได้ ระบบทดสอบนี้ไม่ใช่ระบบบัญชีคู่หรือใบกำกับภาษีตามกฎหมาย</div></div></div>`;}
function showForgot(){root.innerHTML=`<div class="login-page"><div class="card login"><div class="row"><div class="logo">TB</div><h1>ลืมรหัสผ่าน</h1></div><p>เพื่อป้องกันคนอื่นยึดบัญชี พนักงานต้องขอให้เจ้าของระบบรีเซ็ตรหัสจากเมนู “ผู้ใช้งาน”</p><p class="small-note">แจ้งชื่อผู้ใช้แก่เจ้าของเท่านั้น ห้ามส่งรหัสผ่านเดิมหรือรหัสใหม่ผ่านแชต</p><button class="btn secondary block" id="show-login" type="button">กลับไปเข้าสู่ระบบ</button></div></div>`;}
function navItems(){
 const allowed=roleViews[state.user.role]||['dashboard'];
 return navGroups.map(([label,views],index)=>{
  const items=views.filter(view=>view==='operations'||allowed.includes(view));
  if(!items.length)return '';
  return `<div class="nav-group ${index===0?'nav-primary':'nav-more'}"><div class="nav-label">${label}</div>${items.map(view=>{
   if(view==='operations')return '<button type="button" data-op="email">รายสัปดาห์ / ค่าแรง / หลักฐาน</button>';
   const current=state.view===view;
   return `<button type="button" data-nav="${view}" ${current?'class="active" aria-current="page"':''}>${labels[view]}</button>`;
  }).join('')}</div>`;
 }).join('');
}
function shell(){
 root.innerHTML=`<div class="layout">
 <aside class="sidebar">
  <div class="brand"><span class="logo" aria-hidden="true">TB</span><div><strong>ธนาบุณยภัทร</strong><small>Mini ERP</small></div></div>
  <nav class="nav" id="nav" aria-label="เมนูหลัก">${navItems()}</nav>
  <button type="button" class="menu-toggle" id="toggle-nav" aria-controls="nav" aria-expanded="false">เมนูทั้งหมด</button>
 </aside>
 <main id="main-content">
  <header class="page-header"><h1 id="title" tabindex="-1">${labels[state.view]}</h1>
   <div class="row account"><span>${esc(roleLabels[state.user.role]||'พนักงาน')}</span><button class="btn secondary slim" id="logout">ออกจากระบบ</button></div>
  </header>
  <p class="staging-note">ระบบทดสอบ · เอกสารที่ออกเป็นร่างสำหรับตรวจสอบ</p>
  <div id="view" aria-busy="true"><p class="loading" role="status">กำลังโหลดข้อมูล…</p></div>
 </main></div>`;
}
async function refresh(){
 if(!state.user)return;
 try{
  const needs=state.view;
  const base=['dashboard','reports','pos','wholesale','sales','quotations','returns','inventory','customers','prices'].includes(needs);
  if(base){
  const requests=[api('/products'),api('/customers'),api('/api/online/dashboard'),api('/api/online/sales'),api('/api/online/orders'),api('/api/online/config')];if(state.user.role==='admin')requests.push(api('/users'));
  const results=await Promise.allSettled(requests);
   const keys=['products','customers','summary','sales','orders','vatRate'];
   results.slice(0,6).forEach((res,i)=>{if(res.status==='fulfilled')state[keys[i]]=i===2?res.value:i===5?Number(res.value.vat_rate):res.value.items;else if(!String(res.reason).includes('401'))console.warn(keys[i],res.reason);});if(state.user.role==='admin'&&results[6]?.status==='fulfilled')state.users=results[6].value.items;
  }
  if(needs==='sales'){
   const salesPage=await api('/api/online/sales?outstanding='+(state.salesOutstanding?'1':'0'));
   state.sales=salesPage.items;
   state.salesCursor=salesPage.next_before;
  }
  if(needs==='quotations')state.quotations=(await api('/api/quotations')).items;
  if(needs==='returns'){const page=await api('/api/returns');state.returns=page.items;state.returnsCursor=page.next_before;}
  if(needs==='expenses')state.expenses=(await api('/api/online/expenses')).items;
  if(needs==='users'&&state.user.role==='admin')state.users=(await api('/users')).items;
   if(needs==='settings'&&state.user.role==='admin')state.company=await api('/api/extended/company');
   if(needs==='pos'||needs==='inventory')state.imageIds=(await api('/api/extended/product-images')).ids;
   if(needs==='pos'&&state.posCustomer)await loadPosPrices(state.posCustomer);
  if(state.view===needs)render();
 }catch(err){
  const view=$('view');
  if(view?.getAttribute('aria-busy')==='true'){
   view.setAttribute('aria-busy','false');
   view.innerHTML='<div class="card"><p>โหลดข้อมูลไม่สำเร็จ</p><button type="button" class="btn secondary" id="retry-view">ลองใหม่</button></div>';
  }
  warn(err.message);
 }
}
function navigate(v){
 if(!(roleViews[state.user?.role]||['dashboard']).includes(v))return;
 delete root.dataset.operations;
 state.view=v;
 shell();
 window.scrollTo(0,0);
 $('title').focus({preventScroll:true});
 refresh();
}
function card(label,val,sub){return `<div class="card metric"><small>${esc(label)}</small><strong>${esc(val)}</strong><small>${esc(sub)}</small></div>`;}
function summary(){const s=state.summary||{};return `<div class="grid g4 metrics">${card('ยอดขายวันนี้',fmt(s.today_total),'รวม VAT ตามรายการขาย')}${card('ยอดขายสะสม',fmt(s.sales_total),'ยอดการขาย ไม่ใช่ยอดรับเงิน')}${card('ลูกหนี้คงเหลือ',fmt(s.receivable),'ยังไม่ได้รับชำระ')}${card('ยอดสินค้าคงเหลือ',String(s.stock_units??0),'จำนวนหน่วยทุกสินค้า')}</div>`;}
function dashboard(){
 const s=state.summary||{};
 const allowed=roleViews[state.user.role]||[];
 return `${summary()}<div class="dashboard-actions" aria-label="งานที่ใช้บ่อย">
 ${allowed.includes('pos')?'<button type="button" data-nav="pos" class="btn">เริ่มขายหน้าร้าน</button>':''}
 ${allowed.includes('wholesale')?'<button type="button" data-nav="wholesale" class="btn secondary">เปิดงานขายส่ง</button>':''}
 ${allowed.includes('sales')?'<button type="button" data-nav="sales" class="btn secondary">เปิดบิลและลูกหนี้</button>':''}
 </div><div class="grid g2"><div class="card"><h2>งานจัดส่งที่ยังไม่เสร็จ</h2><div class="row space"><strong>${esc(s.pending_delivery||0)} ออเดอร์</strong><button data-nav="wholesale" class="btn slim">จัดการจัดส่ง</button></div></div><div class="card"><h2>ค่าใช้จ่ายที่บันทึก</h2><strong>${fmt(s.expenses_total)}</strong><p>ไม่ใช่ตัวเลขกำไรสุทธิ เพราะยังไม่มีต้นทุนสินค้าขายและบัญชีคู่</p></div></div><div class="card"><h2>ยอดขายล่าสุด</h2>${tableSales(state.sales.slice(0,7),false)}</div>`;}
function posUnitPrice(product){
 return state.posPrices.get(product.id) ?? product.price;
}
function vatAmounts(entered,mode){
 const rate=Math.round(state.vatRate*100);
 const vat=Math.round(entered*rate/(mode==='inclusive'?10000+rate:10000));
 return mode==='inclusive'?{base:entered-vat,vat,total:entered}:{base:entered,vat,total:entered+vat};
}
function vatModeSelect(selected='exclusive'){
 return `<fieldset class="field vat-options"><legend>รูปแบบราคา VAT</legend>
 <label><input type="radio" name="vat_price_mode" value="exclusive" ${selected==='exclusive'?'checked':''}><span>ราคาก่อน VAT<small>บวก VAT เพิ่ม</small></span></label>
 <label><input type="radio" name="vat_price_mode" value="inclusive" ${selected==='inclusive'?'checked':''}><span>ราคารวม VAT<small>ถอด VAT จากยอดเดิม</small></span></label></fieldset>`;
}
function vatSummary({base,vat,total}){
 return `<div><span>ยอดก่อน VAT</span><b>${fmt(base/100)}</b></div><div><span>VAT ${state.vatRate}%</span><b>${fmt(vat/100)}</b></div><div class="total"><span>ยอดรวม</span><b>${fmt(total/100)}</b></div>`;
}
function posTotals(){
 const entered=[...state.cart].reduce((sum,[id,quantity])=>{
  const product=state.products.find(item=>item.id===id);
  return sum+(product?Math.round(Number(posUnitPrice(product))*100)*quantity:0);
 },0);
 return vatAmounts(entered,state.posVatMode);
}
function printerButton(){
 return '<button type="button" class="btn secondary" data-printer-connect>เชื่อมต่อเครื่องพิมพ์ Bluetooth</button>';
}
function salePrintActions(kind){
 const sale=state.lastSale;
 return `<div class="toolbar">${printerButton()}${sale?.kind===kind?`
 <button type="button" class="btn" data-print="${sale.id}">พิมพ์สรุปบิล #${sale.id}</button>
 <button type="button" class="btn secondary" data-history="${sale.id}">ใบเสร็จ / ใบกำกับภาษี #${sale.id}</button>`:''}</div>`;
}
async function loadPosPrices(customerId){
 state.posCustomer=customerId;
 state.posPriceReady=false;
 state.posPrices=new Map();
 render();
 if(!customerId)return;
 const result=await api('/api/extended/prices/'+customerId);
 if(state.posCustomer!==customerId)return;
 state.posPrices=new Map(result.items.map(item=>[item.product_id,item.price]));
 state.posPriceReady=true;
 render();
}
function searchField(key,label,placeholder){
 return `<div class="field list-search"><label for="search-${key}">${label}</label>
 <input type="search" id="search-${key}" data-search="${key}" placeholder="${placeholder}" value="${esc(state.search[key]||'')}" autocomplete="off"></div>`;
}
function filterVisibleRows(key){
 const query=(state.search[key]||'').trim().toLocaleLowerCase('th');
 let visible=0;
 for(const item of root.querySelectorAll(`[data-search-list="${key}"] [data-search-text]`)){
  item.hidden=!item.dataset.searchText.toLocaleLowerCase('th').includes(query);
  if(!item.hidden)visible++;
 }
 const empty=$(`no-match-${key}`);
 if(empty)empty.hidden=!query||visible>0;
}
function pos(){
 const entries=[...state.cart].map(([id,quantity])=>({product:state.products.find(item=>item.id===id),quantity}))
  .filter(item=>item.product&&item.quantity>0);
 const totals=posTotals();
 const {total}=totals;
 const products=state.products.map(product=>{
  const photo=state.imageIds.includes(product.id)
   ? `<img class="product-photo" src="/api/extended/products/${product.id}/image" alt="">` : '';
  const marker=state.posPrices.has(product.id)?'<small>ราคาพิเศษลูกค้า</small>':'';
  return `<button type="button" class="product" data-search-text="${esc(product.name+' '+product.sku)}" data-add="${product.id}" ${product.stock<=0?'disabled':''}>${photo}<b>${esc(product.name)}</b><small>${esc(product.sku)} · สต๊อก ${product.stock}</small><strong>${fmt(posUnitPrice(product))}</strong>${marker}</button>`;
 }).join('');
 const lines=entries.map(({product,quantity})=>
  `<div class="line"><div><b>${esc(product.name)}</b><small> ${fmt(posUnitPrice(product))} × ${quantity}</small></div>
  <div class="row"><button type="button" class="btn secondary slim qty-control" aria-label="ลดจำนวน ${esc(product.name)}" data-dec="${product.id}">−</button><b>${quantity}</b><button type="button" class="btn secondary slim qty-control" aria-label="เพิ่มจำนวน ${esc(product.name)}" data-add="${product.id}">+</button></div></div>`
 ).join('');
 return `${salePrintActions('pos')}<div class="grid pos-layout"><section class="card catalog" id="pos-catalog" tabindex="-1"><h2>เลือกสินค้า</h2>
 ${searchField('products','ค้นหาสินค้า','พิมพ์ชื่อหรือรหัสสินค้า')}
 <div class="products" data-search-list="products">${products||'<p class="empty">ยังไม่มีสินค้า เพิ่มสินค้าได้จากเมนูสต๊อก</p>'}</div>
 ${products?'<p class="empty" id="no-match-products" role="status" hidden>ไม่พบสินค้า ลองใช้ชื่อหรือรหัสอื่น</p>':''}</section>
 <section class="card cart" id="pos-cart" tabindex="-1"><h2>รายการขาย <span class="count">${entries.reduce((sum,item)=>sum+item.quantity,0)} หน่วย</span></h2>${lines||'<div class="empty">ยังไม่มีสินค้าในตะกร้า</div>'}
 <form id="pos-form">${customerSelect('customer_id',state.posCustomer)}${methodSelect(state.posMethod)}${vatModeSelect(state.posVatMode)}
 <div class="summary">${vatSummary(totals)}</div>
 <button class="btn block" ${!entries.length||!state.posPriceReady?'disabled':''}>บันทึกการขายและตัดสต๊อก</button>
 <p class="small-note">รูปแบบ VAT ใช้กับราคาสินค้าที่แสดง รวมถึงราคาพิเศษ</p></form>
 <button type="button" class="btn secondary mobile-cart" data-pos-jump="pos-catalog">กลับไปเลือกสินค้า</button></section>
 ${entries.length?`<div class="cart-shortcut"><button type="button" class="btn block" data-pos-jump="pos-cart"><span>ดูรายการขาย</span><strong>${fmt(total/100)}</strong></button></div>`:''}</div>`;
}

function whEntered(){
 return state.wh.reduce((sum,line)=>sum+line.quantity*Math.round(num(line.unit_price)*100),0);
}
function updateWholesaleTotal(){
 const form=$('wh-form');
 const summary=$('wh-vat-total');
 if(!form||!summary)return;
 const values=f(form);
 const entered=whEntered()-Math.round(num(values.discount)*100)
  +(values.delivery_mode==='pickup'?0:Math.round(num(values.shipping_fee)*100));
 summary.innerHTML=entered<0?'<div>ส่วนลดเกินยอดสินค้า</div>':vatSummary(vatAmounts(entered,values.vat_price_mode));
}
function wholesale(){if(!['admin','sales'].includes(state.user.role))return `<div class="card"><h2>ติดตามออเดอร์ขายส่ง / จัดส่ง</h2>${orderTable()}</div>`;const rows=state.wh.map((x,i)=>{const p=state.products.find(p=>p.id===x.product_id);return `<tr><td>${esc(p?.name||'?')}</td><td class="num">${x.quantity}</td><td class="num">${fmt(x.unit_price)}</td><td class="num">${fmt(x.quantity*num(x.unit_price))}</td><td><button class="btn secondary slim" data-whdel="${i}">ลบ</button></td></tr>`;}).join('');return `${salePrintActions('wholesale')}<div class="grid g2"><div class="card"><h2>สร้างออเดอร์ขายส่ง / จัดส่ง</h2><form id="wh-add-form"><div class="field"><label>สินค้า</label>${productSelect('product_id')}</div><div class="grid g2">${field('จำนวนแพ็ค / หน่วย','quantity','number','1','min="1" step="1" required')}${field('ราคาส่งต่อหน่วย','unit_price','number','','min="0.01" step="0.01" required')}</div><button class="btn secondary block">เพิ่มสินค้าในออเดอร์</button></form><div class="tablewrap desktop-table"><table><thead><tr><th>สินค้า</th><th class="num">จำนวน</th><th class="num">ราคาส่ง</th><th class="num">รวม</th><th></th></tr></thead><tbody>${rows||'<tr><td colspan="5" class="empty">ยังไม่มีสินค้า</td></tr>'}</tbody></table></div><div class="summary"><div><b>ยอดสินค้าก่อนส่วนลด</b><strong>${fmt(whEntered()/100)}</strong></div></div></div><div class="card"><h2>ข้อมูลลูกค้าและการจัดส่ง</h2><form id="wh-form">${customerSelect()}<div class="field"><label>รูปแบบรับสินค้า</label><select name="delivery_mode">${opt('delivery','จัดส่งถึงร้าน')}${opt('pickup','รับเองที่โกดัง')}</select></div>${field('วันนัดส่ง','delivery_date','date',new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Bangkok',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date()))}${field('ที่อยู่จัดส่ง','address','text','','maxlength="1000"')}${field('โทรศัพท์ติดต่อ','phone','tel','','maxlength="30"')}${field('ชื่อคนขับรถ','driver','text','','maxlength="100"')}<div class="grid g2">${field('ส่วนลด (บาท)','discount','number','0.00','min="0" step="0.01" required')}${field('ค่าจัดส่ง (บาท)','shipping_fee','number','0.00','min="0" step="0.01" required')}</div>${methodSelect()}${vatModeSelect()}${field('หมายเหตุ','note','text','','maxlength="600"')}<p class="small-note">รูปแบบ VAT ใช้กับราคาสินค้า ส่วนลด และค่าจัดส่ง</p><div class="summary" id="wh-vat-total"></div><button class="btn block" ${!state.wh.length?'disabled':''}>ยืนยันออเดอร์ขายส่ง</button></form><div class="small-note">ยืนยันแล้วตัดสต๊อกทันที และสถานะจัดส่งสามารถติดตามต่อด้านล่าง</div></div></div><div class="card"><h2>สถานะออเดอร์จัดส่ง</h2>${orderTable()}</div>`;}
const statusName={pending:'รอเตรียม',packing:'กำลังจัดสินค้า',out_for_delivery:'กำลังนำส่ง',delivered:'ส่งสำเร็จ',ready:'พร้อมรับ',picked_up:'รับสินค้าแล้ว'};
function orderTable(){if(!state.orders.length)return '<div class="empty">ยังไม่มีออเดอร์ขายส่ง</div>';return `<div class="tablewrap"><table><thead><tr><th>เลขบิล</th><th>ลูกค้า</th><th>วิธีรับ</th><th>ยอด</th><th>สถานะ</th><th></th></tr></thead><tbody>${state.orders.map(o=>{const done=['delivered','picked_up'].includes(o.status);return `<tr><td>#${o.id}</td><td>${esc(o.customer)}</td><td>${o.mode==='pickup'?'รับเอง':'จัดส่ง'}</td><td>${fmt(o.total)}</td><td><span class="status ${esc(o.status)}">${esc(statusName[o.status]||o.status)}</span></td><td><div class="row">${done?'':`<button class="btn slim" data-next="${o.id}">อัปเดตขั้นต่อไป</button>`}<button class="btn secondary slim" data-note="${o.id}">พิมพ์ใบส่งสินค้า</button>${state.user.role==='warehouse'?'':`<button type="button" class="btn secondary slim" data-history="${o.id}">ใบเสร็จ / ใบกำกับภาษี</button>`}</div></td></tr>`;}).join('')}</tbody></table></div>`;}
function tableSales(items,allowPay=true){if(!items.length)return '<div class="empty">ยังไม่มีรายการขาย</div>';return `<div class="tablewrap"><table><thead><tr><th>เลข</th><th>วันที่</th><th>ลูกค้า</th><th class="num">รวม</th><th class="num">ค้างชำระ</th><th>ดำเนินการ</th></tr></thead><tbody>${items.map(s=>`<tr><td>#${s.id}</td><td>${formatDate(s.date)}</td><td>${esc(s.customer)}</td><td class="num">${fmt(s.total)}</td><td class="num">${fmt(s.balance)}<small class="muted"> ${num(s.balance)===0?'ชำระครบ':num(s.paid)>0?'ชำระบางส่วน':'ค้างชำระ'}</small></td><td><div class="row"><button class="btn secondary slim" data-print="${s.id}">พิมพ์สรุป</button><button class="btn secondary slim" data-history="${s.id}">ชำระ / เอกสาร</button><a class="btn secondary slim" href="/api/billing-notes/${s.id}/print" target="_blank" rel="noopener">ใบวางบิลตัวอย่าง</a><button class="btn secondary slim" data-op-sale="${s.id}">แนบสลิป</button>${allowPay&&num(s.balance)>0&&['admin','accountant'].includes(state.user.role)?`<button class="btn slim" data-pay="${s.id}">รับชำระ</button>`:''}</div></td></tr>`).join('')}</tbody></table></div>`;}
function sales(){
 return `<div class="card"><h2>บิลขายและลูกหนี้</h2><div class="row"><button type="button" class="btn secondary" data-sales-filter="all" aria-pressed="${!state.salesOutstanding}">บิลทั้งหมด</button>
 <button type="button" class="btn secondary" data-sales-filter="open" aria-pressed="${state.salesOutstanding}">เฉพาะค้างชำระ</button></div>
 <p>${state.salesOutstanding?'กำลังดูเฉพาะบิลที่ยังมียอดค้าง':'กำลังดูบิลทั้งหมด'} · รับชำระบางส่วนหรือเต็มยอด</p>
 ${tableSales(state.sales)}${state.salesCursor?'<button type="button" class="btn secondary" data-sales-more>โหลดบิลเก่ากว่า</button>':''}</div>`;
}
function quotations(){
 const canCreate=['admin','sales'].includes(state.user.role);
 const lines=state.quoteLines.map((x,i)=>{
  const p=state.products.find(p=>p.id===x.product_id);
  return `<tr><td>${esc(p?.name||x.product_id)}</td><td>${x.quantity}</td><td><button type="button" class="btn secondary slim" data-quote-remove="${i}">ลบ</button></td></tr>`;
 }).join('');
 const quotes=state.quotations.map(q=>`<tr><td>${esc(q.number)}</td><td>${esc(q.customer_name)}</td><td>${formatDate(q.date)}</td><td class="num">${fmt(q.total)}</td><td><button type="button" class="btn secondary slim" data-quote-detail="${q.id}">ดูรายละเอียด</button> <a class="btn secondary slim" target="_blank" rel="noopener" href="/api/quotations/${q.id}/print">พิมพ์ร่าง</a></td></tr>`).join('');
 const selected=state.quoteSelected;
 const quoteActions=canCreate&&!selected?.sale_id?(selected?.status==='draft'?[['sent','บันทึกว่าส่งแล้ว']]:selected?.status==='sent'?[['accepted','ลูกค้ายืนยัน'],['declined','ลูกค้าปฏิเสธ']]:[]):[];
 const detailsStatus={draft:'ร่าง',sent:'ส่งให้ลูกค้าแล้ว',accepted:'บันทึกลูกค้ายืนยันแล้ว',declined:'ลูกค้าปฏิเสธ'};
 const detail=selected?`<section class="card" id="quote-detail"><h2>รายละเอียด ${esc(selected.number)}</h2><p>ลูกค้า ${esc(selected.customer.name)} · ยอดรวม ${fmt(selected.total)} · VAT ${fmt(selected.vat)}</p><p>สถานะ: ${esc(detailsStatus[selected.status]||selected.status)}</p><p>เอกสารร่าง ไม่ใช่ใบเสร็จหรือใบกำกับภาษี</p><div class="tablewrap"><table><tbody>${selected.lines.map(x=>`<tr><td>${esc(x.name)}</td><td>${x.quantity} × ${fmt(x.unit_price)}</td></tr>`).join('')}</tbody></table></div>
 ${quoteActions.length?`<div class="field"><label for="quote-status-note">หมายเหตุหรือหลักฐานการติดต่อกับลูกค้า</label><input id="quote-status-note" maxlength="600" placeholder="เช่น ลูกค้ายืนยันทางโทรศัพท์" required></div><div class="row">${quoteActions.map(([status,label])=>`<button type="button" class="btn secondary slim" data-quote-transition="${status}" data-quote-id="${selected.id}">${label}</button>`).join('')}</div>`:''}
 ${selected.sale_id?`<p>แปลงเป็นบิลขาย #${selected.sale_id} แล้ว</p>`:''}
 ${canCreate&&selected.status==='accepted'&&!selected.sale_id?`<form id="quote-convert-form"><h3>แปลงใบเสนอราคาเป็นบิลขายเชื่อ</h3><p class="small-note">ตรวจราคาปัจจุบันและสต็อกอีกครั้ง หากเปลี่ยนจะไม่สร้างบิล</p><div class="field"><label>รูปแบบรับสินค้า<select name="delivery_mode">${opt('pickup','รับสินค้าเอง')}${opt('delivery','ส่งสินค้า')}</select></label></div>${field('ที่อยู่จัดส่ง','address','text',selected.customer.address||'','maxlength="1000"')}${field('โทรศัพท์','phone','tel','','maxlength="30"')}${field('คนขับ','driver','text','','maxlength="100"')}${field('วันจัดส่ง','delivery_date','date')}${field('หมายเหตุ','note','text','','maxlength="600"')}<button class="btn">ยืนยันแปลงเป็นบิลขาย</button></form>`:''}
 <h3>ประวัติการเปลี่ยนสถานะ</h3><div class="tablewrap"><table><tbody>${(selected.events||[]).map(e=>`<tr><td>${formatDate(e.created_at)}</td><td>${esc(detailsStatus[e.to_status]||e.to_status)}</td><td>${esc(e.note)}</td></tr>`).join('')||'<tr><td>ยังไม่มีการเปลี่ยนสถานะ</td></tr>'}</tbody></table></div></section>`:'';
 return `${canCreate?`<div class="grid g2"><section class="card"><h2>เพิ่มรายการเสนอราคา</h2><form id="quote-add-form"><div class="field"><label>สินค้า${productSelect()}</label></div>${field('จำนวนสินค้า','quantity','number','1','min="1" step="1" max="1000000" required')}<button class="btn secondary block">เพิ่มรายการเสนอราคา</button></form><div class="tablewrap"><table><thead><tr><th>สินค้า</th><th>จำนวน</th><th>จัดการ</th></tr></thead><tbody>${lines||'<tr><td colspan="3">ยังไม่มีรายการ</td></tr>'}</tbody></table></div></section><section class="card"><h2>สร้างใบเสนอราคา (ร่าง)</h2><p>ไม่ตัดสต็อก และราคาจะคำนวณจากเซิร์ฟเวอร์เมื่อบันทึก</p><form id="quote-form">${customerSelect()}${vatModeSelect()}${field('วันหมดอายุ','expires_on','date')}${field('หมายเหตุ','note','text','','maxlength="600"')}<button class="btn block" ${!state.quoteLines.length?'disabled':''}>บันทึกใบเสนอราคาร่าง</button></form></section></div>`:''}<section class="card"><h2>ใบเสนอราคาที่บันทึก</h2><div class="tablewrap"><table><thead><tr><th>เลขอ้างอิง</th><th>ลูกค้า</th><th>วันที่</th><th>ยอดรวม</th><th>ดำเนินการ</th></tr></thead><tbody>${quotes||'<tr><td colspan="5">ยังไม่มีใบเสนอราคา</td></tr>'}</tbody></table></div><p class="small-note">เลข QT-DRAFT เป็นเลขอ้างอิงภายใน ไม่ใช่เลขที่เอกสารภาษี</p></section>${detail}`;
}
function returnIntake(){
 const role=state.user.role, canRequest=['admin','sales'].includes(role), canInspect=['admin','warehouse'].includes(role);
 const eligible=state.returnEligible;
 const statusLabels={draft:'รอตรวจรับ',received:'ตรวจรับแล้ว',rejected:'ไม่รับคืน'};
 const cart=state.returnLines.map((x,i)=>{
  const item=eligible?.lines.find(p=>p.sale_line_id===x.sale_line_id);
  return `<tr><td>${esc(item?.name||x.sale_line_id)}</td><td>${x.quantity}</td><td><button type="button" class="btn secondary slim" data-return-remove="${i}">ลบ</button></td></tr>`;
 }).join('');
 const options=eligible?.lines.filter(x=>x.remaining_quantity>0&&!state.returnLines.some(y=>y.sale_line_id===x.sale_line_id))||[];
 const entries=state.returns.map(x=>`<tr><td>${esc(x.number)}</td><td>#${x.sale_id}</td><td>${esc(statusLabels[x.status]||x.status)}</td><td><button type="button" class="btn secondary slim" data-return-detail="${x.id}">รายละเอียด</button></td></tr>`).join('');
 const detail=state.returnSelected;
 return `
 ${canRequest?`<div class="grid g2"><section class="card"><h2>คำขอรับคืนสินค้า</h2><p>บันทึกคำขอจากเลขบิลขาย ไม่ลดลูกหนี้หรือออกใบลดหนี้อัตโนมัติ</p><div class="field"><label for="return-sale-id">เลขบิลขาย</label><input id="return-sale-id" type="number" min="1" step="1" value="${eligible?.sale_id||''}" placeholder="กรอกเลขบิลขาย"></div><button type="button" class="btn secondary" data-return-load="1">โหลดสินค้าในบิล</button>
 ${eligible?`<p><b>บิล #${eligible.sale_id}</b> · ${esc(eligible.customer_name)}</p><form id="return-add-form"><div class="field"><label>รายการสินค้า<select name="sale_line_id" required><option value="">เลือกรายการ</option>${options.map(x=>opt(x.sale_line_id,`${x.name} · คืนได้อีก ${x.remaining_quantity}`)).join('')}</select></label></div>${field('จำนวนที่ขอคืน','quantity','number','1','min="1" step="1" required')}<button class="btn secondary" ${!options.length?'disabled':''}>เพิ่มรายการคืน</button></form>`:''}</section><section class="card"><h2>ยืนยันคำขอคืน (ร่าง)</h2><div class="tablewrap"><table><thead><tr><th>สินค้า</th><th>จำนวน</th><th>จัดการ</th></tr></thead><tbody>${cart||'<tr><td colspan="3">ยังไม่มีรายการคืน</td></tr>'}</tbody></table></div><form id="return-request-form"><div class="field"><label for="return-reason">เหตุผลการคืนสินค้า</label><input id="return-reason" name="reason" type="text" required maxlength="600" placeholder="เช่น ลูกค้าคืนแพ็คที่ยังไม่ได้เปิด"></div><button class="btn block" ${!state.returnLines.length?'disabled':''}>บันทึกคำขอรับคืนร่าง</button></form><p class="small-note">รอคลังตรวจของจริงก่อนนำกลับเข้าสต็อก</p></section></div>`:''}
 <section class="card"><h2>รายการรับคืนสินค้า</h2><div class="tablewrap"><table><thead><tr><th>เลขรับคืน</th><th>บิลขาย</th><th>สถานะ</th><th>รายละเอียด</th></tr></thead><tbody>${entries||'<tr><td colspan="4">ยังไม่มีรายการรับคืน</td></tr>'}</tbody></table></div>${state.returnsCursor?'<button type="button" class="btn secondary" data-return-more="1">ดูรายการเก่ากว่า</button>':''}</section>
 ${detail?`<section class="card" id="return-detail"><h2>${esc(detail.number)} — ${esc(statusLabels[detail.status]||detail.status)}</h2><p>อ้างอิงบิล #${detail.sale_id} · ลูกค้า ${esc(detail.customer_name)}</p><p>เหตุผล: ${esc(detail.reason)}</p><p>ผู้ตรวจ: ${detail.inspected_by||'รอตรวจ'} · ${esc(detail.inspection_note||'ยังไม่มีหมายเหตุ')}</p><p><b>ไม่ใช่ใบลดหนี้ภาษี</b> และไม่ปรับยอดรับชำระหรือลูกหนี้</p><div class="tablewrap"><table><thead><tr><th>สินค้า</th><th>จำนวนขอคืน</th></tr></thead><tbody>${detail.lines.map(x=>`<tr><td>${esc(x.name)} · ${esc(x.sku)}</td><td>${x.quantity}</td></tr>`).join('')}</tbody></table></div>
 ${canInspect&&detail.status==='draft'?`<form id="return-inspect-form"><h3>ตรวจสภาพสินค้าจริง</h3><div class="field"><label>ผลตรวจสภาพ<select name="condition"><option value="resellable">ขายต่อได้ — นำกลับเข้าสต็อก</option><option value="damaged">ชำรุด — ไม่เพิ่มสต็อกขาย</option></select></label></div>${field('หมายเหตุการตรวจรับ','inspection_note','text','','required maxlength="600"')}<div class="row"><button class="btn">ยืนยันรับคืน</button><button type="button" class="btn secondary" data-return-reject="${detail.id}">ปฏิเสธรับคืน</button></div></form>`:''}
 </section>`:''}`;
}
function inventory(){const canWrite=['admin','warehouse'].includes(state.user.role);return `<div class="grid g2">${canWrite?`<div class="card"><h2>เพิ่มสินค้า</h2><form id="product-form">${field('รหัสสินค้า SKU','sku','text','','required maxlength="80"')}${field('ชื่อสินค้า','name','text','','required maxlength="200"')}${field('ราคาขายก่อน VAT (บาท)','price','number','','required min="0" step="0.01"')}<button class="btn">บันทึกสินค้า</button></form></div><div class="card"><h2>รับเข้า / ปรับสต๊อก</h2><form id="stock-form"><div class="field"><label>สินค้า</label>${productSelect()}</div>${field('จำนวนเพิ่ม (+) หรือลด (−)','delta','number','1','step="1" required')}${field('เหตุผลปรับสต๊อก','reason','text','','required maxlength="200"')}<button class="btn">บันทึกสต๊อก</button></form></div>`:''}</div><div class="card"><h2>สินค้าคงเหลือ</h2><div class="tablewrap"><table><thead><tr><th>SKU</th><th>สินค้า</th><th class="num">ราคา</th><th class="num">คงเหลือ</th></tr></thead><tbody>${state.products.map(p=>`<tr><td>${esc(p.sku)}</td><td>${esc(p.name)}</td><td class="num">${fmt(p.price)}</td><td class="num">${p.stock}</td></tr>`).join('')}</tbody></table></div></div>`;}
function customers(){
 const rows=(state.customerLookupResults||state.customers).map(c=>`<tr data-search-text="${esc(c.name+' '+c.address+' '+(c.tax_id||''))}"><td><b>${esc(c.name)}</b><div class="muted">${esc(c.address)}</div><button type="button" class="btn secondary slim" data-customer-history="${c.id}">ดูประวัติซื้อ</button></td></tr>`).join('');
 return `<div class="grid g2 directory-layout">
 <section class="card"><h2>รายชื่อลูกค้า</h2>${searchField('customers','ค้นหาลูกค้า','พิมพ์ชื่อร้านหรือที่อยู่')}<button type="button" class="btn secondary slim" data-customer-server-search="1">ค้นหาทั้งฐานข้อมูล</button>${state.customerLookupResults?'<button type="button" class="btn secondary slim" data-customer-clear="1">กลับสู่รายชื่อเดิม</button>':''}
 <div class="tablewrap"><table aria-label="รายชื่อลูกค้า"><tbody data-search-list="customers">${rows}</tbody></table></div>
 ${rows?'<p class="empty" id="no-match-customers" role="status" hidden>ไม่พบลูกค้า ลองใช้ชื่อหรือที่อยู่อื่น</p>':'<p class="empty">ยังไม่มีลูกค้า</p>'}${state.customerHistory?`<section id="customer-purchase-history" tabindex="-1"><h3>ประวัติซื้อ: ${esc(state.customerHistory.customer.name)}</h3><p>ยอดซื้อ ${fmt(state.customerHistory.summary.total_sales)} · รับแล้ว ${fmt(state.customerHistory.summary.total_paid)} · ค้างชำระ ${fmt(state.customerHistory.summary.outstanding)}</p><div class="tablewrap"><table><thead><tr><th>บิล</th><th>วันที่</th><th>ยอดขาย</th><th>ค้างชำระ</th></tr></thead><tbody>${state.customerHistory.items.map(s=>`<tr><td>#${s.id}</td><td>${formatDate(s.date)}</td><td>${fmt(s.total)}</td><td>${fmt(s.balance)}</td></tr>`).join('')||'<tr><td colspan="4">ยังไม่มีประวัติซื้อ</td></tr>'}</tbody></table></div></section>`:''}</section>
 <section class="card"><h2>เพิ่มลูกค้า</h2><form id="customer-form">${field('ชื่อร้านค้า / ลูกค้า','name','text','','required maxlength="200"')}${field('ที่อยู่','address','text','','required maxlength="1000"')}${field('เลขผู้เสียภาษี 13 หลัก (ถ้ามี)','tax_id','text','','pattern="[0-9]{13}" maxlength="13"')}<button class="btn">บันทึกลูกค้า</button></form></section></div>`;
}
function expenses(){return `<div class="grid g2"><div class="card"><h2>บันทึกค่าใช้จ่าย</h2><p>ใช้ติดตามรายจ่าย ไม่ใช่ลงบัญชีคู่</p><form id="expense-form">${field('หมวดหมู่','category','text','ขนส่ง','required maxlength="80"')}${field('รายละเอียด','description','text','','required maxlength="250"')}${field('จำนวนเงิน (บาท)','amount','number','','min="0.01" step="0.01" required')}<div class="field"><label>ชำระโดย</label><select name="method">${opt('cash','เงินสด')}${opt('transfer','โอนเงิน')}</select></div><button class="btn">บันทึกรายจ่าย</button></form></div><div class="card"><h2>รายจ่ายล่าสุด</h2><div class="tablewrap"><table><tbody>${state.expenses.map(x=>`<tr><td>#${x.id} ${esc(x.category)}<div class="muted">${esc(x.description)}</div><button class="btn secondary slim" data-op-expense="${x.id}">แนบรูปใบเสร็จ</button></td><td class="num">${fmt(x.amount)}</td></tr>`).join('')}</tbody></table></div></div></div>`;}
function reports(){const s=state.summary||{};return `${summary()}<div class="card"><h2>รายงานการจัดส่งและค่าใช้จ่าย</h2><div class="grid g2">${card('รอส่งสินค้า',String(s.pending_delivery||0),'สถานะยังไม่สิ้นสุด')}${card('รายจ่ายที่บันทึก',fmt(s.expenses_total),'ไม่รวมต้นทุนสินค้าขาย')}</div><div class="alert">ยังไม่มีระบบต้นทุนสินค้า กำไรขาดทุนบัญชีคู่ งบการเงิน และรายงานภาษีที่ผ่านการรับรอง ห้ามนำยอดรวมนี้ไปอ้างว่าเป็นกำไรสุทธิ</div></div>`;}
function users(){
 if(state.user.role!=='admin')return '<div class="alert">ไม่มีสิทธิ์เข้าถึง</div>';
 const rows=state.users.map(u=>`<tr><td>${esc(u.username)}</td><td>${esc(roleLabels[u.role]||u.role)}</td><td>${u.active?'เปิดใช้':'ปิดใช้'}</td><td>${u.role==='admin'?'เจ้าของระบบ':`<button class="btn secondary slim" data-staff="${u.id}">แก้สิทธิ์</button>`} <button class="btn secondary slim" data-reset="${u.id}">ตั้งรหัสใหม่</button></td></tr>`).join('');
 return `<div class="grid g2"><div class="card"><h2>สร้างบัญชีพนักงาน (เจ้าของเท่านั้น)</h2><form id="create-user-form">${field('ชื่อผู้ใช้','username','text','','required maxlength="80"')}${field('รหัสผ่านแรกเริ่ม','password','password','','required minlength="12" maxlength="128"')}<div class="field"><label>หน้าที่</label><select name="role">${['sales','warehouse','accountant'].map(r=>opt(r,roleLabels[r])).join('')}</select></div><button class="btn">สร้างบัญชี</button></form></div><div class="card"><h2>บัญชีผู้ใช้งาน</h2><div class="tablewrap"><table><tbody>${rows}</tbody></table></div></div></div>`;
}
function showStaff(id){const u=state.users.find(x=>x.id===Number(id));if(!u||u.role==='admin')return;$('view').insertAdjacentHTML('afterbegin',`<div class="card"><h2>แก้สิทธิ์: ${esc(u.username)}</h2><form id="staff-form"><input name="id" type="hidden" value="${u.id}"><div class="field"><label>บทบาท</label><select name="role">${['sales','warehouse','accountant'].map(r=>opt(r,roleLabels[r],u.role)).join('')}</select></div><div class="field"><label>สถานะ</label><select name="active">${opt('true','เปิดใช้',String(u.active))}${opt('false','ปิดใช้',String(u.active))}</select></div><button class="btn">บันทึกสิทธิ์</button></form></div>`);}
function prices(){
 if(!['admin','sales'].includes(state.user.role))return '<div class="alert">ไม่มีสิทธิ์</div>';
 return `<div class="card"><h2>ราคาพิเศษรายลูกค้า</h2><p>ราคาที่บันทึกจะนำไปใช้กับ POS และออเดอร์ที่ไม่ได้ระบุราคาต่อรองด้วยตนเอง</p><form id="price-form">${customerSelect()}<div class="field"><label>สินค้า</label>${productSelect()}</div>${field('ราคาพิเศษก่อน VAT','price','number','','min="0.01" step="0.01" required')}<button class="btn">บันทึกราคาพิเศษ</button></form><h3>ดูราคาที่บันทึก</h3><div class="field"><select id="price-customer"><option value="">เลือกลูกค้า</option>${state.customers.map(c=>opt(c.id,c.name,state.selectedCustomer)).join('')}</select></div><button class="btn secondary slim" data-load-prices="1">แสดงรายการ</button><div class="tablewrap"><table><tbody>${state.specialPrices.map(x=>`<tr><td>${esc(state.products.find(p=>p.id===x.product_id)?.name||x.product_id)}</td><td>${fmt(x.price)}</td><td><button class="btn secondary slim" data-remove-price="${x.product_id}">ลบ</button></td></tr>`).join('')}</tbody></table></div></div>`;
}
function settings(){const c=state.company||{};return `<div class="card"><h2>ข้อมูลบริษัทสำหรับเอกสาร</h2><form id="company-form">${field('ชื่อจดทะเบียน','legal_name','text',c.legal_name||'','required')}${field('เลขผู้เสียภาษี 13 หลัก','tax_id','text',c.tax_id||'','pattern="[0-9]{13}"')}${field('ชื่อสาขา','branch','text',c.branch||'สำนักงานใหญ่','required')}${field('ที่อยู่จดทะเบียน','address','text',c.address||'','required')}${field('เบอร์ติดต่อ','phone','tel',c.phone||'')}${field('ข้อความท้ายเอกสาร','receipt_footer','text',c.receipt_footer||'')}<div class="field"><label>ขนาดกระดาษเริ่มต้น</label><select name="default_paper">${opt('a4','A4',c.default_paper)}${opt('58','สลิป 58 มม.',c.default_paper)}</select></div><button class="btn">บันทึกข้อมูลบริษัท</button></form><p>เอกสารทุกฉบับยังเป็นร่างทดสอบ ไม่ใช่เอกสารภาษีที่รับรองแล้ว</p></div><div class="card"><h2>นำเข้าและส่งออก Excel</h2><p>นำเข้าเฉพาะข้อมูลใหม่ ไม่แก้สต๊อกเดิมหรือปรับราคาโดยอัตโนมัติ</p><form id="excel-form"><select name="entity">${opt('products','สินค้า')}${opt('customers','ลูกค้า')}</select><input name="file" type="file" accept=".xlsx" required><button class="btn">นำเข้า Excel</button></form><a href="/api/extended/excel/products">ส่งออกสินค้า XLSX</a> · <a href="/api/extended/excel/customers">ส่งออกลูกค้า XLSX</a></div>`;}
function inventoryWithExtras(){const writable=['admin','warehouse'].includes(state.user.role);return inventory()+`${writable?`<div class="card"><h2>เพิ่มรูปสินค้า</h2><form id="image-form"><div class="field"><label>สินค้า</label>${productSelect()}</div><input name="image" type="file" accept="image/jpeg,image/png,image/webp" required><button class="btn">อัปโหลดรูป (ไม่เกิน 1 MB)</button></form></div>`:''}<div class="card"><h2>ภาพสินค้า</h2><div class="products">${state.products.filter(p=>state.imageIds.includes(p.id)).map(p=>`<div class="product"><img class="product-photo" src="/api/extended/products/${p.id}/image" alt="${esc(p.name)}"><div>${esc(p.name)}</div></div>`).join('')||'ยังไม่มีภาพสินค้า'}</div></div>`;}
async function showHistory(id){
 const view=$('view');
 const [history,docs]=await Promise.all([api(`/api/extended/sales/${Number(id)}/payments`),api(`/api/extended/sales/${Number(id)}/documents`)]);
 if(!view?.isConnected||root.dataset.operations)return;
 $('sale-history')?.remove();
 const canIssue=['admin','accountant'].includes(state.user.role);
 const canIssueTax=canIssue&&!docs.items.some(doc=>doc.kind==='tax_invoice');
 view.insertAdjacentHTML('afterbegin',`<section class="card" id="sale-history" tabindex="-1">
 <div class="row space"><h2>เอกสารและการชำระ · บิล #${id}</h2><button type="button" class="btn secondary slim" data-close-history>ปิด</button></div>
 <p>ยอดรวม ${fmt(history.total)} · ค้างชำระ ${fmt(history.balance)}</p>
 ${history.payments.length?`<div class="tablewrap"><table><tbody>${history.payments.map(p=>`<tr><td>${formatDate(p.date)}</td><td>${esc(p.method)}</td><td>${fmt(p.amount)}</td><td>${canIssue?`<button type="button" class="btn secondary slim" data-issue-doc="receipt" data-sale-id="${id}" data-payment-id="${p.id}">ออกใบเสร็จร่าง</button>`:''}</td></tr>`).join('')}</tbody></table></div>`:'<p>ยังไม่มีรายการรับชำระ</p>'}
 ${canIssueTax?`<details class="invoice-details"><summary>ออกใบกำกับภาษีร่าง</summary>
 <form id="tax-invoice-form"><input type="hidden" name="sale_id" value="${id}">
 ${field('ชื่อผู้ซื้อ / ชื่อนิติบุคคล','buyer_name','text',history.buyer.name,'required maxlength="200"')}
 <div class="field"><label for="buyer_address">ที่อยู่สำหรับใบกำกับภาษี</label><textarea id="buyer_address" name="buyer_address" required maxlength="1000" rows="3">${esc(history.buyer.address)}</textarea></div>
 <div class="grid g2">${field('เลขผู้เสียภาษี 13 หลัก','buyer_tax_id','text',history.buyer.tax_id,'required inputmode="numeric" maxlength="13" pattern="[0-9]{13}"')}
 ${field('รหัสสาขา (00000 สำหรับสำนักงานใหญ่)','buyer_branch','text','','inputmode="numeric" maxlength="5" pattern="[0-9]{5}"')}</div>
 <button class="btn">บันทึกใบกำกับภาษีร่าง</button></form></details>`:''}
 <h3>เอกสารที่บันทึกไว้</h3>
 ${docs.items.map(d=>`<div class="row document-actions"><strong>${esc(d.number)}</strong>
 <a class="btn secondary slim" target="_blank" rel="noopener" href="/api/extended/documents/${d.id}/print?paper=a4">A4</a>
 <a class="btn secondary slim" target="_blank" rel="noopener" href="/api/extended/documents/${d.id}/print?paper=58">58 มม.</a>
 <button type="button" class="btn secondary slim" data-thermal-document="${d.id}">พิมพ์ Bluetooth</button></div>`).join('')||'<p>ยังไม่มีเอกสาร</p>'}</section>`);
 $('sale-history').focus({preventScroll:true});
 $('sale-history').scrollIntoView({block:'start'});
}

function render(){
 if(!state.user||root.dataset.operations)return;
 const view=$('view');
 if(!view)return;
 const quoteStatusDraft=$('quote-status-note')?.value||'';
 const returnReasonDraft=$('return-reason')?.value??state.returnReason;
 const quoteForm=$('quote-form');
 const quoteDraft=quoteForm?f(quoteForm):null;
 const wholesaleDraft=$('wh-form');
 const draft=wholesaleDraft?f(wholesaleDraft):null;
 const focused=document.activeElement;
 const cartAction=focused?.matches('.qty-control,.product[data-add]')?
  {attr:focused.hasAttribute('data-dec')?'data-dec':'data-add',id:focused.dataset.dec||focused.dataset.add,qty:focused.classList.contains('qty-control')}:null;
 const map={dashboard,pos,wholesale,sales,quotations,returns:returnIntake,inventory:inventoryWithExtras,customers,expenses,reports,users,prices,settings};
 view.innerHTML=(map[state.view]||dashboard)();
 if($('quote-status-note'))$('quote-status-note').value=quoteStatusDraft;
 if($('return-reason'))$('return-reason').value=returnReasonDraft;
 view.setAttribute('aria-busy','false');
 if(quoteDraft&&$('quote-form'))for(const [name,value] of Object.entries(quoteDraft)){
  const control=$('quote-form').elements.namedItem(name);
  if(control)control.value=value;
 }
 if(draft&&$('wh-form'))for(const [name,value] of Object.entries(draft)){
  const control=$('wh-form').elements.namedItem(name);
  if(control)control.value=value;
 }
 if(state.view==='pos'){
  filterVisibleRows('products');
  if(cartAction){
   const action=view.querySelector(`${cartAction.qty?'.qty-control':'.product'}[${cartAction.attr}="${cartAction.id}"]`);
   (action||view.querySelector(`.product[data-add="${cartAction.id}"]`))?.focus({preventScroll:true});
  }
 }
 if(state.view==='customers')filterVisibleRows('customers');
 if(state.view==='wholesale')updateWholesaleTotal();
}
function showReset(id){const user=state.users.find(x=>x.id===Number(id));if(!user)return;const el=$('view');el.insertAdjacentHTML('afterbegin',`<div class="card"><h2>ตั้งรหัสใหม่: ${esc(user.username)}</h2><form id="reset-password-form"><input type="hidden" name="user_id" value="${user.id}">${field('รหัสผ่านใหม่','password','password','','autocomplete="new-password" required minlength="12" maxlength="128"')}${field('ยืนยันรหัสผ่านใหม่','confirm_password','password','','autocomplete="new-password" required minlength="12" maxlength="128"')}<button class="btn">บันทึกรหัสใหม่</button></form><div class="small-note">ให้ส่งรหัสใหม่แก่พนักงานผ่านช่องทางส่วนตัวเท่านั้น</div></div>`);window.scrollTo({top:0,behavior:'smooth'});}
async function doLogin(form){const values=f(form);await getCsrf();const r=await api('/auth/login',{method:'POST',body:{username:values.username,password:values.password}});state.csrf=r.csrf_token;state.user=await api('/auth/me');state.view='dashboard';shell();await refresh();}
async function confirmSale(kind,form){
 const v=f(form);
 if(kind==='pos'&&(!state.posPriceReady||Number(v.customer_id)!==state.posCustomer))throw Error('กรุณาเลือกลูกค้าและรอตรวจราคา');
 const lines=kind==='pos'?[...state.cart].filter(([id,q])=>q>0).map(([id,q])=>({product_id:Number(id),quantity:q})):state.wh.map(x=>({...x}));
 if(!lines.length)throw Error('กรุณาเลือกสินค้าก่อน');
 const body={kind,vat_price_mode:v.vat_price_mode,customer_id:Number(v.customer_id),lines,method:v.method,delivery_mode:kind==='pos'?'pickup':v.delivery_mode};
 if(kind==='pos')body.expected_total=(posTotals().total/100).toFixed(2);
 if(kind==='wholesale'){
  const entered=whEntered()-Math.round(num(v.discount)*100)+(v.delivery_mode==='pickup'?0:Math.round(num(v.shipping_fee)*100));
  if(entered<0)throw Error('ส่วนลดเกินยอดสินค้า');
  body.expected_total=(vatAmounts(entered,v.vat_price_mode).total/100).toFixed(2);
 }
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
 let x;
 try{x=await api('/api/online/orders',{method:'POST',body:{...body,idempotency_key}});}
 catch(err){
  if(kind==='pos'&&err.message.includes('ราคาหรือยอดรวมเปลี่ยน'))await loadPosPrices(state.posCustomer);
  throw err;
 }
 sessionStorage.removeItem(slot);
 if(kind==='pos')state.cart.clear();
 else{state.wh=[];form.reset();}
 state.lastSale={id:x.id,kind};
 warn(`บันทึกบิล #${x.id} สำเร็จ`);
 await refresh();
}
async function send(form){if(state.busy)return;state.busy=true;const submit=form.querySelector('button[type=submit],button:not([type])');if(submit)submit.disabled=true;try{
 const id=form.id,v=f(form);
 if(id==='login-form')await doLogin(form);
 else if(id==='create-user-form'){await api('/users',{method:'POST',body:{username:v.username,password:v.password,role:v.role}});warn('สร้างบัญชีพนักงานแล้ว');await refresh();}
  else if(id==='staff-form'){await api(`/users/${Number(v.id)}`,{method:'PATCH',body:{role:v.role,active:v.active==='true'}});warn('บันทึกสิทธิ์แล้ว');await refresh();}
  else if(id==='price-form'){await api('/api/extended/prices',{method:'POST',body:{customer_id:Number(v.customer_id),product_id:Number(v.product_id),price:moneyInput(v.price)}});warn('บันทึกราคาพิเศษแล้ว');}
  else if(id==='company-form'){state.company=await api('/api/extended/company',{method:'POST',body:{legal_name:v.legal_name,tax_id:v.tax_id,branch:v.branch,address:v.address,phone:v.phone,receipt_footer:v.receipt_footer,default_paper:v.default_paper}});warn('บันทึกข้อมูลบริษัทแล้ว');}
  else if(id==='image-form'||id==='excel-form'){const endpoint=id==='image-form'?`/api/extended/products/${Number(v.product_id)}/image`:`/api/extended/excel/${v.entity}/import`;const response=await fetch(endpoint,{method:'POST',credentials:'same-origin',headers:{'X-CSRFToken':state.csrf},body:new FormData(form)});const result=await response.json().catch(()=>({}));if(!response.ok)throw Error(result.error||`อัปโหลดไม่สำเร็จ ${response.status}`);warn('นำเข้าข้อมูลสำเร็จ');await refresh();}
  else if(id==='reset-password-form'){if(v.password!==v.confirm_password)throw Error('รหัสผ่านยืนยันไม่ตรงกัน');await api(`/users/${Number(v.user_id)}/password`,{method:'POST',body:{password:v.password}});warn('ตั้งรหัสใหม่แล้ว');render();}
 else if(id==='tax-invoice-form'){
  const saleId=Number(v.sale_id);
  const result=await api('/api/extended/documents',{method:'POST',body:{kind:'tax_invoice',sale_id:saleId,buyer:{name:v.buyer_name,address:v.buyer_address,tax_id:v.buyer_tax_id,branch:v.buyer_branch}}});
  warn(`จัดทำร่าง ${result.number} แล้ว`);
  await showHistory(saleId);
 }
 else if(id==='pos-form')await confirmSale('pos',form);
 else if(id==='wh-form')await confirmSale('wholesale',form);
 else if(id==='return-add-form'){
  const line=state.returnEligible?.lines.find(x=>x.sale_line_id===Number(v.sale_line_id));
  const qty=Number(v.quantity);
  if(!line||!Number.isInteger(qty)||qty<1||qty>line.remaining_quantity)throw Error('จำนวนคืนไม่ถูกต้อง');
  if(state.returnLines.some(x=>x.sale_line_id===line.sale_line_id))throw Error('รายการคืนซ้ำ');
  state.returnReason=$('return-reason')?.value||state.returnReason;
  state.returnLines.push({sale_line_id:line.sale_line_id,quantity:qty});render();
 }
 else if(id==='return-request-form'){
  if(!state.returnEligible||!state.returnLines.length)throw Error('กรุณาระบุรายการคืน');
  const body={sale_id:state.returnEligible.sale_id,lines:state.returnLines.map(x=>({...x})),reason:v.reason};
  const bytes=new TextEncoder().encode(JSON.stringify(body));
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const slot='tb-pending-return-v1';
  let pending=null;try{pending=JSON.parse(sessionStorage.getItem(slot)||'null');}catch(_){/* ignore stale retry key */}
  const request_key=pending?.hash===hash?pending.key:uuid();
  sessionStorage.setItem(slot,JSON.stringify({hash,key:request_key}));
  const result=await api('/api/returns',{method:'POST',body:{...body,request_key}});
  sessionStorage.removeItem(slot);
  state.returnLines=[];state.returnEligible=null;state.returnReason='';
  state.returnSelected=await api(`/api/returns/${result.id}`);
  warn('บันทึกคำขอรับคืนแล้ว');await refresh();
 }
 else if(id==='return-inspect-form'){
  if(!state.returnSelected)throw Error('กรุณาเลือกรายการคืน');
  const result=await api(`/api/returns/${state.returnSelected.id}/inspect`,{method:'POST',body:{condition:v.condition,inspection_note:v.inspection_note}});
  state.returnSelected=await api(`/api/returns/${result.id}`);
  warn(result.restocked?'ตรวจรับและเพิ่มสต็อกแล้ว':'บันทึกรับคืนสินค้าชำรุดแล้ว');await refresh();
 }
 else if(id==='quote-add-form'){
  const p=state.products.find(x=>x.id===Number(v.product_id));const qty=Number(v.quantity);
  if(!p||!Number.isInteger(qty)||qty<1||qty>1000000)throw Error('ตรวจสอบสินค้าและจำนวน');
  if(state.quoteLines.length>=100||state.quoteLines.some(x=>x.product_id===p.id))throw Error('รายการซ้ำหรือเกิน 100 รายการ');
  state.quoteLines.push({product_id:p.id,quantity:qty});render();
 }
 else if(id==='quote-convert-form'){
  if(!state.quoteSelected)throw Error('ไม่พบใบเสนอราคา');
  const body={delivery_mode:v.delivery_mode,address:v.address,phone:v.phone,driver:v.driver,delivery_date:v.delivery_date||null,note:v.note||''};
  const result=await api(`/api/quotations/${state.quoteSelected.id}/convert`,{method:'POST',body});
  state.quoteSelected=await api(`/api/quotations/${state.quoteSelected.id}`);
  warn(`แปลงเป็นบิลขาย #${result.sale_id} สำเร็จ`);await refresh();
 }
 else if(id==='quote-form'){
  if(!state.quoteLines.length)throw Error('กรุณาเพิ่มรายการเสนอราคา');
  const payload={customer_id:Number(v.customer_id),vat_price_mode:v.vat_price_mode,expires_on:v.expires_on||null,note:v.note||'',lines:state.quoteLines.map(x=>({...x}))};
  const bytes=new TextEncoder().encode(JSON.stringify(payload));
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
  const slot='tb-pending-quote-v1';
  let pending=null;try{pending=JSON.parse(sessionStorage.getItem(slot)||'null');}catch(_){/* invalid retry metadata */}
  const request_key=pending?.hash===hash?pending.key:uuid();
  sessionStorage.setItem(slot,JSON.stringify({hash,key:request_key}));
  const result=await api('/api/quotations',{method:'POST',body:{...payload,request_key}});
  sessionStorage.removeItem(slot);
  state.quoteLines=[];state.quoteSelected=await api(`/api/quotations/${result.id}`);
  warn(`บันทึกร่าง ${result.number} แล้ว`);await refresh();
 }
 else if(id==='wh-add-form'){const p=state.products.find(x=>x.id===Number(v.product_id));const qty=Number(v.quantity);const price=Number(v.unit_price);if(!p||!Number.isInteger(qty)||qty<1||qty>p.stock||!Number.isFinite(price)||price<=0)throw Error('ตรวจสอบสินค้า จำนวนและราคาขายส่ง');const found=state.wh.find(x=>x.product_id===p.id);if(found)throw Error('รายการสินค้าซ้ำ โปรดลบรายการเดิมก่อน');state.wh.push({product_id:p.id,quantity:qty,unit_price:moneyInput(price)});render();}
 else if(id==='product-form'){await api('/products',{method:'POST',body:{sku:v.sku,name:v.name,price:moneyInput(v.price)}});warn('เพิ่มสินค้าแล้ว');await refresh();}
 else if(id==='stock-form'){await api('/stock/adjustments',{method:'POST',body:{product_id:Number(v.product_id),delta:Number(v.delta),reason:v.reason}});warn('ปรับสต๊อกแล้ว');await refresh();}
 else if(id==='customer-form'){await api('/customers',{method:'POST',body:{name:v.name,address:v.address,tax_id:v.tax_id||null}});warn('เพิ่มลูกค้าแล้ว');await refresh();}
 else if(id==='expense-form'){await api('/api/online/expenses',{method:'POST',body:{category:v.category,description:v.description,amount:moneyInput(v.amount),method:v.method}});warn('บันทึกรายจ่ายแล้ว');await refresh();}
 else if(id==='pay-form'){await api(`/api/online/sales/${Number(v.sale_id)}/payments`,{method:'POST',body:{amount:moneyInput(v.amount),method:v.method,reference:(form.dataset.reference||=`webpay-${uuid()}`)}});warn('บันทึกรับชำระแล้ว');await refresh();await showHistory(Number(v.sale_id));}
 }catch(err){warn(`ไม่สำเร็จ: ${err.message}`);}finally{state.busy=false;if(submit?.isConnected)submit.disabled=false;}}
function showPayment(id){document.getElementById('pay-panel')?.remove();const item=state.sales.find(s=>s.id===Number(id));if(!item)return;const el=$('view');el.insertAdjacentHTML('afterbegin',`<div class="card" id="pay-panel"><h2>รับชำระบิล #${id}</h2><p>ยอดค้าง ${fmt(item.balance)}</p><form id="pay-form"><input type="hidden" name="sale_id" value="${id}"><div class="grid g2">${field('จำนวนรับชำระ (บาท)','amount','number',item.balance,'min="0.01" step="0.01" required')}<div class="field"><label>รับชำระโดย</label><select name="method">${opt('cash','เงินสด')}${opt('transfer','โอนเงิน')}</select></div></div><button class="btn">บันทึกรับชำระ</button></form></div>`);window.scrollTo({top:0,behavior:'smooth'});}
async function printSale(id){const s=state.sales.find(x=>x.id===Number(id));if(!s)throw Error('ไม่พบบิล');const details=await api(`/sales/${Number(id)}`);const rows=(details.lines||[]).map(x=>`<tr><td>${esc(x.name)} × ${x.quantity}</td><td>${fmt(x.quantity*num(x.price))}</td></tr>`).join('');$('print-root').innerHTML=`<h2>หจก. ธนาบุณยภัทร</h2><p>ใบสรุปการขายตัวอย่าง<br>ไม่ใช่ใบกำกับภาษี<br>บิล #${s.id} วันที่ ${formatDate(s.date)}<br>ลูกค้า ${esc(s.customer)}</p><table>${rows}<tr><td>ยอดก่อน VAT</td><td>${fmt(s.subtotal)}</td></tr><tr><td>VAT</td><td>${fmt(s.vat)}</td></tr><tr><td><b>ยอดรวม</b></td><td><b>${fmt(s.total)}</b></td></tr><tr><td>รับชำระแล้ว</td><td>${fmt(s.paid)}</td></tr><tr><td>ค้างรับ</td><td>${fmt(s.balance)}</td></tr></table><p>เอกสารประกอบการตรวจสอบภายใน</p>`;window.print();}
async function printDelivery(id){
 const o=await api(`/api/online/orders/${Number(id)}`);
 const rows=(o.lines||[]).map(x=>`<tr><td>${esc(x.name)}<br><small>${esc(x.sku)}</small></td><td>${x.quantity}</td></tr>`).join('');
 $('print-root').innerHTML=`<h2>หจก. ธนาบุณยภัทร</h2><p><b>ใบส่งสินค้า (ตัวอย่าง)</b><br>ไม่ใช่ใบกำกับภาษี<br>เลขที่บิล #${o.id}<br>วันที่จัดส่ง ${esc(o.delivery_date||'—')}<br>ลูกค้า ${esc(o.customer)}<br>สถานที่ ${esc(o.address)}<br>ผู้ติดต่อ ${esc(o.phone)}<br>คนขับ ${esc(o.driver)}</p><table><thead><tr><th>สินค้า</th><th>จำนวน</th></tr></thead><tbody>${rows}</tbody></table><p>รับสินค้าครบถ้วน: __________________<br>วันที่รับ: __________________</p>`;
 window.print();
}
document.addEventListener('input',event=>{
 if(event.target.form?.id==='wh-form')updateWholesaleTotal();
 const key=event.target.dataset.search;
 if(!key)return;
 state.search[key]=event.target.value;
 filterVisibleRows(key);
});
document.addEventListener('change',async event=>{
 if(event.target.form?.id==='wh-form'){updateWholesaleTotal();return;}
 if(event.target.form?.id!=='pos-form')return;
 if(event.target.name==='vat_price_mode'){state.posVatMode=event.target.value;render();$('pos-form').querySelector('[name="vat_price_mode"]:checked').focus();return;}
 if(event.target.name==='method'){state.posMethod=event.target.value;return;}
 if(event.target.name==='customer_id'){
  try{await loadPosPrices(Number(event.target.value));}catch(err){warn(err.message);}
 }
});
document.addEventListener('submit',event=>{if(!event.target.matches('form'))return;event.preventDefault();send(event.target);});
document.addEventListener('click',async event=>{
 const btn=event.target.closest('button');if(!btn)return;
 try{
 if(btn.id==='toggle-nav'){
  const open=btn.getAttribute('aria-expanded')==='true';
  btn.setAttribute('aria-expanded',String(!open));
  btn.textContent=open?'เมนูทั้งหมด':'ย่อเมนู';
  $('nav').classList.toggle('expanded',!open);
  return;
 }
 if(btn.id==='retry-view'){navigate(state.view);return;}
 if(btn.dataset.posJump){const section=$(btn.dataset.posJump);section?.focus({preventScroll:true});section?.scrollIntoView({block:'start'});return;}
 if(btn.dataset.nav){navigate(btn.dataset.nav);return;}
  if(btn.dataset.customerServerSearch){const term=state.search.customers||'';const page=await api('/api/customers/lookup?q='+encodeURIComponent(term)+'&limit=100');state.customerLookupResults=page.items;state.customerHistory=null;render();if(page.next_after)warn('แสดง 100 รายชื่อแรก กรุณาระบุคำค้นให้แคบลง');return;}
  if(btn.dataset.customerClear){state.customerLookupResults=null;state.customerHistory=null;state.search.customers='';render();return;}
  if(btn.dataset.customerHistory){state.customerHistory=await api(`/api/customers/${Number(btn.dataset.customerHistory)}/history`);render();$('customer-purchase-history')?.focus({preventScroll:true});return;}
 if(btn.hasAttribute('data-quote-remove')){state.quoteLines.splice(Number(btn.dataset.quoteRemove),1);render();return;}
 if(btn.dataset.quoteTransition){
  const note=$('quote-status-note')?.value.trim();
  if(!note)throw Error('กรุณาบันทึกหมายเหตุการติดต่อลูกค้า');
  const updated=await api(`/api/quotations/${Number(btn.dataset.quoteId)}/status`,{method:'POST',body:{status:btn.dataset.quoteTransition,note}});
  state.quoteSelected=updated;warn('อัปเดตสถานะใบเสนอราคาแล้ว');await refresh();return;
 }
 if(btn.dataset.quoteDetail){state.quoteSelected=await api(`/api/quotations/${Number(btn.dataset.quoteDetail)}`);render();return;}
 if(btn.dataset.salesFilter){state.salesOutstanding=btn.dataset.salesFilter==='open';await refresh();return;}
 if(btn.hasAttribute('data-sales-more')&&state.salesCursor){
  const page=await api(`/api/online/sales?outstanding=${state.salesOutstanding?'1':'0'}&before=${state.salesCursor}`);
  state.sales.push(...page.items);state.salesCursor=page.next_before;render();return;
 }
 if(btn.id==='show-forgot'){showForgot();return;}
 if(btn.id==='show-login'){showLogin();return;}
 if(btn.id==='logout'){await api('/auth/logout',{method:'POST',body:{}});state.user=null;state.csrf=null;state.search={};state.cart.clear();state.wh=[];state.quoteLines=[];state.quotations=[];state.quoteSelected=null;state.returns=[];state.returnEligible=null;state.returnLines=[];state.returnSelected=null;state.returnReason='';state.posCustomer=0;state.posPrices.clear();state.posPriceReady=false;state.posMethod='cash';state.posVatMode='exclusive';state.lastSale=null;window.erpPrinter.disconnect();showLogin();return;}
 if(btn.dataset.add){const id=Number(btn.dataset.add);const p=state.products.find(p=>p.id===id);if(!p)return;const qty=state.cart.get(id)||0;if(qty>=p.stock)throw Error('สินค้าไม่พอ');state.cart.set(id,qty+1);render();return;}
 if(btn.dataset.dec){const id=Number(btn.dataset.dec),qty=(state.cart.get(id)||0)-1;if(qty<=0)state.cart.delete(id);else state.cart.set(id,qty);render();return;}
 if(btn.dataset.whdel!==undefined){state.wh.splice(Number(btn.dataset.whdel),1);render();return;}
 if(btn.dataset.next){await api(`/api/online/orders/${Number(btn.dataset.next)}/advance`,{method:'POST',body:{}});warn('อัปเดตสถานะจัดส่งแล้ว');await refresh();return;}
 if(btn.dataset.pay){showPayment(btn.dataset.pay);return;}
 if(btn.dataset.print){await printSale(btn.dataset.print);return;}
 if(btn.dataset.note){await printDelivery(btn.dataset.note);return;}
 if(btn.dataset.activate){await api(`/users/${Number(btn.dataset.activate)}/activate`,{method:'POST',body:{}});warn('อนุมัติผู้ใช้งานแล้ว');await refresh();return;}
 if(btn.dataset.reset){showReset(btn.dataset.reset);return;}
  if(btn.dataset.staff){showStaff(btn.dataset.staff);return;}
  if(btn.hasAttribute('data-close-history')){$('sale-history')?.remove();return;}
 if(btn.hasAttribute('data-printer-connect')){window.erpPrinter.open();return;}
 if(btn.dataset.thermalDocument){
  if(!window.erpPrinter.connected()){window.erpPrinter.open();warn('เชื่อมต่อเครื่องพิมพ์ แล้วกดพิมพ์ Bluetooth อีกครั้ง');return;}
  btn.disabled=true;
  try{
   const doc=await api(`/api/extended/documents/${Number(btn.dataset.thermalDocument)}/thermal`);
   await window.erpPrinter.print(doc);
   warn('ส่งข้อมูลไปยังเครื่องพิมพ์แล้ว');
  }finally{btn.disabled=false;}
  return;
 }
 if(btn.dataset.history){await showHistory(btn.dataset.history);return;}
  if(btn.dataset.loadPrices){state.selectedCustomer=Number($('price-customer').value);if(!state.selectedCustomer)throw Error('เลือกลูกค้าก่อน');state.specialPrices=(await api(`/api/extended/prices/${state.selectedCustomer}`)).items;render();return;}
  if(btn.dataset.removePrice){await api(`/api/extended/prices/${state.selectedCustomer}/${Number(btn.dataset.removePrice)}`,{method:'DELETE'});state.specialPrices=(await api(`/api/extended/prices/${state.selectedCustomer}`)).items;render();return;}
  if(btn.dataset.issueDoc){const payload={kind:btn.dataset.issueDoc,sale_id:Number(btn.dataset.saleId)};if(payload.kind==='receipt')payload.payment_id=Number(btn.dataset.paymentId);const result=await api('/api/extended/documents',{method:'POST',body:payload});warn(`จัดทำร่าง ${result.number} แล้ว`);await showHistory(payload.sale_id);return;}
 }catch(err){warn(err.message);}
});
document.addEventListener('change',evt=>{if(evt.target.name==='product_id'&&evt.target.closest('#wh-add-form')){const p=state.products.find(p=>p.id===Number(evt.target.value));const price=document.querySelector('#wh-add-form [name="unit_price"]');if(price)price.value=p?moneyInput(p.price):'';}});
(async()=>{if(location.hash.startsWith('#recover=')||location.hash.startsWith('#verify-email='))return;try{state.user=await api('/auth/me');await getCsrf();shell();await refresh();}catch(_){showLogin();}})();
})();
