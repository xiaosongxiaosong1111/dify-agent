import {useEffect,useRef,useState} from 'react';
import {useOwnedActivity} from './useActivityOwnership';
type Sample={id:string;task_id:string;revision:number;node_id:string;state:string;original_cleanup_verified:boolean;last_cleanup?:{verified:boolean;status:string}};
type Plan={id:string;task_id:string;revision:number;sample_id:string;sample_revision:number;node_id:string;state:string;review_token:string;resource:{id:string;name:string;image:string;operation_id:string;profile:string;state:string}|null;verification:string;task_changed:boolean;execution_result_changed:boolean;code_executed:boolean;result?:{status:string;verified:boolean;removed:boolean}};
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/,image='sha256:ceede5b903afaa20348f7ad80ebf847379dc56d886a99b9ec6a08913dacd7732';
export default function CodeSampleMaintenance({taskId,revision,blocked,onActivity}:{taskId:string;revision:number;blocked:boolean;onActivity?:(value:boolean,owner?:object)=>void}){
 const [samples,setSamples]=useState<Sample[]>([]),[selected,setSelected]=useState(''),[plan,setPlan]=useState<Plan|null>(null),[ack,setAck]=useState(false),[sent,setSent]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState('');
 const source=taskId+':'+revision+':'+selected,current=useRef(source);current.current=source;const unavailable=useRef(blocked);unavailable.current=blocked;
 const ticket=useRef(0),active=useRef(false),report=useOwnedActivity(onActivity,taskId+':'+revision);
 useEffect(()=>{ticket.current++;active.current=false;setSamples([]);setSelected('');setPlan(null);setAck(false);setSent(false);setError('');setWorking(false);return()=>{ticket.current++;report(false)}},[taskId,revision,report]);
 const row=samples.find(r=>r.id===selected);
 function valid(value:Plan){return value&&uuid.test(value.id)&&value.task_id===taskId&&value.revision===revision&&value.sample_id===selected&&uuid.test(value.sample_id)&&typeof value.review_token==='string'&&/^[a-f0-9]{64}$/.test(value.review_token)&&value.verification==='local_sample_resource_only'&&value.task_changed===false&&value.execution_result_changed===false&&value.code_executed===false&&['prepared','executing','verified','unknown'].includes(value.state)&&(value.resource===null||value.resource?.operation_id===selected&&value.resource.name==='/sierra-code-'+selected&&/^[a-f0-9]{64}$/.test(value.resource.id)&&value.resource.image===image&&value.resource.profile==='pure-python-v1')}
 async function act(kind:'history'|'prepare'|'confirm'){
  if(unavailable.current||active.current||kind!=='history'&&!row||kind==='confirm'&&(!plan||!ack||sent||plan.state!=='prepared'))return;
  active.current=true;const id=++ticket.current,stamp=source;setWorking(true);setError('');report(true);if(kind==='confirm'){setSent(true);setAck(false)}
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),kind==='confirm'?45000:15000),still=()=>id===ticket.current&&current.current===stamp;
  try{
   const payload=kind==='history'?null:kind==='prepare'?{revision,sample_id:selected}:{revision,proposal_id:plan!.id,review_token:plan!.review_token,acknowledge_cleanup:true};
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/code-sample-maintenance${kind==='history'?'':'/'+kind}`,{...(payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{cache:'no-store' as RequestCache}),signal:controller.signal});const value=await response.json();
   if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'本机维护未完成，请只读核对。');if(!still())return;
   if(kind==='history'){
    if(value.schema_version!==1||value.task_id!==taskId||value.current_revision!==revision||!Array.isArray(value.samples)||value.samples.length>20||!value.samples.every((r:Sample)=>r.task_id===taskId&&uuid.test(r.id)&&Number.isSafeInteger(r.revision)&&r.revision>0&&typeof r.node_id==='string'&&['prepared','executing','passed','failed','unknown'].includes(r.state))||new Set(value.samples.map((r:Sample)=>r.id)).size!==value.samples.length)throw Error('历史归属或当前修订无法核对，未采用列表。');
    setSamples(value.samples);if(plan){const known=Array.isArray(value.maintenance)?value.maintenance.find((p:Plan)=>p.id===plan.id):null;if(known&&valid(known)){setPlan(known);setSent(known.state==='executing');setAck(false)}}
   }else{
    if(!valid(value)||kind==='confirm'&&value.id!==plan!.id)throw Error('维护回执目标或范围不匹配，未采用结果。');
    setPlan(value);setAck(false);setSent(value.state==='executing');
    if(value.result&&typeof value.result.verified==='boolean')setSamples(xs=>xs.map(r=>r.id===selected?{...r,last_cleanup:{verified:value.result.verified,status:value.result.status}}:r));
   }
  }catch(e){if(still())setError(e instanceof Error&&e.name!=='AbortError'?e.message:'读取中断或超时；维护请求可能已到达，请只读核对保存回执，不自动重发。')}
  finally{clearTimeout(timer);if(id===ticket.current){active.current=false;setWorking(false);report(false)}}
 }
 return <details className="code-sample-maintenance configuration-proposal"><summary>本机样例历史与资源维护 · 不执行代码</summary>
  <p className="hint">明确读取最多20份本机历史（含旧修订），按原UUID、名称、标签、镜像及预览容器ID核对，只维护本次临时资源。资源已清理与原执行通过是不同事实。</p>
  <fieldset disabled={blocked||working}>
   <button className="secondary" onClick={()=>void act('history')}>读取本机样例历史与维护回执</button>
   {samples.length>0&&<label className="field"><span>原本机样例回执</span><select aria-label="待维护本机样例" value={selected} onChange={e=>{ticket.current++;setSelected(e.target.value);setPlan(null);setAck(false);setSent(false);setError('')}}><option value="">请明确选择历史记录</option>{samples.map(r=><option key={r.id} value={r.id}>v{r.revision} · {r.node_id} · {r.state} · {r.id.slice(0,8)}</option>)}</select></label>}
   {row&&<><p>原执行：v{row.revision} · {row.state}；当前任务v{revision}。{row.last_cleanup?.verified?'已单独核对资源，原执行状态保持。':row.original_cleanup_verified?'原执行回执报告已清理。':'原资源清理尚未确认。'}</p><button className="secondary" disabled={!['passed','failed','unknown'].includes(row.state)||sent} onClick={()=>void act('prepare')}>核对这份回执的本机资源</button></>}
   {plan&&<div className="callout" style={{display:'block'}}><b>{sent&&plan.state==='prepared'?'维护已请求，请只读核对保存回执':plan.state==='prepared'?'仅准备维护，尚未停止/删除':plan.state==='verified'?'本机资源已单独核对':'维护状态待核对'}</b><p>{plan.resource?`预期容器 ${plan.resource.name} · ${plan.resource.id} · ${plan.resource.state||'状态未知'}；确认后可强制停止并移除。`:'未发现对应容器；确认后再次只读核对缺失，不创建资源。'}</p><p>原样例v{plan.sample_revision}，原执行/成绩/费用保持，不重新执行代码。</p>{plan.state==='prepared'&&!sent&&<><label className="repair-ack"><input aria-label="确认仅维护本机样例资源" type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>确认只维护上述归属资源，原执行结果保持。</label><button className="primary" disabled={!ack} onClick={()=>void act('confirm')}>确认本机资源维护</button></>}{plan.result&&<p>{plan.result.verified?'已确认资源不存在或已移除；原执行状态没有升级。':'未确认清理或资源已变化，请保留回执并重新只读核对。'} · {plan.result.status}</p>}{sent&&<p>请求已提交，请先读取保存回执，不重复确认。</p>}</div>}
  </fieldset>
  {working&&<p role="status">正在核对本机归属资源…</p>}{error&&<div role="alert" className="callout amber">{error}</div>}
 </details>;
}
