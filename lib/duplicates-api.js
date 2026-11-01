import {owner,sameOrigin,body,reply,fail,HttpError} from './security.js';
import {terminalConfig,ticket} from './terminal-ticket.js';
export function createDuplicatesHandler({authorize=owner,config=terminalConfig,mint=ticket}={}){
  return async(req,res)=>{try{
    if(req.method!=='POST')throw new HttpError(405,'Phương thức không hỗ trợ.');
    sameOrigin(req);await authorize(req,res);
    if(body(req).action!=='connect')throw new HttpError(400,'Thao tác không hợp lệ.');
    return reply(res,200,mint(config(),Date.now(),'nas-duplicates'));
  }catch(error){return fail(res,error);}};
}
export default createDuplicatesHandler();
