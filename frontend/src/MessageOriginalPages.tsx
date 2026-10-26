import {useEffect,useMemo,useRef,useState} from 'react';

type Labels={role:string;purpose:string;record_source:string;context_revision:number|null;result_revision:number|null};
type Page={task_id:string;revision:number;message_index:number;source_id:string;source_token:string;content_sha256:string;source_length:number;source_bytes:number;role:string;purpose:string;record_source:string;context_revision:number|null;result_revision:number|null;content_chunk:string;page_start:number;page_end:number;has_previous:boolean;has_next:boolean;complete_message:boolean;note:string};
const positive=(v:unknown)=>Number.isSafeInteger(v)&&Number(v)>0?Number(v):null;
const sha=async(bytes:Uint8Array)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('');
function part(text:string,start:number,end:number){let count=0,a=0,b=0;for(const char of text){if(count===start)a=b;if(count===end)break;b+=char.length;count++}return text.slice(a,b)}

export default function MessageOriginalPages({taskId,revision,index,message,text}:{taskId:string;revision:number;index:number;message:Record<string,unknown>;text:string}){
 const labels:Labels={role:typeof message.role==='string'?message.role:'unknown',purpose:['review','discussion'].includes(String(message.purpose))?String(message.purpose):'unknown',record_source:['model','system','user'].includes(String(message.source))?String(message.source):'unknown',context_revision:positive(message.context_revision),result_revision:positive(message.result_revision)},labelKey=JSON.stringify(labels);
 const source=useMemo(()=>({taskId,revision,index,text,labels:JSON.parse(labelKey) as Labels}),[taskId,revision,index,text,labelKey]);
 const [open,setOpen]=useState(false),[page,setPage]=useState<Page|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),current=useRef(source);current.current=source;
 useEffect(()=>{epoch.current++;controller.current?.abort();setOpen(false);setPage(null);setError('');setBusy(false);return()=>{epoch.current++;controller.current?.abort()}},[source]);
 const close=()=>{epoch.current++;controller.current?.abort();setOpen(false);setPage(null);setError('');setBusy(false)};
 const read=async(offset:number,token:string|null=null)=>{
  const captured=source,ticket=++epoch.current,active=new AbortController();controller.current?.abort();controller.current=active;setOpen(true);setBusy(true);setError('');const live=()=>current.current===captured&&ticket===epoch.current;const timer=setTimeout(()=>active.abort(),12000);
  try{
   if(captured.text.length>2_000_000)throw Error('此原话超过本入口2MB UTF8完整核对范围；未发送正文或截断冒充完整。');
   const bytes=new TextEncoder().encode(captured.text);if(bytes.length>2_000_000)throw Error('此原话超过本入口2MB UTF8完整核对范围；未发送正文或截断冒充完整。');
   const digest=await sha(bytes);if(!live())return;let length=0;for(const _ of captured.text)length++;
   const response=await fetch(`/api/tasks/${encodeURIComponent(captured.taskId)}/history/message-page`,{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',signal:active.signal,body:JSON.stringify({revision:captured.revision,message_index:captured.index,content_sha256:digest,labels:captured.labels,source_token:token,offset})});
   const value=await response.json().catch(()=>null);if(!live())return;
   if(!response.ok)throw Error(typeof value?.detail==='string'?value.detail:`原话分页读取失败（HTTP ${response.status}），未采用正文。`);
   if(!value||value.schema_version!==1||value.task_id!==captured.taskId||value.revision!==captured.revision||value.message_index!==captured.index||value.source_id!==`message:${captured.index}`||value.verification!=='saved_message_page_only'||value.task_modified!==false||value.model_called!==false||value.external_network_requested!==false||value.business_verified!==false||value.content_sha256!==digest||value.source_length!==length||value.source_bytes!==bytes.length||!(/^[a-f0-9]{64}$/).test(value.source_token)||token!==null&&value.source_token!==token||Object.entries(captured.labels).some(([k,v])=>value[k]!==v))throw Error('原话来源、摘要或读取范围无法核对，未展示正文。');
   const end=Math.min(length,offset+4000);
   if(value.page_size_limit!==4000||value.page_start!==offset||value.page_end!==end||typeof value.content_chunk!=='string'||value.content_chunk!==part(captured.text,offset,end)||value.has_previous!==(offset>0)||value.has_next!==(end<length)||value.complete_message!==(offset===0&&end===length)||typeof value.note!=='string')throw Error('原话页码、正文或完整性无法核对，未展示片段。');
   setPage(value);
  }catch(e){if(live()){setPage(null);setError(active.signal.aborted?'原话读取已取消或超时，没有自动重发。':e instanceof TypeError?'本机原话读取失败，未采用片段。':e instanceof Error?e.message:'原话读取失败。')}}finally{clearTimeout(timer);if(live())setBusy(false)}
 };
 return <div className="message-original-pages"><button type="button" className="secondary" disabled={busy} onClick={()=>void read(0)}>核对完整单条原话（分页）</button>{open&&<section aria-label={`分页原话 message:${index}`}><p className="hint">仅核对本任务保存的一条原话，每页最多4000字符；当前页不是其余页已读、模型已读或本次批准的证明，不修改或发送模型。</p>{busy&&<p role="status">正在只读核对原话来源…</p>}{error&&<p role="alert">{error}</p>}{page&&<><small>{page.source_id} · {page.role==='user'?'用户':'助手'} · {page.complete_message?'完整单条原话':`本页字符${page.page_start+1}—${page.page_end} / ${page.source_length}，其余未在本页显示`}</small><pre aria-label="本页原话" style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:280,overflowY:'auto'}}>{page.content_chunk}</pre><div className="actions"><button className="secondary" disabled={busy||!page.has_previous} onClick={()=>void read(0,page.source_token)}>原话首页</button><button className="secondary" disabled={busy||!page.has_previous} onClick={()=>void read(Math.max(0,page.page_start-4000),page.source_token)}>原话上一页</button><button className="secondary" disabled={busy||!page.has_next} onClick={()=>void read(page.page_end,page.source_token)}>原话下一页</button><button className="secondary" disabled={busy||!page.has_next} onClick={()=>void read(Math.floor((page.source_length-1)/4000)*4000,page.source_token)}>原话末页</button></div><p className="hint">{page.note}</p></>}<button type="button" className="secondary" onClick={close}>关闭原话分页</button></section>}</div>;
}
