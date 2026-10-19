import {useEffect,useRef,useState} from 'react';
export type MappingInputs={revision:number;reference_id:string;merge_token:string;document_token:string;target_environment_id:string;expected_target_connection_revision?:string|null;node_models_json:Record<string,string>;dataset_mapping:Record<string,string>;node_rerankers:Record<string,{provider:string;model:string}>;dependency_mapping:Record<string,string>;additional_dependencies:string[];acknowledge_unverified_target:boolean;acknowledge_retained_external_settings:boolean;acknowledge_dependency_consolidation?:boolean;target_document_token?:string|null;target_parallel_reviews?:Record<string,unknown>;target_loop_reviews?:Record<string,unknown>};
type RecordValue={id:string;task_id:string;draft_revision:number;source_revision:number;payload_token:string;preview_token:string;payload:MappingInputs;created_at:string;verification:string};
type State={draft_revision:number;record:RecordValue|null;stale:boolean;blocker:string|null;restorable:boolean;restore_inputs:MappingInputs|null;confirmed:boolean;can_apply:boolean;can_download:boolean;note:string;historical?:boolean};
type Props={taskId:string;disabled:boolean;payload:MappingInputs|null;previewToken:string|null;canSave:boolean;onBusy:(v:boolean)=>void;onPending:(v:boolean)=>void;onSaved:()=>void;onRestore:(p:MappingInputs)=>boolean};
function canonical(value:unknown):string{
 if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
 if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical((value as Record<string,unknown>)[k])).join(',')+'}';
 return JSON.stringify(value);
}
function normalized(p:MappingInputs){return {...p,expected_target_connection_revision:p.expected_target_connection_revision??null,acknowledge_dependency_consolidation:p.acknowledge_dependency_consolidation??false,target_document_token:p.target_document_token??null,target_parallel_reviews:p.target_parallel_reviews||{},target_loop_reviews:p.target_loop_reviews||{}}}
export function savedReplyMatches(state:State,payload:MappingInputs,previewToken:string,counter:number){
 return !!state.record&&[counter,counter+1].includes(state.draft_revision)&&state.record.draft_revision===state.draft_revision&&state.record.preview_token===previewToken&&canonical(normalized(state.record.payload))===canonical(normalized(payload));
}
function inputShape(value:MappingInputs){
 const object=(v:unknown)=>!!v&&typeof v==='object'&&!Array.isArray(v);
 if(!object(value)||!Number.isSafeInteger(value.revision)||value.revision<1||['reference_id','merge_token','document_token','target_environment_id'].some(k=>typeof (value as unknown as Record<string,unknown>)[k]!=='string'))return false;
 if([value.node_models_json,value.dataset_mapping,value.dependency_mapping].some(v=>!object(v)||Object.values(v).some(x=>typeof x!=='string'))||!object(value.node_rerankers))return false;
 return Object.values(value.node_rerankers).every(v=>object(v)&&typeof v.provider==='string'&&typeof v.model==='string')&&Array.isArray(value.additional_dependencies)&&value.additional_dependencies.every(v=>typeof v==='string')&&typeof value.acknowledge_unverified_target==='boolean'&&typeof value.acknowledge_retained_external_settings==='boolean'&&(value.acknowledge_dependency_consolidation===undefined||typeof value.acknowledge_dependency_consolidation==='boolean');
}
export function checked(value:State,taskId:string){
 if(!value||!Number.isSafeInteger(value.draft_revision)||value.draft_revision<0||typeof value.stale!=='boolean'||typeof value.restorable!=='boolean'||value.confirmed!==false||value.can_apply!==false||value.can_download!==false||typeof value.note!=='string'||value.blocker!==null&&typeof value.blocker!=='string')throw Error('流程映射进度回执结构不完整，未采用旧结果。');
 if(value.record){const r=value.record;if(r.id!==taskId||r.task_id!==taskId||!Number.isSafeInteger(r.draft_revision)||r.draft_revision<1||r.draft_revision>value.draft_revision||r.verification!=='unconfirmed_workflow_mapping_inputs'||typeof r.created_at!=='string'||!r.payload||r.payload.revision!==r.source_revision)throw Error('流程映射记录与当前任务不符，不读取未知内容。')}
 else if(value.draft_revision!==0)throw Error('流程映射版本与记录不一致，不按空进度处理。');
 if(value.restorable&&(!value.record||value.stale||!value.restore_inputs||!inputShape(value.restore_inputs)||value.restore_inputs.acknowledge_unverified_target!==false||value.restore_inputs.acknowledge_retained_external_settings!==false||value.restore_inputs.acknowledge_dependency_consolidation===true||value.restore_inputs.target_document_token!==null||Object.keys(value.restore_inputs.target_parallel_reviews||{}).length||Object.keys(value.restore_inputs.target_loop_reviews||{}).length))throw Error('恢复回执未清除旧确认或输入不完整，未填入输入。');
 return value;
}
export default function WorkflowMappingProgress(props:Props){
 const {taskId,disabled,payload,previewToken,canSave}=props;const handlers=useRef(props);handlers.current=props;
 const [current,setCurrent]=useState<State|null>(null),[history,setHistory]=useState<State|null>(null),[number,setNumber]=useState(''),[overwrite,setOverwrite]=useState(false),[busy,setBusy]=useState(false),[pending,setPending]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const alive=useRef(true),generation=useRef(0),active=useRef(false),base=`/api/tasks/${encodeURIComponent(taskId)}/workflow-environment-mapping/draft`;
 const uncertain=(value:boolean)=>{setPending(value);handlers.current.onPending(value)};
 const run=async(fn:(seq:number)=>Promise<void>,initialRead=false)=>{if(active.current||disabled&&!initialRead)return;active.current=true;setBusy(true);setError('');setNotice('');handlers.current.onBusy(true);const seq=++generation.current;try{await fn(seq)}catch(e){if(alive.current&&seq===generation.current)setError(e instanceof Error?e.message:'读取未完成，输入保持。')}finally{active.current=false;if(alive.current&&seq===generation.current){setBusy(false);handlers.current.onBusy(false)}}};
 const get=async(path:string)=>{const response=await fetch(path),value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'读取进度未完成。');return checked(value,taskId)};
 const latest=(initialRead=false)=>run(async seq=>{setCurrent(null);const value=await get(base);if(alive.current&&seq===generation.current){setCurrent(value);uncertain(false);setOverwrite(false);setNotice('已读取已存状态，尚未覆盖本页输入。')}},initialRead);
 useEffect(()=>{alive.current=true;void latest(true);return()=>{alive.current=false;generation.current++;if(active.current)handlers.current.onBusy(false)}},[taskId]);
 const save=()=>run(async seq=>{
  if(!current||pending||!canSave||!payload||!previewToken)throw Error('请先读取已存版本，并完成当前完整映射预览后保存。');
  let response:Response;try{response=await fetch(base,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,draft_revision:current.draft_revision,preview_token:previewToken})})}catch{uncertain(true);throw Error('保存结果尚未确认，请先读取已存状态；原输入保持，不自动重试。')}
  let value;try{value=await response.json()}catch{uncertain(true);throw Error('保存回执不完整，请先读取已存状态；不重复保存或覆盖输入。')}
  if(!response.ok){if(response.status>=500)uncertain(true);throw Error(typeof value.detail==='string'?value.detail:'保存未完成，请核对已存状态。')}
  let state:State;try{state=checked(value,taskId)}catch(e){uncertain(true);throw e}
  if(!savedReplyMatches(state,payload,previewToken,current.draft_revision)){uncertain(true);throw Error('保存回执与本次完整输入或版本不一致，请先读取已存状态；原输入保持。')}
  if(alive.current&&seq===generation.current){setCurrent(state);uncertain(false);setOverwrite(false);handlers.current.onSaved();setNotice('完整映射输入已保存到本机，未改变任务环境或审批；目标DSL仍须重新验证。')}
 });
 const readHistory=()=>run(async seq=>{setHistory(null);if(!/^[1-9]\d{0,15}$/.test(number)||!Number.isSafeInteger(Number(number)))throw Error('历史版本须为可精确表示的正整数，不会舍入后查询。');const value=await get(base+'/history/'+number);if(alive.current&&seq===generation.current){setHistory(value);setOverwrite(false)}});
 const restore=(state:State,historical:boolean)=>{const apply=handlers.current.onRestore;return run(async seq=>{
  if(!overwrite||pending||!state.restorable||!state.record)throw Error('请先核对记录并明确接受覆盖本页输入；保存结果未知时先读取已存状态。');
  const fresh=await get(historical?base+'/history/'+state.record.draft_revision:base);
  if(!fresh.restorable||!fresh.restore_inputs||fresh.record?.draft_revision!==state.record.draft_revision||fresh.record?.payload_token!==state.record.payload_token)throw Error(fresh.blocker||'已存输入或环境已变化，请重新读取核对；没有覆盖本页。');
  if(alive.current&&seq===generation.current){if(!apply(fresh.restore_inputs))throw Error('当前来源与该记录不一致，输入保留；请重新分析来源后核对。');setOverwrite(false);setNotice('仅填入已存输入，旧勾选与目标容器复核已清除；请重新预览。')}
 })};
 const render=(state:State|null,historical=false)=>state&&<div className="merge-conflict"><b>{historical?'历史输入':'当前已存输入'} · {state.record?`版本 ${state.record.draft_revision}`:'尚未保存'}</b><p className="hint">{state.note}</p>{state.record&&<><p>保存于 {state.record.created_at} · 来源修订 {state.record.source_revision}</p>{state.stale&&<p className="callout amber">仅供参考：{state.blocker}</p>}<details><summary>{historical?'历史':'已存'}完整映射输入（未确认）</summary><pre>{JSON.stringify(state.record.payload,null,2)}</pre></details><button className="secondary" disabled={disabled||busy||pending||!overwrite||!state.restorable} onClick={()=>void restore(state,historical)}>{historical?'明确恢复历史映射输入':'明确恢复已存映射输入'}</button></>}</div>;
 return <details className="workflow-mapping-progress"><summary>保存与恢复流程映射输入（本机未确认）</summary><p className="hint">保存完整候选的输入与摘要，不保存旧输出DSL或半成品参数向导。刷新后先分析当前来源，再读取并明确恢复；历史不是批准。</p>
  {error&&<p className="callout amber" role="alert">{error}</p>}{notice&&<p className="hint">{notice}</p>}{pending&&<p className="callout amber">保存结果待核对；请先读取已存状态，不重复写入或清除本页。</p>}
  <button className="secondary" disabled={disabled||busy} onClick={()=>void latest()}>读取已存流程映射状态（不覆盖输入）</button>
  <button className="secondary" disabled={disabled||busy||pending||!current||!canSave||!payload||!previewToken} onClick={()=>void save()}>保存完整流程映射输入（不确认）</button>
  <label className="case-required"><input type="checkbox" disabled={disabled||busy||pending} aria-label="确认恢复流程映射覆盖本页输入" checked={overwrite} onChange={e=>setOverwrite(e.target.checked)}/>已核对记录，明确接受覆盖本页模型、知识库和插件输入；旧确认不沿用</label>
  {render(current)}<label className="field"><span>流程映射历史版本号</span><input aria-label="流程映射历史版本号" value={number} disabled={disabled||busy} onChange={e=>setNumber(e.target.value)}/></label><button className="secondary" disabled={disabled||busy} onClick={()=>void readHistory()}>读取流程映射历史</button>{render(history,true)}
 </details>
}
