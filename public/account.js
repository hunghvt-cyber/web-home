(()=>{
 const $=id=>document.getElementById(id),home=!!$('portal-account');
 let state={authenticated:false},busy=false,generation=0;
 const channel=typeof BroadcastChannel!=='undefined'?new BroadcastChannel('homepage-access'):null;
 function announce(){channel?.postMessage('changed');window.dispatchEvent(new Event('portal-auth-refresh'));}
 function update(){
  $('account-state').textContent=state.authenticated?'Đã mở khóa':'Chưa mở khóa';
  if(home){$('account-login').hidden=state.authenticated;$('account-logout').hidden=!state.authenticated;$('account-change-password').hidden=!state.authenticated;if(state.authenticated)$('password-form').hidden=true;if(!state.authenticated){$('change-password-form').hidden=true;$('change-password-form').reset();}}
  window.dispatchEvent(new CustomEvent('account-change',{detail:state}));
 }
 const show=text=>{$('account-message').textContent=text;};
 async function api(url,value){
  const r=await fetch(url,{credentials:'same-origin',cache:'no-store',...(value?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(value)}:{})});
  const data=await r.json();if(!r.ok){if(r.status===401){state={authenticated:false,expired:true};update();}const error=new Error(data.error||'Không thể thực hiện.');error.status=r.status;error.reference=/^N4-[0-9a-f]{8}$/.test(data.reference||'')?data.reference:null;throw error;}return data;
 }
 function login(){if(home){$('portal-account').open=true;$('password-form').hidden=false;$('account-password').focus();}else{window.top.location.href='/#portal-account';}}
 window.PortalAccount={api,get state(){return state;},login};
 async function refresh(){if(busy)return;const id=++generation;try{const s=await api('/api/auth');if(id===generation){state=s;update();}}catch(e){if(id===generation){state={authenticated:false};show(e.message);update();}}}
 channel?.addEventListener('message',refresh);window.addEventListener('focus',refresh);window.addEventListener('pageshow',refresh);
 // Same-origin iframes share cookies, but need their own UI refreshed after a change.
 window.addEventListener('portal-auth-refresh',()=>{for(const frame of document.querySelectorAll('iframe')){try{frame.contentWindow.dispatchEvent(new Event('portal-session-changed'));}catch{}}});
 window.addEventListener('portal-session-changed',refresh);
 document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
 if(home){
  $('account-login').addEventListener('click',login);
  $('password-form').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;busy=true;const id=++generation;$('password-submit').disabled=true;try{const s=await api('/api/auth',{action:'login',password:$('account-password').value});if(id===generation){state=s;$('password-form').reset();show('Đã mở khóa Homepage và Notes.');update();announce();}}catch(e){show(e.message);}finally{busy=false;$('password-submit').disabled=false;}});
  $('account-logout').addEventListener('click',async()=>{if(busy)return;busy=true;++generation;try{state=await api('/api/auth',{action:'logout'});$('password-form').reset();show('Đã khóa Homepage và Notes trên trình duyệt này.');update();announce();}catch(e){show(e.message);}finally{busy=false;}});
  $('account-change-password').addEventListener('click',()=>{$('change-password-form').hidden=false;$('current-password').focus();});
  $('password-cancel').addEventListener('click',()=>{$('change-password-form').reset();$('change-password-form').hidden=true;});
  $('change-password-form').addEventListener('submit',async e=>{e.preventDefault();if(busy)return;if($('new-password').value!==$('confirm-password').value){show('Hai mật khẩu mới chưa trùng nhau.');return;}busy=true;++generation;const buttons=[...e.target.querySelectorAll('button')];buttons.forEach(b=>b.disabled=true);try{state=await api('/api/auth',{action:'change-password',currentPassword:$('current-password').value,newPassword:$('new-password').value,confirmPassword:$('confirm-password').value});show('Đã đổi mật khẩu và khóa các phiên cũ. Hãy mở khóa bằng mật khẩu mới.');update();announce();login();}catch(e){show(e.message+' Nếu vừa mất kết nối khi lưu, thử mở khóa bằng mật khẩu mới trước.');}finally{$('change-password-form').reset();busy=false;buttons.forEach(b=>b.disabled=false);}});
 }
 refresh();
})();
