(()=>{
 const $=id=>document.getElementById(id),api=(value)=>window.PortalAccount.api('/api/nas-terminal',value);
 const uuid=()=>crypto.randomUUID().replaceAll('-','');
 let ws=null,online=false,seq=0,selected=null,ids=[],term=null,fit=null,attached=false,connecting=false,authGeneration=0,renewTimer=null;
 const pending=new Set();
 const message=text=>{$('message').textContent=text;};
 function controls(){
  const ready=ws?.readyState===WebSocket.OPEN&&online;
  $('new-session').disabled=!ready||ids.length>=3;$('refresh').disabled=!ready;
  $('disconnect').disabled=!ws;$('connect').disabled=connecting||!!ws;
  for(const id of ['paste','ctrl-c','tab-key','escape','send-paste'])$(id).disabled=!ready||!attached;
  $('terminate').disabled=!ready||!selected;
  $('empty').hidden=!!selected;
 }
 function size(){if(fit){try{fit.fit();}catch{}}return {cols:Math.max(20,Math.min(300,term?.cols||80)),rows:Math.max(5,Math.min(100,term?.rows||24))};}
 function send(op,extra={}){
  if(!online||ws?.readyState!==WebSocket.OPEN){message('Chưa kết nối NAS. Input chưa được gửi.');return false;}
  const c={op,id:selected||uuid(),seq:++seq,...extra};
  if(pending.size>=128){message('Có nhiều input chưa xác nhận. Ngắt kết nối và kiểm tra phiên trước khi nhập tiếp.');return false;}
  try{ws.send(JSON.stringify({type:'command',command:c}));pending.add(c.seq);return true;}catch{message('Chưa rõ input đã tới NAS chưa. Không tự gửi lại.');return false;}
 }
 function initTerm(){if(term)return;term=new Terminal({cursorBlink:true,fontSize:14,scrollback:2000,theme:{background:'#0b1018',foreground:'#e4eaf4'},allowProposedApi:false,disableStdin:true});fit=new FitAddon.FitAddon();term.loadAddon(fit);term.open($('terminal'));term.onData(data=>{if(attached)send('input',{data});});}
 function tabs(){
  $('sessions').replaceChildren();
  ids.forEach((id,i)=>{const b=document.createElement('button');b.type='button';b.role='tab';b.textContent='Phiên '+(i+1);b.setAttribute('aria-selected',String(selected===id));b.onclick=()=>attach(id);$('sessions').append(b);});controls();
 }
 function attach(id,create=false){
  if(!online)return;
  if(selected&&attached)send('detach');
  initTerm();selected=id;attached=false;term.options.disableStdin=true;term.reset();tabs();
  send(create?'create':'attach',{...size()});
 }
 function disconnected(text){
  online=false;attached=false;connecting=false;if(term)term.options.disableStdin=true;
  $('connection').textContent='Đã ngắt kết nối';
  message(text+(pending.size?' Có input chưa được xác nhận; kiểm tra kết quả trước khi gửi lại.':''));
  pending.clear();controls();
 }
 function close(){clearTimeout(renewTimer);const old=ws;ws=null;old?.close();disconnected('Các phiên shell vẫn được giữ trên NAS.');}
 async function connect(){
  if(ws||connecting)return;connecting=true;controls();const generation=authGeneration;
  try{
   const t=await api({action:'connect'});if(generation!==authGeneration)return;
   const socket=new WebSocket(t.url);ws=socket;controls();
   socket.onopen=()=>{
    socket.send(JSON.stringify({type:'auth',token:t.token}));
    renewTimer=setTimeout(()=>{close();connect();},Math.max(1000,t.expiresAt-Date.now()-15000));
   };
   socket.onmessage=e=>{
    if(socket!==ws)return;
    let m;try{m=JSON.parse(e.data);}catch{return;}
    if(m.type==='ready'||m.type==='online'){
     online=m.type==='online'||m.online;connecting=false;
     $('connection').textContent=online?'NAS online':'Relay đã nối · NAS offline';
     if(online)send('list');controls();
    }else if(m.type==='offline'){disconnected('NAS mất kết nối relay. Bấm Kết nối lại sau khi ngắt kết nối.');}
    else if(m.type==='sessions'){
     ids=m.sessions.filter(id=>/^[a-f0-9]{32}$/.test(id)).slice(0,3);
     if(selected&&!ids.includes(selected)){selected=null;attached=false;}
     tabs();if(ids.length&&!attached)attach(selected||ids[0]);
    }else if(m.type==='attached'){
     if(m.id!==selected)return;attached=true;term.options.disableStdin=false;size();term.focus();
     if(!ids.includes(m.id))ids.push(m.id);tabs();message('Đã mở phiên. Rời trang vẫn giữ shell chạy.');
    }else if(m.type==='output'&&m.id===selected){
     try{term.write(Uint8Array.from(atob(m.data),c=>c.charCodeAt(0)));}catch{message('Không đọc được output.');}
    }else if(m.type==='detached'&&m.id===selected){attached=false;term.options.disableStdin=true;message(m.reason);controls();}
    else if(m.type==='terminated'){ids=ids.filter(id=>id!==m.id);if(selected===m.id){selected=null;attached=false;term?.reset();}tabs();message('Đã kết thúc phiên.');}
    else if(m.type==='ack'){pending.delete(m.seq);}
    else if(m.type==='error'){pending.delete(m.seq);message(m.error);}
   };
   socket.onerror=()=>message('Không kết nối được relay.');
   socket.onclose=()=>{if(socket!==ws)return;clearTimeout(renewTimer);ws=null;disconnected('Kết nối đã đóng hoặc quyền terminal hết hạn. Bấm Kết nối để tiếp tục.');};
  }catch(e){message(e.message);if(e.status===403)$('unlock-panel').hidden=false;}finally{connecting=false;controls();}
 }
 $('connect').onclick=connect;$('disconnect').onclick=close;
 $('new-session').onclick=()=>attach(uuid(),true);$('refresh').onclick=()=>send('list');
 $('ctrl-c').onclick=()=>send('input',{data:'\x03'});$('tab-key').onclick=()=>send('input',{data:'\t'});$('escape').onclick=()=>send('input',{data:'\x1b'});
 $('terminate').onclick=()=>{if(selected&&confirm('Kết thúc phiên này và các chương trình trong phiên?'))send('terminate');};
 $('copy').onclick=async()=>{if(!term)return;try{term.selectAll();await navigator.clipboard.writeText(term.getSelection());term.clearSelection();message('Đã copy nội dung terminal.');}catch{message('Không copy được; chọn nội dung để copy thủ công.');}};
 $('paste').onclick=async()=>{try{$('paste-input').value=await navigator.clipboard.readText();}catch{}$('paste-panel').open=true;$('paste-input').focus();};
 $('send-paste').onclick=()=>{const data=$('paste-input').value;if(!data)return;if(new TextEncoder().encode(data).length>8192){message('Mỗi lần gửi tối đa 8 KiB.');return;}if(send('input',{data})){$('paste-input').value='';term?.focus();}};
 $('unlock-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{await api({action:'unlock',password:$('terminal-password').value});$('unlock-panel').hidden=true;message('Đã mở quyền terminal trong 15 phút.');await connect();}catch(e){message(e.message);}finally{$('terminal-password').value='';button.disabled=false;}};
 window.addEventListener('account-change',e=>{
  $('unlock-form').hidden=!e.detail.authenticated;
  if(!e.detail.authenticated){authGeneration++;close();$('unlock-panel').hidden=false;}
 });
 let resizeTimer;new ResizeObserver(()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(()=>{if(attached)send('resize',size());},150);}).observe($('terminal'));
 window.addEventListener('pagehide',close);controls();
})();
