import {useEffect,useRef,useState} from 'react';
type RecordValue={id:string;revision:number;app_type:string;draft_revision:number;source_token:string;text:string;byte_count:number;updated_at:string;verification:string};
type State={schema_version:1;task_id:string;revision:number;app_type:string;draft_revision:number;record:RecordValue|null;stale:boolean;source_current:boolean;task_changed:false;model_called:false;network_requested:false;business_verified:false;note:string};
const integer=(v:unknown,min=0)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=min;
const sha=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
function valid(v:unknown,id:string,revision:number,appType:string):v is State{
 if(!v||typeof v!=='object'||Array.isArray(v))return false;const s=v as State;
 if(s.schema_version!==1||s.task_id!==id||s.revision!==revision||s.app_type!==appType||!integer(s.draft_revision)||typeof s.stale!=='boolean'||typeof s.source_current!=='boolean'||['task_changed','model_called','network_requested','business_verified'].some(k=>s[k as keyof State]!==false)||typeof s.note!=='string'||!s.note||s.note.length>600)return false;
 if(s.record===null)return !s.stale&&!s.source_current;
 const r=s.record;return !!r&&typeof r==='object'&&r.id===id&&integer(r.revision,1)&&['workflow','advanced-chat','agent'].includes(r.app_type)&&r.draft_revision===s.draft_revision&&sha(r.source_token)&&typeof r.text==='string'&&!!r.text.trim()&&integer(r.byte_count,1)&&r.byte_count<=2000000&&new TextEncoder().encode(r.text).length===r.byte_count&&typeof r.updated_at==='string'&&r.updated_at.length<=100&&r.verification==='unconfirmed_case_json_text'&&s.stale===!s.source_current&&(!s.source_current||r.revision===revision&&r.app_type===appType);
}

export default function CaseJsonDraftPanel({taskId,revision,appType,sourceToken,text,dirty,blocked,onLoad,onActivity}:{taskId:string;revision:number;appType:string;sourceToken:string|null;text:string;dirty:boolean;blocked:boolean;onLoad:(text:string)=>boolean;onActivity:(label:string)=>void}){
 const scope=JSON.stringify([taskId,revision,appType,sourceToken]);
 const [value,setValue]=useState<State|null>(null),[loadedScope,setLoadedScope]=useState(''),[working,setWorking]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState(''),[replace,setReplace]=useState(false),[old,setOld]=useState(false);
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),latest=useRef({onLoad,onActivity});latest.current={onLoad,onActivity};
 const known=!!value&&loadedScope===scope,record=known?value.record:null,needsReplace=!!record&&dirty&&record.text!==text;
 async function request(method:'GET'|'PUT'|'DELETE'){
  if(method!=='GET'&&(working||!known||blocked||method==='PUT'&&!sourceToken))return;
  const ticket=++epoch.current,abort=new AbortController();controller.current?.abort();controller.current=abort;setWorking(true);setError('');setNotice('');setReplace(false);setOld(false);if(method==='GET')setLoadedScope('');else latest.current.onActivity(method==='PUT'?'保存样例JSON草稿':'丢弃保存的样例JSON草稿');
  const timer=setTimeout(()=>abort.abort(),10000);
  try{
   const body=method==='GET'?undefined:JSON.stringify({revision,draft_revision:value!.draft_revision,...(method==='PUT'?{source_token:sourceToken,text}:{})});
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/test-cases/draft${method==='GET'?`?revision=${revision}`:''}`,{method,body,headers:body?{'Content-Type':'application/json'}:undefined,signal:abort.signal,cache:'no-store'});
   if(ticket!==epoch.current)return;
   if(!r.ok){setLoadedScope('');const data=await r.json().catch(()=>null);throw Error(r.status===409?'草稿版本、正式来源或任务修订变化，编辑框文字保持；请读取最新副本核对，不自动重试。':typeof data?.detail==='string'?data.detail:'未取得可靠草稿回执，请读取原副本核对；本页文字保持。')}
   const v:unknown=await r.json();if(ticket!==epoch.current)return;
   if(!valid(v,taskId,revision,appType)||method!=='GET'&&value&&!(v.draft_revision===value.draft_revision||v.draft_revision===value.draft_revision+1)||v.record&&v.source_current&&sourceToken&&v.record.source_token!==sourceToken)throw Error('保存草稿的任务、版本、来源或文字范围无法核对，未载入编辑框。');
   setValue(v);setLoadedScope(scope);if(method!=='GET')setNotice(method==='PUT'?'独立草稿副本已保存；正式样例、确认和编辑框文字未改变。':'已丢弃保存副本；当前编辑框文字和正式样例未改变。');
  }catch(e){if(ticket===epoch.current){setLoadedScope('');setError(e instanceof Error?e.message:'草稿请求失败，本页文字保持。')}}finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false);if(method!=='GET')latest.current.onActivity('')}
 }
 useEffect(()=>{epoch.current++;controller.current?.abort();setValue(null);setLoadedScope('');setWorking(false);setError('');setNotice('');setReplace(false);setOld(false);void request('GET');return()=>{epoch.current++;controller.current?.abort()}},[scope]);
 function load(){
  if(!known||!record||working||blocked||!sourceToken||value.stale&&!old||needsReplace&&!replace)return;
  if(!latest.current.onLoad(record.text)){setError('任务或编辑来源变化，未载入保存草稿；当前文字保持。');return}
  setReplace(false);setOld(false);setNotice('已主动放入未确认编辑框；正式样例不变，仍须核对并保存为当前来源。');
 }
 return <section className="case-json-draft configuration-proposal"><b>独立未确认JSON草稿</b><p className="hint">半成品可先保存本机副本，重开后主动读取并放入编辑框；不自动采用、不送模型，也不改变正式样例或确认。</p>{working&&<p role="status">读取或保存草稿副本…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}<div className="actions"><button className="secondary" disabled={working} onClick={()=>void request('GET')}>读取保存的JSON草稿</button><button className="secondary" disabled={working||blocked||!known||!sourceToken||!text.trim()} onClick={()=>void request('PUT')}>保存当前文字为未确认草稿</button></div>{known&&!record&&<p className="hint">尚无保存的JSON文字副本；当前编辑框内容不会自动保存。</p>}{record&&<><p className="hint">独立草稿版本 {value!.draft_revision} · 来源修订 v{record.revision} · {record.byte_count} UTF8字节</p><details><summary>查看已保存草稿文字（未采用）</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:240,overflow:'auto'}}>{record.text}</pre></details>{value!.stale&&<label className="checkline"><input type="checkbox" checked={old} disabled={working||blocked} onChange={e=>setOld(e.target.checked)}/>将旧来源草稿仅作未确认文字参考，不沿用旧来源或确认</label>}{needsReplace&&<label className="checkline"><input type="checkbox" checked={replace} disabled={working||blocked} onChange={e=>setReplace(e.target.checked)}/>用保存副本替换本页已有未保存文字（正式样例不变）</label>}<div className="actions"><button className="secondary" disabled={working||blocked||!sourceToken||value!.stale&&!old||needsReplace&&!replace} onClick={load}>将保存草稿放入编辑框（未采用）</button><button className="secondary" disabled={working||blocked} onClick={()=>void request('DELETE')}>丢弃已保存JSON草稿</button></div><p className="hint">{value!.note}</p></>}</section>;
}
