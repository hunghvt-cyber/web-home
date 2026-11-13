const labels={ok:'Hoạt động',pass:'Đạt',warn:'Cần kiểm tra',fail:'Có lỗi',unknown:'Chưa xác minh'};
const time=value=>{if(!value)return null;const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleString('vi-VN',{timeZone:'Asia/Ho_Chi_Minh'}):null};
const bytesGiB=value=>typeof value==='number'&&Number.isSafeInteger(value)&&value>=0?(value/1024**3).toFixed(1)+' GiB':null;
const percent=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=100?value.toFixed(1)+'%':null;
const display=(id,value,stale,hasTimestamp)=>{document.getElementById(id).textContent=stale?'Dữ liệu cũ':(hasTimestamp?(value||'Chưa có dữ liệu'):'Chưa có dữ liệu')};
async function refresh(){
  const stamp=document.getElementById('updated');
  try{
    const response=await fetch(window.PORTAL_STATUS_URL||'/status.json',{cache:'no-store',signal:AbortSignal.timeout(15000)});
    if(!response.ok)throw new Error('HTTP');
    const data=await response.json();
    if(data.schema!==1)throw new Error('schema');
    const snapshotTime=time(data.updated_at);
    const age=snapshotTime?Date.now()-new Date(data.updated_at).getTime():Infinity;
    const receivedTime=time(data._report?.received_at);
    const receivedMs=receivedTime?Date.parse(data._report.received_at):NaN;
    const receivedAge=Date.now()-receivedMs;
    const measurementAgeAtReceipt=receivedMs-Date.parse(data.updated_at);
    const stale=data._report
      ? (!receivedTime||receivedAge>45*60*1000||receivedAge< -5*60*1000||!snapshotTime||measurementAgeAtReceipt>15*60*1000||measurementAgeAtReceipt< -5*60*1000)
      : !!snapshotTime&&(age>15*60*1000||age< -5*60*1000);
    for(const key of ['cam1','cam2','nas','maintenance','retention']){
      const item=data[key]||{};
      const el=document.getElementById(key);
      if(key==='maintenance'||key==='retention'){
        el.textContent=key==='retention'?(item.verification_status==='VERIFIED_WITH_CURRENT_EVIDENCE'?'Đã xác minh bằng bằng chứng hiện tại':item.verification_status==='HISTORICALLY_VERIFIED'?'Đã xác minh bằng bằng chứng lịch sử':({pass:'Đạt',ok:'Đạt',warn:'Cần kiểm tra',fail:'Không đạt',unknown:'Chưa có kết quả xác nhận'}[item.state]||'Chưa có kết quả xác nhận')):(labels[item.state]||'Chưa có kết quả xác nhận');
        const detail=document.getElementById(key+'-time');
        const measured=time(item.measured_at);
        const evidence=key==='retention'&&Number.isSafeInteger(item.file_count)&&item.file_count>=0&&Number.isSafeInteger(item.byte_count)&&item.byte_count>=0
          ?' · '+item.file_count.toLocaleString('vi-VN')+' tệp · '+(item.byte_count/1024**3).toFixed(1)+' GiB':'';
        const evidenceTime=key==='retention'&&time(item.evidence_collected_at)?' · Bằng chứng hiện tại thu thập lúc '+time(item.evidence_collected_at):'';
        detail.textContent=measured?'Kết quả gần nhất · '+measured+evidence+evidenceTime:'Chưa có thời điểm kết quả';
      }else {
        const label=stale?'Dữ liệu cũ · Chưa xác minh hiện tại':!snapshotTime?'Chưa xác minh':key==='nas'?({ok:'Đủ chỗ',pass:'Đủ chỗ',warn:'Sắp đầy',fail:'Cần kiểm tra dung lượng',unknown:'Chưa xác minh'}[item.state]||labels.unknown):(labels[item.state]||labels.unknown);
        const free=key==='nas'&&snapshotTime&&!stale?bytesGiB(data.health?.vol1?.available_bytes):null;
        el.textContent=label+(free?' · Còn trống '+free:'');
      }
    }
    stamp.textContent=snapshotTime?'Đo lúc: '+snapshotTime+(receivedTime?' · Nhận lúc: '+receivedTime:'')+(stale?' · Dữ liệu cũ hoặc chưa xác minh.':'')+(data._report?.recovered_previous?' · Đang dùng bản báo cáo trước.':''):'Chưa có thời gian báo cáo';
    window.dispatchEvent(new CustomEvent('portal:nas-status',{detail:{data,stale,snapshotTime,receivedTime}}));
    const health=data.health||{};
    const healthStamp=document.getElementById('health-updated');
    healthStamp.textContent=snapshotTime?'Theo báo cáo gần nhất · '+snapshotTime+(stale?' · Dữ liệu cũ':''):'Chưa có dữ liệu';
    const root=health.root||{},vol1=health.vol1||{},ram=health.ram||{},swap=health.swap||{};
    display('health-root-used',percent(root.used_percent),stale,!!snapshotTime);
    display('health-root-free',bytesGiB(root.available_bytes),stale,!!snapshotTime);
    display('health-vol1-used',percent(vol1.used_percent),stale,!!snapshotTime);
    display('health-vol1-free',bytesGiB(vol1.available_bytes),stale,!!snapshotTime);
    display('health-ram',bytesGiB(ram.available_bytes),stale,!!snapshotTime);
    const swapValid=Number.isSafeInteger(swap.used_bytes)&&Number.isSafeInteger(swap.total_bytes)&&swap.used_bytes>=0&&swap.total_bytes>0&&swap.used_bytes<=swap.total_bytes;
    const swapUsage=swapValid?bytesGiB(swap.used_bytes)+' / '+bytesGiB(swap.total_bytes):null;
    const swapPercent=swapValid?(swap.used_bytes/swap.total_bytes*100).toFixed(1)+'%':null;
    display('health-swap-usage',swapUsage,stale,!!snapshotTime);
    display('health-swap-percent',swapPercent,stale,!!snapshotTime);
  }catch{
    window.dispatchEvent(new CustomEvent('portal:nas-status',{detail:{error:true}}));
    stamp.textContent='Không tải được báo cáo mới. Camera/NAS hiện chưa được xác minh.';
    for(const key of ['cam1','cam2','nas'])document.getElementById(key).textContent='Chưa xác minh';
    document.getElementById('health-updated').textContent='Chưa tải được báo cáo mới';
    for(const id of ['health-root-used','health-root-free','health-vol1-used','health-vol1-free','health-ram','health-swap-usage','health-swap-percent'])document.getElementById(id).textContent='Chưa có dữ liệu mới';
  }
}
refresh();
setInterval(refresh,300000);


