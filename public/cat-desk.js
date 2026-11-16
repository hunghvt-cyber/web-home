/* Read the existing report event; no extra requests or NAS work. */
(()=>{
  const desk=document.getElementById('cat-desk');
  if(!desk)return;
  const profile=document.getElementById('cat-profile');
  const wideProfile=window.matchMedia?.('(min-width: 641px)');
  if(profile&&wideProfile){
    profile.open=wideProfile.matches;
    wideProfile.addEventListener('change',event=>{profile.open=event.matches;});
  }

  const put=(id,value)=>{document.getElementById(id).textContent=value;};
  let expiry;
  function waiting(message,stamp){
    desk.dataset.mood='waiting';
    put('cat-state','Chưa xác minh NAS');
    put('cat-screen-title','Chờ tin từ NAS…');
    put('cat-screen-cameras','Camera · chưa rõ');
    put('cat-screen-storage','Ổ đĩa · chưa rõ');
    put('cat-says',message);
    put('cat-report-time',stamp||'Chưa nhận được báo cáo mới. Không thể xác nhận tình trạng hiện tại.');
  }
  window.addEventListener('portal:nas-status',({detail})=>{
    clearTimeout(expiry);
    if(detail.error){waiting('Chưa nhận tin mới, đại ca xem lại báo cáo giúp em nhé.');return;}
    const {data,stale,snapshotTime,receivedTime}=detail;
    const stamp='Đo: '+(snapshotTime||'chưa rõ')+(receivedTime?' · Nhận: '+receivedTime:'')+(data._report?.recovered_previous?' · Bản báo cáo trước.':'');
    if(stale||!snapshotTime){waiting('Sổ trực đã cũ, em chưa dám khẳng định NAS đang ổn.',stamp+' · Chưa xác minh hiện tại.');return;}
    const states=['cam1','cam2','nas'].map(key=>data[key]?.state);
    const warning=states.some(state=>['warn','fail'].includes(state));
    const verified=states.every(state=>['ok','pass'].includes(state));
    desk.dataset.mood=warning?'warn':verified?'ok':'waiting';
    put('cat-state',warning?'Có mục cần kiểm tra':verified?'Báo cáo NAS ổn':'Báo cáo chưa đủ dữ liệu');
    put('cat-screen-title',warning?'Đại ca ơi, xem sổ!':verified?'Báo cáo gần nhất: ổn':'Còn mục chưa xác minh');
    const cameras=states.slice(0,2);
    const cameraText=cameras.every(state=>['ok','pass'].includes(state))?'2/2 ổn':cameras.some(state=>['warn','fail'].includes(state))?'cần kiểm tra':'chưa rõ';
    put('cat-screen-cameras','Camera · '+cameraText);
    const free=data.health?.vol1?.available_bytes;
    put('cat-screen-storage','Ổ · '+(['warn','fail'].includes(states[2])?'cần kiểm tra':!['ok','pass'].includes(states[2])?'chưa xác minh':Number.isSafeInteger(free)&&free>=0?'trống '+(free/1024**3).toFixed(1)+' GiB':'đủ chỗ'));
    put('cat-says',warning?'Em thấy có cảnh báo trong báo cáo, đại ca kiểm tra phía dưới nhé.':verified?'Đại ca cứ thong thả. Sổ gần nhất ghi hai camera và dung lượng đều ổn.':'Em có báo cáo rồi, nhưng còn mục chưa xác minh được đại ca ạ.');
    put('cat-report-time',stamp+' · Theo báo cáo, không phải giám sát trực tiếp.');
    const validUntil=data._report?Date.parse(data._report.received_at)+45*60000:Date.parse(data.updated_at)+15*60000;
    expiry=setTimeout(()=>waiting('Đã lâu chưa có tin mới, em chờ báo cáo tiếp theo.',stamp+' · Dữ liệu cũ; chưa xác minh hiện tại.'),Math.max(0,validUntil-Date.now()+1));
  });
  const clock=document.getElementById('cat-clock');
  function tick(){clock.textContent=new Date().toLocaleTimeString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh',hour:'2-digit',minute:'2-digit'})+' · giờ Việt Nam';clock.dateTime=new Date().toISOString();}
  tick();setInterval(tick,60000);
  const reduced=window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const toggle=document.getElementById('cat-motion');
  function motion(paused){desk.classList.toggle('motion-paused',paused);toggle.setAttribute('aria-pressed',String(paused));toggle.textContent=paused?'Bật chuyển động':'Dừng chuyển động';}
  motion(!!reduced?.matches);
  reduced?.addEventListener('change',event=>motion(event.matches));
  toggle.addEventListener('click',()=>motion(!desk.classList.contains('motion-paused')));
})();
