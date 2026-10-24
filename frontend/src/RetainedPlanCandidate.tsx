import {useEffect,useRef,useState} from 'react';
import CandidateFieldSelection from './CandidateFieldSelection';
import CandidateTextMapping from './CandidateTextMapping';
import BooleanFormatPreview from './BooleanFormatPreview';
type Candidate={task_id:string;planning_run_id:string;input_revision:number;current_revision:number;is_current_revision:boolean;app_type:string;plan_text:string;source_sha256:string;byte_count:number;verification:string;formal_plan_changed:boolean;network_requested:boolean;platform_checked:boolean;business_verified:boolean};
export type RetainedDraft={taskId:string;revision:number;text:string};
const keys='app_type,business_verified,byte_count,current_revision,formal_plan_changed,input_revision,is_current_revision,network_requested,plan_text,planning_run_id,platform_checked,source_sha256,task_id,verification';
export default function RetainedPlanCandidate({taskId,revision,runId,inputRevision,appType,blocked,onLoad}:{taskId:string;revision:number;runId:string;inputRevision:number;appType:string;blocked:boolean;onLoad:(draft:RetainedDraft)=>boolean}){
 const [value,setValue]=useState<Candidate|null>(null),[reading,setReading]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');const epoch=useRef(0);
 useEffect(()=>{epoch.current++;setValue(null);setReading(false);setError('');setNotice('');return()=>{epoch.current++}},[taskId,revision,runId,inputRevision,appType]);
 async function read(){const ticket=epoch.current;setReading(true);setValue(null);setError('');setNotice('');try{
  const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/planning/${encodeURIComponent(runId)}/candidate`);const v=await response.json() as Candidate;
  if(!response.ok)throw Error('候选读取未通过，请核对规划记录；未载入或修改草稿。');
  if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).sort().join(',')!==keys||v.task_id!==taskId||v.planning_run_id!==runId||v.current_revision!==revision||!Number.isSafeInteger(v.input_revision)||v.input_revision!==inputRevision||v.input_revision<1||v.is_current_revision!==(v.input_revision===revision)||v.app_type!==appType||v.verification!=='retained_candidate_unverified'||v.formal_plan_changed!==false||v.network_requested!==false||v.platform_checked!==false||v.business_verified!==false||typeof v.plan_text!=='string'||v.plan_text.length>2000000||typeof v.source_sha256!=='string'||!/^[a-f0-9]{64}$/.test(v.source_sha256)||!Number.isSafeInteger(v.byte_count))throw Error('候选归属或未验证标志不匹配，未载入草稿。');
  const bytes=new TextEncoder().encode(v.plan_text);if(bytes.length!==v.byte_count||bytes.length>2000000)throw Error('候选大小不匹配，未载入草稿。');
  const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  if(hash!==v.source_sha256)throw Error('候选原文摘要不匹配，未载入草稿。');
  const parsed=JSON.parse(v.plan_text);if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw Error('候选不是完整计划对象，未载入草稿。');
  if(ticket===epoch.current)setValue(v);
 }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'候选读取失败，当前编辑保持。')}finally{if(ticket===epoch.current)setReading(false)}}
 const visible=value&&value.task_id===taskId&&value.current_revision===revision&&value.planning_run_id===runId&&value.input_revision===inputRevision&&value.app_type===appType?value:null;
 return <div className="retained-plan-candidate"><p className="hint">保留候选可能仍有缺节点、配置或代码错误；只读取原文，不修复、不保存正式方案，也不运行。文字来自后台已保存对象的完整JSON，不是供应商响应的逐字复原；不会从截断预览补齐。</p>
 <button className="secondary" disabled={reading||blocked} onClick={()=>void read()}>读取保留流程候选原文</button>
 {reading&&<p role="status">正在读取本机候选...</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 {visible&&<><p>输入修订 v{visible.input_revision} · {visible.byte_count} 字节 · SHA256 {visible.source_sha256.slice(0,12)}</p>{!visible.is_current_revision&&<p>这是历史修订候选，仅供查看，不能放入当前草稿。</p>}
 <details><summary>查看候选原文（未验证）</summary><pre>{visible.plan_text}</pre></details>
 <button className="secondary" disabled={blocked||reading||!visible.is_current_revision} onClick={()=>{if(onLoad({taskId,revision,text:visible.plan_text}))setNotice('已放入未保存流程草稿；请修正并后台校验，尚未保存或确认。')}}>放入未保存流程草稿</button>{visible.is_current_revision&&<><BooleanFormatPreview taskId={taskId} revision={revision} runId={runId} appType={appType} candidateSha={visible.source_sha256} blocked={blocked||reading} onLoad={onLoad}/><CandidateFieldSelection taskId={taskId} revision={revision} runId={runId} appType={appType} candidateSha={visible.source_sha256} blocked={blocked||reading} onLoad={onLoad}/><CandidateTextMapping taskId={taskId} revision={revision} runId={runId} appType={appType} candidateSha={visible.source_sha256} blocked={blocked||reading} onLoad={onLoad}/></>}</>}
 </div>;
}
