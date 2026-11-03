import {createSchedulesHandler} from '../lib/schedules.js';
import {createDonationsHandler} from '../lib/donations.js';
import {SNAPSHOT_URL,RUNS_URL,validateProgress,currentRun,boundedJson} from '../lib/backfill-progress.js';
export function createBackfillProgressHandler({request=fetch,now=Date.now}={}){
 return async(req,res)=>{
  res.setHeader('X-Content-Type-Options','nosniff');
  if(req.method!=='GET'){res.setHeader('Cache-Control','no-store');return res.status(405).json({code:'METHOD_NOT_ALLOWED'});}
  const read=async(url,limit)=>boundedJson(await request(url,{headers:{Accept:'application/json','User-Agent':'Homepage-backfill-progress'},signal:AbortSignal.timeout(8000),redirect:'error'}),limit);
  const [snapshotResult,runResult]=await Promise.allSettled([read(SNAPSHOT_URL,8192).then(d=>validateProgress(d,now())),read(RUNS_URL,65536).then(currentRun)]);
  const snapshot=snapshotResult.status==='fulfilled'?snapshotResult.value:null;
  const current=runResult.status==='fulfilled'?runResult.value:null;
  if(!snapshot&&!current){res.setHeader('Cache-Control','no-store');return res.status(502).json({code:'BACKFILL_PROGRESS_UNAVAILABLE'});}
  res.setHeader('Cache-Control','public, s-maxage=120, stale-while-revalidate=120');
  return res.status(200).json({snapshot,current,checked_at:new Date(now()).toISOString(),snapshot_available:!!snapshot,current_available:runResult.status==='fulfilled'});
 };
}
export function createPublicProgressHandler(options={}){
 const backfill=createBackfillProgressHandler(options),donations=createDonationsHandler(options),schedules=createSchedulesHandler(options);
 return (req,res)=>req.query?.feed==='schedules'?schedules(req,res):req.query?.feed==='donations'?donations(req,res):backfill(req,res);
}
export default createPublicProgressHandler();
