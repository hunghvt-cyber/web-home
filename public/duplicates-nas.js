(()=>{
  const $=id=>document.getElementById(id),uuid=()=>crypto.randomUUID().replaceAll('-','');
  const names={gdrive:'Google Drive',koofr:'Koofr'},states={running:'Đang quét',pausing:'Đang tạm dừng',paused:'Đã tạm dừng',interrupted:'Bị gián đoạn',failed:'Chưa hoàn tất',complete:'Đã quét xong'};
  let ws=null,online=false,seq=0,scan=null,offset=0,groupScan=null,poll=null,renew=null,connecting=false,auth=false,epoch=0,pickerReady=false,selectedLocation=null,browsed=null,pickerBusy=false,pickerEpoch=0;
  const pending=new Map();
  const message=text=>{$('nas-scan-message').textContent=text;};
  const bytes=n=>new Intl.NumberFormat('vi-VN',{maximumFractionDigits:2}).format(n/1024/1024)+' MiB';
  function controls(){
    const ready=auth&&online&&ws?.readyState===WebSocket.OPEN;
    $('nas-scan-connect').disabled=!auth||connecting||!!ws;
    for(const id of ['nas-scan-cloud','nas-scan-refresh'])$(id).disabled=!ready;
    $('nas-scan-start').disabled=!ready||!selectedLocation||['running','pausing'].includes(scan?.state);
    $('nas-folder-open').disabled=!ready||!pickerReady;
    for(const id of ['nas-folder-root','nas-folder-reload','nas-folder-more'])$(id).disabled=!ready||pickerBusy;
    $('nas-folder-up').disabled=!ready||pickerBusy||!browsed?.parent;
    for(const button of document.querySelectorAll('.cloud-folder'))button.disabled=!ready||pickerBusy;
    $('nas-folder-choose').disabled=!ready||pickerBusy||!browsed||['running','pausing'].includes(scan?.state);
    $('nas-scan-pause').disabled=!ready||scan?.state!=='running';
    $('nas-scan-resume').disabled=!ready||!['paused','failed','interrupted'].includes(scan?.state);
  }
  function stop(){
    clearInterval(poll);clearTimeout(renew);poll=null;renew=null;
    const old=ws;ws=null;old?.close();online=false;connecting=false;pickerBusy=false;pickerEpoch++;
    for(const req of pending.values()){clearTimeout(req.timer);req.reject(new Error('Mất kết nối. Lượt quét đang chạy vẫn được giữ; kết nối lại để kiểm tra.'));}pending.clear();controls();
  }
  function request(action,extra={}){
    if(!online||ws?.readyState!==WebSocket.OPEN)return Promise.reject(new Error('NAS chưa kết nối.'));
    const id=uuid(),number=++seq;
    return new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>{pending.delete(number);reject(new Error('Chưa nhận được xác nhận. Không tự gửi lại; xem Lượt gần nhất trước khi thử tiếp.'));},20000);
      pending.set(number,{id,resolve,reject,timer});
      try{ws.send(JSON.stringify({type:'command',command:{op:'audit',id,seq:number,action,...extra}}));}
      catch{clearTimeout(timer);pending.delete(number);reject(new Error('Không gửi được yêu cầu.'));}
    });
  }
  function clearGroups(){groupScan=null;offset=0;$('nas-scan-groups').replaceChildren();$('nas-scan-results').hidden=true;$('nas-scan-more').hidden=true;}
  async function groupPage(){
    if(!scan||scan.state!=='complete')return;
    const ident=scan.id,stamp=epoch;
    const result=await request('groups',{scanId:ident,offset});
    if(stamp!==epoch||scan?.id!==ident)return;
    $('nas-scan-results').hidden=false;
    if(offset===0&&!result.groups.length){const p=document.createElement('p');p.textContent='Không tìm thấy nhóm trùng có checksum phù hợp.';$('nas-scan-groups').append(p);}
    for(const group of result.groups){
      const details=document.createElement('details');details.className='duplicate-group';
      const summary=document.createElement('summary');summary.textContent=`${group.copies} bản · ${bytes(group.size)}/file · dư ${bytes(group.size*(group.copies-1))}`;details.append(summary);
      const list=document.createElement('ol');details.append(list);
      let fileOffset=0,loaded=false,busy=false;
      const more=document.createElement('button');more.type='button';more.textContent='Xem thêm file';more.hidden=true;details.append(more);
      async function files(){
        if(busy)return;busy=true;more.disabled=true;
        try{
          const data=await request('files',{scanId:ident,group:group.hash,offset:fileOffset});
          if(stamp!==epoch||scan?.id!==ident)return;
          for(const file of data.files){const li=document.createElement('li');li.textContent=file.path;list.append(li);}
          loaded=true;fileOffset=data.nextOffset;more.hidden=fileOffset===null;
        }catch(error){message(error.message);}finally{busy=false;more.disabled=false;}
      }
      details.addEventListener('toggle',()=>{if(details.open&&!loaded)files();});more.onclick=files;
      $('nas-scan-groups').append(details);
    }
    offset=result.nextOffset;$('nas-scan-more').hidden=offset===null;
  }
  async function render(result){
    scan=result.scan||null;controls();
    if(!scan){$('nas-scan-progress').textContent='Chưa có lượt quét trên NAS.';clearGroups();return;}
    $('nas-scan-progress').textContent=`${names[scan.cloud]} / ${scan.path||'(toàn cloud)'} · ${states[scan.state]||scan.state} · ${scan.files.toLocaleString('vi-VN')} file · ${scan.unhashed.toLocaleString('vi-VN')} file thiếu checksum · ${scan.foldersDone}/${scan.foldersDiscovered} thư mục đã biết · cập nhật ${new Date(scan.updatedAt*1000).toLocaleString('vi-VN')}`;
    message(scan.error||'Kết nối NAS · chỉ đọc. Số thư mục có thể tăng trong lúc khám phá; chưa phải tổng toàn kho.');
    if(scan.state==='complete'&&groupScan!==scan.id){clearGroups();groupScan=scan.id;try{await groupPage();}catch(error){groupScan=null;message(error.message);}}
    else if(scan.state!=='complete')clearGroups();
  }
  async function refresh(latest=false){const stamp=epoch;try{const data=await request('status',!latest&&scan?{scanId:scan.id}:{});if(stamp===epoch)await render(data);}catch(error){message(error.message);}}
  async function connect(){
    if(ws||connecting||!auth)return;connecting=true;controls();const stamp=epoch;
    try{
      const ticket=await window.PortalAccount.api('/api/auth?service=duplicates',{action:'connect'});
      if(stamp!==epoch||!auth)return;
      const socket=new WebSocket(ticket.url);ws=socket;
      socket.onopen=()=>{socket.send(JSON.stringify({type:'auth',token:ticket.token}));renew=setTimeout(()=>{stop();connect();},Math.max(1000,ticket.expiresAt-Date.now()-15000));};
      socket.onmessage=async event=>{
        if(ws!==socket)return;let value;try{value=JSON.parse(event.data);}catch{return;}
        if(value.type==='ready'||value.type==='online'){
          online=value.type==='online'||value.online;connecting=false;controls();
          if(!online){message('Relay đã nối nhưng NAS đang offline.');return;}
          try{
            const roots=await request('roots');pickerReady=roots.version>=2;
            for(const option of $('nas-scan-cloud').options)option.disabled=!roots.clouds.includes(option.value);
            if(!roots.clouds.includes($('nas-scan-cloud').value))$('nas-scan-cloud').value=roots.clouds[0]||'';
            if(!pickerReady){message('Cần cập nhật bộ quét trên NAS để chọn thư mục.');controls();return;}
            await refresh();clearInterval(poll);poll=setInterval(()=>{if(online&&pending.size===0)refresh();},5000);
          }catch(error){message(error.message);}
        }else if(value.type==='offline'){stop();message('NAS mất kết nối; bấm Kết nối NAS để kiểm tra lại.');}
        else if(value.type==='audit'||value.type==='error'){
          const req=pending.get(value.seq);if(!req)return;
          if(value.type==='audit'&&req.id!==value.requestId)return;
          clearTimeout(req.timer);pending.delete(value.seq);
          if(value.type==='error')req.reject(new Error(value.error));else req.resolve(value.result);
        }
      };
      socket.onerror=()=>message('Không kết nối được NAS relay.');
      socket.onclose=()=>{if(ws===socket){stop();message('Kết nối đã đóng. Lượt quét trên NAS vẫn được giữ.');}};
    }catch(error){message(error.message);}finally{connecting=false;controls();}
  }
  $('nas-scan-connect').onclick=connect;
  $('nas-scan-refresh').onclick=()=>{epoch++;clearGroups();refresh(true);};
  async function startScan(){
    if(!selectedLocation)return;const selected={...selectedLocation};$('nas-scan-start').disabled=true;epoch++;clearGroups();
    try{await render(await request('start',{cloud:selected.cloud,location:selected.location}));}catch(error){message(error.message);}finally{controls();}
  }
  $('nas-scan-form').onsubmit=async event=>{event.preventDefault();await startScan();};
  async function browse(location,more=false){
    if(!online||!pickerReady)return;
    const cloud=$('nas-scan-cloud').value,stamp=++pickerEpoch;
    const previous=browsed;pickerBusy=true;controls();
    if(!more){browsed=null;$('nas-folder-list').replaceChildren();$('nas-folder-more').hidden=true;}
    $('nas-folder-status').textContent='Đang tải thư mục…';
    try{
      const result=await request('browse',{cloud,...(location?{location}:{}),...(more?{offset:previous.nextOffset,listing:previous.listing}:{})});
      if(stamp!==pickerEpoch||cloud!==$('nas-scan-cloud').value)return;
      browsed=result;$('nas-folder-title').textContent=names[cloud]+' / '+(result.path||'(gốc cloud)');
      for(const folder of result.folders){
        const button=document.createElement('button');button.type='button';button.className='cloud-folder';
        button.textContent='📁 '+folder.name+(folder.duplicateCount>1?' ('+folder.duplicateIndex+'/'+folder.duplicateCount+')':'')+' ›';
        button.onclick=()=>browse(folder.location);$('nas-folder-list').append(button);
      }
      $('nas-folder-more').hidden=result.nextOffset===null;
      $('nas-folder-status').textContent=$('nas-folder-list').children.length?'Chạm thư mục để mở, hoặc quét thư mục đang xem.':'Không có thư mục con. Có thể quét thư mục này.';
    }catch(error){if(stamp===pickerEpoch){$('nas-folder-status').textContent=error.message;}}
    finally{if(stamp===pickerEpoch){pickerBusy=false;controls();}}
  }
  $('nas-folder-open').onclick=()=>{$('nas-folder-picker').hidden=false;browse(selectedLocation?.cloud===$('nas-scan-cloud').value?selectedLocation.location:undefined);};
  $('nas-folder-close').onclick=()=>{pickerEpoch++;pickerBusy=false;$('nas-folder-picker').hidden=true;controls();};
  $('nas-folder-root').onclick=()=>browse();
  $('nas-folder-up').onclick=()=>{if(browsed?.parent)browse(browsed.parent);};
  $('nas-folder-reload').onclick=()=>browse(browsed?.location);
  $('nas-folder-more').onclick=()=>{if(browsed&&browsed.nextOffset!==null)browse(browsed.location,true);};
  $('nas-folder-choose').onclick=async()=>{
    if(!browsed||pickerBusy)return;
    selectedLocation={cloud:browsed.cloud,location:browsed.location,path:browsed.path};
    $('nas-scan-scope').textContent=names[browsed.cloud]+' / '+(browsed.path||'(toàn cloud)');
    $('nas-folder-picker').hidden=true;await startScan();
  };
  $('nas-scan-cloud').addEventListener('change',()=>{
    pickerEpoch++;pickerBusy=false;selectedLocation=null;browsed=null;
    $('nas-scan-scope').textContent='Chưa chọn thư mục.';$('nas-folder-list').replaceChildren();
    if(!$('nas-folder-picker').hidden)browse();controls();
  });
  for(const action of ['pause','resume'])$('nas-scan-'+action).onclick=async()=>{if(!scan)return;try{await render(await request(action,{scanId:scan.id}));}catch(error){message(error.message);}};
  $('nas-scan-more').onclick=async()=>{const button=$('nas-scan-more');button.disabled=true;try{await groupPage();}catch(error){message(error.message);}finally{button.disabled=false;}};
  window.addEventListener('account-change',event=>{
    auth=event.detail.authenticated;$('nas-scan-workspace').hidden=!auth;
    if(!auth){epoch++;stop();scan=null;selectedLocation=null;browsed=null;pickerReady=false;clearGroups();$('nas-folder-picker').hidden=true;$('nas-folder-list').replaceChildren();$('nas-scan-scope').textContent='Chưa chọn thư mục.';$('nas-scan-progress').textContent='';message('Mở khóa Homepage để kết nối NAS.');}
    else{if(!ws)message('Bấm Kết nối NAS. Bộ quét cần được cài trên NAS trước.');controls();}
  });
  window.addEventListener('pagehide',stop);controls();
})();
