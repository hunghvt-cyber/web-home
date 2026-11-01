// Shared validation: no shell commands are assembled on the relay.
export const ID = /^[a-f0-9]{32}$/;
export function command(value) {
  if (!value || typeof value !== 'object' || !ID.test(value.id || '') || !Number.isSafeInteger(value.seq) || value.seq < 1) throw Error('Invalid command');
  const {op, id, seq} = value;
  if (['create','attach','resize'].includes(op)) {
    const {cols,rows}=value;
    if (!Number.isInteger(cols)||cols<20||cols>300||!Number.isInteger(rows)||rows<5||rows>100) throw Error('Invalid size');
    return {op,id,seq,cols,rows};
  }
  if(op==='input' && typeof value.data==='string' && value.data.length>0 && new TextEncoder().encode(value.data).length<=8192) return {op,id,seq,data:value.data};
  if(['detach','terminate','list'].includes(op)) return {op,id,seq};
  throw Error('Invalid operation');
}
