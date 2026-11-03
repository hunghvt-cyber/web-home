(()=>{
 const panel=document.getElementById('schedule-panel');if(!panel)return;
 const $=id=>document.getElementById(id),tz='Asia/Ho_Chi_Minh';
 const day=d=>new Intl.DateTimeFormat('en-CA',{timeZone:tz,year:'numeric',month:'2-digit',day:'2-digit'}).format(d);
 const clock=t=>new Date(t).toLocaleTimeString('vi-VN',{timeZone:tz,hour:'2-digit',minute:'2-digit'});
 const minute=t=>{const parts=new Intl.DateTimeFormat('en-GB',{timeZone:tz,hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(t)).split(':');return Number(parts[0])*60+Number(parts[1]);};
 const state=s=>s==='success'?['✓ Thành công','ok']:['failure','timed_out','startup_failure','action_required'].includes(s)?['✕ Lỗi','fail']:['queued','in_progress','pending','waiting','requested'].includes(s)?['◷ Đang chạy/chờ','running']:s==='cancelled'?['Đã hủy','unknown']:s==='skipped'?['Bỏ qua','unknown']:['? Chưa xác minh','unknown'];
 const node=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
 let data,busy=false;
 function render(){
  const today=day(new Date());$('schedule-date').textContent=today;
  const sources=data?.sources||[],filter=$('schedule-filter').value;
  $('schedule-coverage').textContent=sources.map(s=>(s.source==='nas'?'NAS':'GitHub')+': '+(!s.available?'chưa kết nối':s.date!==today?'bản ngày '+s.date:s.stale?'dữ liệu cũ':'cập nhật '+clock(s.measured_at))+(s.coverage?.incomplete_repositories?.length?' · có repo chưa đọc được':'')+(s.coverage?.incomplete_sources?.length?' · thiếu nguồn NAS':'')).join(' · ');
  const jobs=sources.filter(s=>s.available&&s.date===today&&(filter==='all'||filter===s.source)).flatMap(s=>s.jobs).sort((a,b)=>(a.planned[0]||a.runs[0]?.started_at||'z').localeCompare(b.planned[0]||b.runs[0]?.started_at||'z'));
  const runs=jobs.flatMap(j=>j.runs);$('schedule-summary').textContent=`${jobs.length} tác vụ · ${runs.length} lượt đã ghi nhận · ${runs.filter(r=>state(r.state)[1]==='fail').length} lỗi · ${jobs.reduce((n,j)=>n+j.planned.filter(t=>Date.parse(t)>Date.now()).length,0)} mốc sắp tới`;
  const list=$('schedule-list'),timeline=$('schedule-timeline');list.replaceChildren();timeline.replaceChildren(node('div',undefined,'schedule-axis'));
  for(let h=0;h<=24;h+=3){const e=node('span',String(h).padStart(2,'0')+':00','schedule-hour');e.style.left=h/24*100+'%';timeline.append(e);}
  const now=node('div',undefined,'schedule-now');now.style.left=minute(new Date())/1440*100+'%';timeline.append(now);
  let pi=0,ri=0;
  function marker(t,label,actual,status,details){const idx=actual?ri++:pi++,lane=idx%4,top=actual?190+lane*28:110-lane*28;const b=node('button',undefined,'schedule-marker '+(actual?'actual':'planned')+' schedule-'+status);b.type='button';b.style.left=Math.min(96,minute(t)/1440*100)+'%';b.style.top=top+'px';b.style.setProperty('--stem',(actual?top-147:137-top)+'px');b.title=clock(t)+' · '+label;b.setAttribute('aria-label',b.title);b.append(node('span',clock(t)+' '+label));b.onclick=()=>{details.open=true;details.scrollIntoView({block:'nearest',behavior:'smooth'});};timeline.append(b);}
  for(const j of jobs){const details=node('details',undefined,'schedule-job'),summary=node('summary');summary.append(node('small',(j.planned[0]?clock(j.planned[0]):'—')+' · '+(j.source==='nas'?'NAS':'GitHub')+' · '+j.group),node('strong',j.name));const latest=j.runs.at(-1);summary.append(node('span',!j.enabled?' · Tạm dừng':latest?' · '+state(latest.state)[0]:' · '+(j.planned.some(t=>Date.parse(t)<Date.now())?'? Chưa thấy lượt chạy':'Chưa đến giờ')));details.append(summary,node('p',j.schedule.join(' / ')));
   if(j.coverage==='next-only')details.append(node('p','Systemd chỉ cung cấp lần chạy gần nhất và mốc kế tiếp; chưa có lịch sử đầy đủ trong ngày.'));
   if(j.coverage==='schedule-only')details.append(node('p','Cron có lịch, chưa có bằng chứng thực thi.'));
   const ul=node('ul');for(const r of [...j.runs].sort((a,b)=>a.started_at.localeCompare(b.started_at))){const li=node('li',clock(r.started_at)+' · '+state(r.state)[0]+' · '+r.event+(r.finished_at?' · '+Math.max(0,Math.round((Date.parse(r.finished_at)-Date.parse(r.started_at))/60000))+' phút':''));if(r.url){const a=node('a',' · Xem log');a.href=r.url;a.target='_blank';a.rel='noopener noreferrer';li.append(a);}ul.append(li);}details.append(ul);list.append(details);
   // Frequent jobs are grouped; individual runs remain in the detail list.
   const planned=j.planned.length>8?j.planned.slice(0,1):j.planned,actual=j.runs.length>8?j.runs.slice(-1):j.runs;
   planned.forEach(t=>marker(t,j.name+(j.planned.length>8?' (lặp lại)':''),false,'unknown',details));actual.forEach(r=>marker(r.started_at,j.name,true,state(r.state)[1],details));
  }
  if(!jobs.length)list.append(node('p','Chưa có lịch hôm nay từ nguồn đã chọn.','schedule-empty'));
 }
 async function load(){if(busy)return;busy=true;$('schedule-refresh').disabled=true;try{const r=await fetch('/api/backfill-progress?feed=schedules',{signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error();data=await r.json();render();}catch{$('schedule-summary').textContent='Không tải được lịch. Dữ liệu đang hiển thị có thể đã cũ.';}finally{busy=false;$('schedule-refresh').disabled=false;}}
 $('schedule-filter').onchange=render;$('schedule-refresh').onclick=load;load();setInterval(()=>{if(!document.hidden)load();},300000);
})();
