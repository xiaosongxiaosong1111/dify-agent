import {useEffect,useRef,useState} from 'react';
export type MessageIntent={request_id:string;revision:number;content:string;mode:'review'|'discussion';stream_response:boolean;compact_history:boolean};
export function useMessageRequests(){
 const intents=useRef<Record<string,MessageIntent>>({});const [,render]=useState(0);
 return {
  pending:(taskId:string)=>intents.current[taskId],
  prepare(taskId:string,revision:number,content:string,mode:'review'|'discussion',stream_response:boolean,compact_history=false){
   const old=intents.current[taskId];
   if(old){if(old.content!==content||old.mode!==mode||old.stream_response!==stream_response||old.compact_history!==compact_history)throw Error('上一条发送结果尚待核对；请先只读核对原发送，再决定新消息。');return old}
   const value={request_id:crypto.randomUUID(),revision,content,mode,stream_response,compact_history};intents.current[taskId]=value;render(n=>n+1);return value;
  },
  clear(taskId:string,requestId:string){if(intents.current[taskId]?.request_id===requestId){delete intents.current[taskId];render(n=>n+1)}}
 }
}

type Receipt={task_id:string;request_id:string;revision:number;operation_id:string|null;state:string;result_revision:number|null;note:string};
const labels:Record<string,string>={applied:'原回复已保存',failed:'原请求失败且已停止',paused:'原请求已暂停',interrupted:'原请求已中断',discarded:'旧修订结果未应用',stale:'修订已变化，原结果未应用',running:'原请求仍在进行',unknown:'原结果尚未核实',no_provider:'原请求没有派发模型'};
export default function MessageRequestRecovery({taskId,intent,onResolved,onForget,disabled=false}:{disabled?:boolean;taskId:string;intent:MessageIntent|undefined;onResolved:(task:unknown,intent:MessageIntent)=>void;onForget:(intent:MessageIntent)=>void}){
 const [state,setState]=useState<Receipt|null>(null),[error,setError]=useState(''),[missing,setMissing]=useState(false),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),generation=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{setState(null);setError('');setMissing(false);setAck(false);setBusy(false);return()=>{generation.current++;controller.current?.abort()}},[taskId,intent?.request_id]);
 if(!intent)return null;
 const read=async()=>{
  const original=intent,ticket=++generation.current,abort=new AbortController();controller.current=abort;setBusy(true);setError('');setMissing(false);setAck(false);setState(null);const timer=setTimeout(()=>abort.abort(),12000);
  try{
   const response=await fetch(`/api/tasks/${taskId}/message-requests/${original.request_id}`,{signal:abort.signal,cache:'no-store'});
   if(generation.current!==ticket)return;
   if(response.status===404){setMissing(true);setState(null);setError('本机未找到该发送标识；未自动重发。请先核对对话历史，再决定是否结束本次待确认发送。');return}
   if(!response.ok)throw Error(`原发送回执读取失败（HTTP ${response.status}），未重发。`);
   const receipt:Receipt=await response.json();if(receipt.task_id!==taskId||receipt.request_id!==original.request_id||receipt.revision!==original.revision||!Object.keys(labels).includes(receipt.state)||typeof receipt.note!=='string')throw Error('回执身份、修订或状态无法核对，未采用也未重发。');
   if(generation.current!==ticket)return;setState(receipt);
   if(!['running','unknown'].includes(receipt.state)){
    const result=await fetch(`/api/tasks/${taskId}`,{signal:abort.signal,cache:'no-store'});if(!result.ok)throw Error('原回执已读，但当前任务读取失败；未重新派发。');
    const task=await result.json();if(task.id!==taskId)throw Error('当前任务身份不匹配，未采用结果。');if(generation.current===ticket)onResolved(task,original);
   }
  }catch(e){if(generation.current===ticket)setError(abort.signal.aborted?'读取超时或已取消，原标识保留，未重发。':e instanceof TypeError?'本机回执读取失败，原标识保留，未重发。':e instanceof Error?e.message:'回执读取失败，未重发。')}
  finally{clearTimeout(timer);if(generation.current===ticket)setBusy(false)}
 }
 return <div className="message-request-recovery callout amber" style={{display:'block'}}><b>当前发送标识已保留</b><p className="hint">结果未返回时保留原文字和发送标识。同一标识不会再次调用模型；读取回执不会发送消息。此标识仅在本页按任务暂存，刷新后请查看任务已有对话及执行记录。</p><p className="hint" style={{overflowWrap:'anywhere'}}>{intent.request_id} · 发送时v{intent.revision}</p><button className="secondary" disabled={busy||disabled} onClick={()=>void read()}>只读核对原发送</button>{busy&&<p role="status">正在读取原发送回执…</p>}{state&&<p>{labels[state.state]}。{state.note}</p>}{error&&<p role="alert">{error}</p>}{missing&&<><label><input type="checkbox" checked={ack} onChange={event=>setAck(event.target.checked)}/>我已核对对话历史，结束本次待确认发送；不立即重发。</label><button className="secondary" disabled={!ack||busy||disabled} onClick={()=>onForget(intent)}>结束待确认发送</button></>}</div>;
}
