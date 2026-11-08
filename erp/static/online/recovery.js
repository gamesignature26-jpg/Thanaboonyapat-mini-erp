/* Recovery tokens stay in the URL fragment, never the request URL or storage. */
(() => {
'use strict';
const root=document.getElementById('root');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let recoveryToken='';
let csrf='';
function resetPage(username='',token=''){
 recoveryToken=token;
 root.innerHTML=`<div class="login-page"><section class="card login"><h1>กู้คืนบัญชี</h1><p>สำหรับเจ้าของและพนักงาน ใช้ลิงก์หรือรหัสกู้คืนที่ได้รับจากผู้ดูแล</p><form id="account-recovery"><div class="field"><label for="recover-user">ชื่อผู้ใช้</label><input id="recover-user" name="username" autocomplete="username" maxlength="80" value="${esc(username)}" required></div>${token?'':'<div class="field"><label for="recover-token">รหัสกู้คืน</label><input id="recover-token" name="token" autocomplete="off" maxlength="2048" required></div>'}<div class="field"><label for="recover-password">รหัสผ่านใหม่ (12–128 ตัวอักษร)</label><input id="recover-password" name="password" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></div><div class="field"><label for="recover-confirmation">ยืนยันรหัสผ่านใหม่</label><input id="recover-confirmation" name="confirmation" type="password" autocomplete="new-password" minlength="12" maxlength="128" required></div><button class="btn block">บันทึกรหัสใหม่</button></form><p id="recovery-message" role="status" aria-live="polite"></p><button class="btn secondary block" data-recovery-back>กลับไปเข้าสู่ระบบ</button><p class="small-note">ลิงก์มีอายุ 15 นาที ใช้สำเร็จได้ครั้งเดียว พนักงานขอได้จากเจ้าของ ส่วนเจ้าของที่เข้าไม่ได้ต้องให้ผู้ดูแลระบบออกลิงก์ผ่านบัญชีจัดการระบบที่ยืนยันตัวตนแล้ว</p></section></div>`;
}
async function request(path,body){
 if(!csrf){const r=await fetch('/auth/csrf',{credentials:'same-origin'});if(!r.ok)throw Error('ไม่สามารถเชื่อมต่อ กรุณาลองใหม่');csrf=(await r.json()).csrf_token;}
 const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':csrf},body:JSON.stringify(body)});
 const result=await r.json().catch(()=>({}));
 if(!r.ok)throw Error(result.error||'ดำเนินการไม่สำเร็จ กรุณาลองใหม่');
 return result;
}
document.addEventListener('click',e=>{
 const button=e.target.closest('button');if(!button)return;
 if(button.id==='show-forgot'){e.preventDefault();e.stopImmediatePropagation();resetPage();}
 if(button.hasAttribute('data-recovery-back')){recoveryToken='';location.replace('/app');}
 if(button.dataset.issueRecovery){
  e.preventDefault();e.stopImmediatePropagation();
  const view=document.getElementById('view');document.getElementById('issue-recovery')?.remove();
  view.insertAdjacentHTML('afterbegin',`<section class="card" id="issue-recovery"><h2>ออกลิงก์กู้คืนบัญชี</h2><form id="issue-recovery-form"><input type="hidden" name="uid" value="${Number(button.dataset.issueRecovery)}"><label for="owner-password">ยืนยันรหัสผ่านเจ้าของ</label><input id="owner-password" name="current_password" type="password" autocomplete="current-password" maxlength="128" required><button class="btn">สร้างลิงก์ 15 นาที</button></form><p id="issue-message" role="status"></p></section>`);
 }
},true);
document.addEventListener('submit',async e=>{
 const form=e.target;if(!['account-recovery','issue-recovery-form'].includes(form.id))return;
 e.preventDefault();e.stopImmediatePropagation();const button=form.querySelector('button');if(button.disabled)return;button.disabled=true;
 const values=Object.fromEntries(new FormData(form));const message=document.getElementById(form.id==='account-recovery'?'recovery-message':'issue-message');message.textContent='กำลังดำเนินการ…';
 try{
  if(form.id==='account-recovery'){
   if(values.password!==values.confirmation)throw Error('รหัสผ่านยืนยันไม่ตรงกัน');
   await request('/auth/recover',{...values,token:recoveryToken||values.token});recoveryToken='';form.reset();form.remove();message.textContent='ตั้งรหัสใหม่สำเร็จ กรุณากดกลับไปเข้าสู่ระบบด้วยรหัสใหม่';
  }else{
   const result=await request(`/users/${Number(values.uid)}/recovery`,{current_password:values.current_password});form.reset();
   const link=`${location.origin}/app#recover=${encodeURIComponent(result.token)}&username=${encodeURIComponent(result.username)}`;
   message.textContent='ส่งลิงก์นี้ให้เจ้าของบัญชีผ่านช่องทางส่วนตัวเท่านั้น (หมดอายุใน 15 นาที)';
   const input=document.createElement('textarea');input.readOnly=true;input.value=link;message.append(input);
  }
 }catch(error){message.textContent=error.message;}finally{button.disabled=false;}
},true);
new MutationObserver(()=>{
 document.querySelectorAll('button[data-reset]').forEach(button=>{
  if(button.parentElement.querySelector('[data-issue-recovery]'))return;
  const issue=document.createElement('button');issue.type='button';issue.className='btn secondary slim';issue.dataset.issueRecovery=button.dataset.reset;issue.textContent='ออกลิงก์กู้คืน';button.parentElement.append(issue);
 });
}).observe(root,{childList:true,subtree:true});
if(location.hash.startsWith('#recover=')){
 const params=new URLSearchParams(location.hash.slice(1));const token=params.get('recover')||'';const username=params.get('username')||'';
 history.replaceState(null,'','/app');resetPage(username,token);
}
})();
