import {createHmac, randomBytes} from 'node:crypto';
import {HttpError} from './security.js';
export function terminalConfig(env=process.env){
  if(env.NAS_TERMINAL_ENABLED!=='true')throw new HttpError(503,'NAS Terminal chưa được kích hoạt.');
  const key=typeof env.NAS_TERMINAL_TICKET_KEY==='string'?env.NAS_TERMINAL_TICKET_KEY.trim():'';
  let u;try{u=new URL(env.NAS_TERMINAL_RELAY_URL);}catch{throw new HttpError(503,'Chưa cấu hình relay terminal.');}
  if(u.protocol!=='https:'||u.username||u.password||u.search||u.hash||u.pathname!=='/'||key.length<32||key.length>256||/\s/.test(key))throw new HttpError(503,'Cấu hình relay terminal chưa hợp lệ.');
  return {url:u.origin.replace('https:','wss:')+'/connect',key};
}
export function ticket(config,now=Date.now()){
  const claims={v:1,aud:'nas-terminal',exp:Math.floor(now/1000)+300,cid:randomBytes(16).toString('hex')};
  const payload=Buffer.from(JSON.stringify(claims)).toString('base64url');
  return {url:config.url,token:payload+'.'+createHmac('sha256',config.key).update(payload).digest('base64url'),expiresAt:claims.exp*1000};
}
