/* Thanabunyapat One: server-backed web app. No localStorage for business data. */
(() => {
'use strict';
const root = document.getElementById('root');
const toast = document.getElementById('toast');
const state = {user:null,csrf:null,view:'dashboard',products:[],customers:[],sales:[],orders:[],expenses:[],users:[],summary:null,cart:new Map(),wh:[],quoteLines:[],quotations:[],quoteSelected:null,returns:[],returnsCursor:null,suppliers:[],purchases:[],purchaseCursor:null,purchaseLines:[],purchaseSelected:null,costEvidence:null,receivablesData:null,billingBatches:[],billingCursor:null,billingSelected:null,creditDrafts:[],creditCursor:null,creditSelected:null,billingCustomerId:null,billingEligible:[],billingEligibleCursor:null,returnEligible:null,returnLines:[],returnSelected:null,returnReason:'',vatRate:7,busy:false,company:{},specialPrices:[],selectedCustomer:0,imageIds:[],posCustomer:0,posPrices:new Map(),posPriceReady:false,posMethod:"cash",customerLookupResults:null,customerHistory:null,salesOutstanding:false,salesCursor:null,search:{},posVatMode:'exclusive',lastSale:null};
const labels = {dashboard:'ภาพรวมธุรกิจ',pos:'ขายหน้าร้าน POS',wholesale:'ขายส่ง / จัดส่ง',sales:'บิลขาย / ลูกหนี้',billing_batches:'ใบวางบิลรวม',credit_drafts:'ใบลดหนี้ร่าง',quotations:'ใบเสนอราคา',returns:'รับคืนสินค้า',purchases:'จัดซื้อและรับสินค้า',inventory:'สินค้าและสต๊อก',customers:'ลูกค้า',expenses:'ค่าใช้จ่าย',reports:'รายงาน',users:'ผู้ใช้งาน',prices:'ราคาพิเศษ',settings:'ตั้งค่าบริษัท'};
const roleLabels = {admin:'เจ้าของระบบ',sales:'พนักงานขาย',warehouse:'พนักงานคลัง',accountant:'พนักงานบัญชี'};
const navGroups = [
 ['งานขาย',['dashboard','pos','wholesale','sales','billing_batches','credit_drafts','quotations','returns']],
 ['ข้อมูลร้าน',['inventory','customers','prices','purchases']],
 ['หลังร้าน',['expenses','reports','users','settings','operations']],
];
const roleViews = {
 admin:Object.keys(labels), sales:['dashboard','pos','wholesale','sales','billing_batches','quotations','returns','inventory','customers','prices'],
 warehouse:['dashboard','wholesale','inventory','returns','purchases'], accountant:['dashboard','wholesale','sales','billing_batches','credit_drafts','quotations','returns','purchases','inventory','customers','expenses','reports'],
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
  const base=['dashboard','reports','pos','wholesale','sales','billing_batches','credit_drafts','quotations','returns','purchases','inventory','customers','prices'].includes(needs);
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
  if(needs==='billing_batches'){
   const batches=await api('/api/billing-batches');
   state.billingBatches=batches.items;state.billingCursor=batches.next_before;
   if(state.billingCustomerId){
    const available=await api('/api/billing-batches/eligible?customer_id='+state.billingCustomerId);
    state.billingEligible=available.items;state.billingEligibleCursor=available.next_before;
   }
  }
  if(needs==='credit_drafts'){
   const page=await api('/api/credit-note-drafts');
   state.creditDrafts=page.items;state.creditCursor=page.next_before;
  }
  if(needs==='quotations')state.quotations=(await api('/api/quotations')).items;
  if(needs==='returns'){const page=await api('/api/returns');state.returns=page.items;state.returnsCursor=page.next_before;}
  if(needs==='purchases'){
   const [vendors,orders]=await Promise.all([api('/api/suppliers'),api('/api/purchases')]);
   state.suppliers=vendors.items;state.purchases=orders.items;state.purchaseCursor=orders.next_before;
  }
  if(needs==='reports'&&['admin','accountant'].includes(state.user.role)){
   const [cost,receivables]=await Promise.all([
    api('/api/reports/cost-evidence?limit=50'),api('/api/reports/receivables?limit=50')
   ]);
   state.costEvidence=cost;state.receivablesData=receivables;
  }
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
function billingBatches(){
 const canCreate=['admin','accountant'].includes(state.user.role);
 const available=state.billingEligible.map(x=>`<tr><td><label><input type="checkbox" name="sale_ids" value="${x.sale_id}"> บิล #${x.sale_id}</label></td><td>${formatDate(x.sale_date)}</td><td>${fmt(x.outstanding)}</td></tr>`).join('');
 const batches=state.billingBatches.map(x=>`<tr><td>${esc(x.number)}</td><td>${esc(x.customer_name)}</td><td>${fmt(x.snapshot_total)}</td><td>${x.status==='draft'?'ร่าง':'ยกเลิกแล้ว'}</td><td><button type="button