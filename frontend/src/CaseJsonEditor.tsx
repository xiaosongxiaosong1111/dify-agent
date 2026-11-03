import {useEffect,useRef,useState} from 'react';
import CaseJsonDraftPanel from './CaseJsonDraftPanel';

type Source={schema_version:1;task_id:string;revision:number;app_type:string;source_token:string;content_sha256:string;cases_text:string;total_utf8_bytes:number;structured_editing_safe:boolean;verification:string;task_changed:false;network_requested:false;business_verified:false;note:string};
const sha=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
async function digest(text:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(n=>n.toString(16).padStart(2,'0')).join('')}

export default function CaseJsonEditor({taskId,revision,appType,cases,structuredDirty,disabled,onSafety,onDirty,onSaved,onActivity}:{taskId:string;revision:number;appType:string;cases:unknown[];structuredDirty:boolean;disabled:boolean;onSafety:(safe:boolean,reason:string)=>void;onDirty:(value:boolean)=>void;onSaved:(value:unknown)=>void;onActivity:(label:string)=>void}){
 const [source,setSource]=useState<Source|null>(null),[text,setText]=useState(''),[dirty,setDirty]=useState(false),[loading,setLoading]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),dirtyRef=useRef(false),latest=useRef({onSafety,onDirty,onSaved,onActivity});latest.current={onSafety,onDirty,onSaved,onActivity};
 const current=source?.task_id===taskId&&source.revision===revision&&source.app_type===appType?source:null;
 const observedCases=JSON.stringify(cases);
 useEffect(()=>{
  const ticket=++epoch.current,abort=new AbortController();controller.current?.abort();controller.current=abort;setLoading(true);setError('');setSource(null);latest.current.onSafety(false,'正在核对完整保存值，普通表单暂不可编辑。');
  const timer=setTimeout(()=>abort.abort(),10000);
  (async()=>{try{
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/test-cases/editor?revision=${revision}`,{signal:abort.signal,cache:'no-store'});if(!r.ok)throw Error('无法完整读取当前样例原文，请刷新任务后核对；未写入或自动重试。');
   const v=await r.json() as Source;if(ticket!==epoch.current)return;
   if(!v||v.schema_version!==1||v.task_id!==taskId||v.revision!==revision||v.app_type!==appType||!sha(v.source_token)||!sha(v.content_sha256)||typeof v.cases_text!=='string'||!Number.isSafeInteger(v.total_utf8_bytes)||v.total_utf8_bytes<2||v.total_utf8_bytes>2000000||new TextEncoder().encode(v.cases_text).length!==v.total_utf8_bytes||typeof v.structured_editing_safe!=='boolean'||v.verification!=='saved_case_json_editor_only'||v.task_changed!==false||v.network_requested!==false||v.business_verified!==false||typeof v.note!=='string'||!v.note||v.note.length>600||await digest(v.cases_text)!==v.content_sha256||!Array.isArray(JSON.parse(v.cases_text)))throw Error('样例原文的任务、修订、摘要或范围无法核对；未载入或写入。');
   if(ticket!==epoch.current)return;
   const matched=JSON.stringify(JSON.parse(v.cases_text))===JSON.stringify(cases),safe=v.structured_editing_safe&&matched;
   if(dirtyRef.current){latest.current.onSafety(false,'来源已变化，原文草稿未重新绑定。');setError('已保存修订发生变化，未覆盖或重新绑定本页原文草稿；请先保留文字，再撤销并重新核对。');return}
   latest.current.onSafety(safe,safe?'':matched?'此保存值含普通表单不能无损往返的数值类型或其他字段；请使用完整JSON原文编辑。':'刚读取的样例与页面保存记录不一致，普通表单不可编辑；请刷新任务。');
   setSource(v);setText(v.cases_text);
  }catch(e){if(ticket===epoch.current){setSource(null);latest.current.onSafety(false,'完整来源尚未核对，普通表单暂不可编辑。');setError(e instanceof Error?e.message:'样例原文读取失败。')}}finally{clearTimeout(timer);if(ticket===epoch.current)setLoading(false)}})();
  return()=>{epoch.current++;abort.abort();clearTimeout(timer)};
 },[taskId,revision,appType,observedCases,refresh]);
 function edit(value:string){setText(value);const changed=value!==source?.cases_text;dirtyRef.current=changed;setDirty(changed);latest.current.onDirty(changed)}
 function discard(){dirtyRef.current=false;setDirty(false);latest.current.onDirty(false);if(current)setText(current.cases_text);else setText('');setError('');setRefresh(x=>x+1)}
 async function save(){
  if(!current||!dirty||disabled||structuredDirty||working||loading)return;
  try{if(new TextEncoder().encode(text).length>2000000||!Array.isArray(JSON.parse(text)))throw Error()}catch{setError('样例原文须为2MB内的完整JSON数组；草稿保持，未保存。');return}
  const ticket=++epoch.current,abort=new AbortController();controller.current=abort;setWorking(true);setError('');latest.current.onActivity('保存完整样例JSON');const timer=setTimeout(()=>abort.abort(),15000);
  try{
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/test-cases/editor`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,source_token:current.source_token,cases_text:text}),signal:abort.signal});
   if(ticket!==epoch.current)return;
   if(!r.ok){const body=await r.json().catch(()=>null);if(r.status===409){setSource(null);latest.current.onSafety(false,'原文来源或执行状态待重新核对。')}throw Error(r.status===409?'来源、执行状态或修订变化，原文草稿保持；请保留文字后撤销并重新读取，不自动重试。':typeof body?.detail==='string'?body.detail:'保存未取得有效回执，原文保持；请核对历史，不直接重发。')}
   const task=await r.json();if(ticket!==epoch.current)return;
   if(!task||task.id!==taskId||task.app_type!==appType||!Number.isSafeInteger(task.revision)||task.revision<revision||!Array.isArray(task.test_cases))throw Error('保存回执归属无法核对；原文保持，请核对历史，不直接重发。');
   dirtyRef.current=false;setDirty(false);latest.current.onDirty(false);latest.current.onSaved(task);
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'保存未取得有效回执，原文保持，请核对历史。')}finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false);latest.current.onActivity('')}
 }
 return <section className="case-json-editor configuration-proposal"><b>完整样例JSON原文</b>{loading&&<p role="status">核对完整保存值…</p>}{error&&<p role="alert">{error}</p>}<p className="hint">需要保留1.0等数值类型、大整数或附加字段时使用此入口；不通过浏览器对象重新序列化。实际变更保存为新修订并须重新确认；不改变判定语义或扩展普通试跑的数值范围。</p><details><summary>展开完整JSON编辑</summary>{current&&<p className="hint">{current.note}</p>}<textarea aria-label="完整样例JSON原文" className="json" value={text} readOnly={!current} disabled={disabled||structuredDirty||working||loading} onChange={e=>edit(e.target.value)} style={{width:'100%',minHeight:300}}/><p className="hint">{structuredDirty?'普通表单已有未保存修改，请先保存或撤销，不能混合覆盖。':dirty?'完整原文有未保存修改，其他操作暂不可用；不会自动保存。':'仅显示本次已保存JSON值，尚未修改。'}</p><div className="actions"><button className="primary" disabled={!current||!dirty||disabled||structuredDirty||working||loading} onClick={()=>void save()}>保存完整JSON</button><button className="secondary" disabled={structuredDirty||working||loading} onClick={discard}>{dirty?'撤销完整JSON编辑':'重新读取完整JSON'}</button></div><CaseJsonDraftPanel taskId={taskId} revision={revision} appType={appType} sourceToken={current?.source_token??null} text={text} dirty={dirty} blocked={disabled||structuredDirty||working||loading} onLoad={value=>{if(!current||disabled||structuredDirty||working||loading)return false;edit(value);return true}} onActivity={onActivity}/></details></section>;
}
