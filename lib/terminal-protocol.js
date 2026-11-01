// Shared validation: no shell commands are assembled on the relay.
export const ID = /^[a-f0-9]{32}$/;
export function command(value) {
  if (!value || typeof value !== 'object' || !ID.test(value.id || '') || !Number.isSafeInteger(value.seq) || value.seq < 1) throw Error('Invalid command');
  const {op, id, seq} = value;
  if(op==='audit') {
    const {action,cloud,path='',scanId,offset=0,group}=value;
    if(!['roots','start','status','groups','files','pause','resume'].includes(action))throw Error('Invalid audit action');
    if(action==='roots'||action==='status'&&!scanId)return {op,id,seq,action};
    if(action==='start'){
      if(!['gdrive','koofr'].includes(cloud)||typeof path!=='string'||path.length>1024||/[\x00-\x1f:]/.test(path)||path.split('/').some(p=>p==='..'||p==='.'))throw Error('Invalid scan scope');
      return {op,id,seq,action,cloud,path};
    }
    if(!ID.test(scanId||'')||!Number.isSafeInteger(offset)||offset<0||offset>10000000)throw Error('Invalid scan');
    if(action==='files'&&(typeof group!=='string'||!/^\d+:(MD5:[a-f0-9]{32}|SHA256:[a-f0-9]{64})$/.test(group)))throw Error('Invalid group');
    return {op,id,seq,action,scanId,offset,...(action==='files'?{group}:{})};
  }
  if (['create','attach','resize'].includes(op)) {
    const {cols,rows}=value;
    if (!Number.isInteger(cols)||cols<20||cols>300||!Number.isInteger(rows)||rows<5||rows>100) throw Error('Invalid size');
    return {op,id,seq,cols,rows};
  }
  if(op==='input' && typeof value.data==='string' && value.data.length>0 && new TextEncoder().encode(value.data).length<=8192) return {op,id,seq,data:value.data};
  if(['detach','terminate','list'].includes(op)) return {op,id,seq};
  throw Error('Invalid operation');
}
