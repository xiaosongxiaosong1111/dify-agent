import {useEffect,useRef,useState} from 'react';
type Page='需求'|'配置'|'流程'|'构建'|'运行'|'历史';
type Step={schema_version:1;task_id:string;revision:number;app_type:string;snapshot_token:string;state:string;target_page:Page|null;title:string;reason:string;checklist:string[];verification:string;task_changed:boolean;network_requested:boolean;automatic_execution:boolean;business_verified:boolean;note:string};
const pages:Page[]=['需求','配置','流程','构建','运行','历史'];
const states=['busy','paused','intake','requirements','plan','plan_required','configuration','build','offline','schedule','human','import','files','publication','publication_review','runtime_key','run','review','manual'];
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown,n:number)=>typeof v==='string'&&v.length>0&&v.length<=n;
export default function TaskNextStep({taskId,revision,appType,scope,editing,onNavigate}:{taskId:string;revision:number;appType:string;scope:string;editing:boolean;onNavigate:(page:Page)=>void}){
 const [step,setStep]=useState<(Step&{observedScope:string})|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[refresh,setRefresh]=useState(0),epoch=useRef(0);
 useEffect(()=>{
  const ticket=++epoch.current,abort=new AbortController();setStep(null);setError('');setLoading(false);
  if(editing)return()=>{epoch.current++;abort.abort()};
  const timer=setTimeout(()=>abort.abort(),10000);setLoading(true);
  (async()=>{try{
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/next-step?revision=${revision}`,{signal:abort.signal});
   if(!response.ok)throw Error('unavailable');const v:unknown=await response.json();if(ticket!==epoch.current)return;
   if(!object(v)||v.schema_version!==1||v.task_id!==taskId||v.revision!==revision||v.app_type!==appType||typeof v.snapshot_token!=='string'||!/^[a-f0-9]{64}$/.test(v.snapshot_token)||typeof v.state!=='string'||!states.includes(v.state)||!(v.target_page===null||pages.includes(v.target_page as Page))||!text(v.title,160)||!text(v.reason,800)||!text(v.note,500)||!Array.isArray(v.checklist)||v.checklist.length>4||v.checklist.some(x=>!text(x,500))||v.verification!=='saved_local_navigation_advice_only'||['task_changed','network_requested','automatic_execution','business_verified'].some(k=>v[k]!==false))throw Error('invalid');
   setStep({...v as Step,observedScope:scope});
  }catch{if(ticket===epoch.current)setError('暂时无法读取当前进度建议；请核对任务或手动选择页面，未执行或重试任何操作。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setLoading(false)}})();
  return()=>{epoch.current++;clearTimeout(timer);abort.abort()};
 },[taskId,revision,appType,scope,editing,refresh]);
 const current=step?.task_id===taskId&&step.revision===revision&&step.app_type===appType&&step.observedScope===scope?step:null;
 return <section className="task-next-step configuration-proposal"><div className="listhead"><b>下一步建议</b><small>仅读已保存进度</small></div>{editing?<p className="hint">当前有未保存编辑；请先保存或撤销，再根据最新进度给出建议。这里不会切换页面或修改内容。</p>:<>{loading&&<p role="status">读取本机进度…</p>}{error&&<p className="hint" role="alert">{error}</p>}{current&&<><p style={{margin:'8px 0'}}><strong>{current.title}</strong></p><details><summary>原因与待核对事项</summary><p className="hint">{current.reason}</p><ul>{current.checklist.map((line,i)=><li key={i}>{line}</li>)}</ul><p className="hint">{current.note}</p></details>{current.target_page&&<button className="secondary" onClick={()=>{if(!editing&&current.task_id===taskId&&current.revision===revision&&current.target_page)onNavigate(current.target_page)}}>前往{current.target_page}页</button>}</>}<button className="secondary" disabled={loading} onClick={()=>setRefresh(v=>v+1)}>重新读取建议</button></>}</section>;
}
