import {useEffect,useRef,useState} from 'react';
import MappingCopyHistoryView,{type History} from './MappingCopyHistoryView';
async function request<T>(path:string):Promise<T>{let r:Response;try{r=await fetch(`/api${path}`)}catch{throw Error('本机回执接口连接中断，请稍后主动读取。')}let value;try{value=await r.json()}catch{throw Error('回执接口未返回完整JSON；不将失败当作零记录。')}if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'创建回执读取失败。');return value}
export default function MappingCopiesPanel({taskId,disabled,onActivity,onOpen}:{taskId:string;disabled:boolean;onActivity:(v:boolean)=>void;onOpen?:(task:unknown,notice:string)=>void}){
 const [history,setHistory]=useState<History|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);const live=useRef(true);
 const path=`/tasks/${taskId}/environment-mapping/copies`;
 useEffect(()=>{live.current=true;let active=true;request<History>(path).then(v=>{if(active)setHistory(v)}).catch(e=>active&&setError(e.message));return()=>{active=false;live.current=false}},[path]);
 const operate=async(fn:()=>Promise<void>)=>{if(disabled||busy)return;setBusy(true);setError('');onActivity(true);try{await fn()}catch(e){if(live.current)setError(e instanceof Error?e.message:'读取失败，不重复创建。')}finally{onActivity(false);if(live.current)setBusy(false)}};
 const read=()=>operate(async()=>{setHistory(null);const value=await request<History>(path);if(live.current)setHistory(value)});
 const open=(operationId:string)=>operate(async()=>{const row=history?.rows.find(r=>r.operation_id===operationId);if(!row||!onOpen)throw Error('请先重新读取并核对本任务的创建历史。');const result=await request<{task:unknown;created:boolean;source_unchanged:boolean}>(path+'/'+encodeURIComponent(operationId));const target=result.task as {id?:unknown;app_type?:unknown;mapping_origin?:{source_task_id?:unknown;operation_id?:unknown;verification?:unknown}}|null;
 if(result.created!==false||result.source_unchanged!==true||!target||target.id!==row.target_task_id||target.app_type!=='agent'||target.mapping_origin?.source_task_id!==taskId||target.mapping_origin.operation_id!==operationId||target.mapping_origin.verification!=='local_mapping_task_only')throw Error('创建回执归属或目标任务不一致，不打开未知任务，也不重新创建。');
 if(live.current)onOpen(result.task,'已打开已有的独立本机目标任务，没有重新创建；当前资源、保留方案和业务验收状态请以该任务为准。')});
 return <details className="mapping-copies-history"><summary>找回已创建的本机目标任务</summary><p className="hint">刷新页面后可从这里只读查找先前创建结果。不自动重复创建；目标任务后续可能已被修改，显示当前本机修订。</p>{error&&<div className="alert error" role="alert">{error}</div>}{busy&&<p role="status">正在读取本机回执…</p>}<button className="secondary" disabled={disabled||busy} onClick={()=>void read()}>刷新本机创建历史（只读）</button>{history&&<MappingCopyHistoryView history={history} disabled={disabled||busy||!onOpen} onSelect={id=>void open(id)}/>}</details>;
}
