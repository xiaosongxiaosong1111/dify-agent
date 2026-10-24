import {useEffect,useRef,useState} from 'react';
import type {RetainedDraft} from './RetainedPlanCandidate';

type Preview={task_id:string;planning_run_id:string;revision:number;app_type:string;candidate_sha256:string;review_token:string;change:{path:(string|number)[];before:string;before_type:string;after:boolean;after_type:string};plan_text:string;byte_count:number;source_sha256:string;verification:string;static_validated:boolean;warnings:string[];formal_plan_changed:boolean;network_requested:boolean;platform_checked:boolean;business_verified:boolean;note:string};
type Props={taskId:string;revision:number;runId:string;appType:string;candidateSha:string;blocked:boolean;onLoad:(draft:RetainedDraft)=>boolean};
const sha=(text:string)=>/^[a-f0-9]{64}$/.test(text);
export default function BooleanFormatPreview(props:Props){
 const {taskId,revision,runId,appType,candidateSha,blocked,onLoad}=props;
 const [value,setValue]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const epoch=useRef(0),current=useRef({blocked,onLoad});current.current={blocked,onLoad};
 useEffect(()=>{epoch.current++;setValue(null);setBusy(false);setError('');setNotice('');return()=>{epoch.current++}},[taskId,revision,runId,appType,candidateSha,blocked]);
 async function request(token?:string){
  const path=`/api/tasks/${encodeURIComponent(taskId)}/planning/${encodeURIComponent(runId)}/boolean-format-preview`;
  const response=await fetch(token?path+'/compose':path+`?revision=${revision}`,token?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,review_token:token})}:{});
  const v=await response.json() as Preview&{detail?:string};
  if(!response.ok)throw Error(typeof v.detail==='string'?v.detail:'未提供格式预览；原候选和草稿保持。');
  const c=v?.change,p=c?.path;
  if(!v||v.task_id!==taskId||v.planning_run_id!==runId||v.revision!==revision||v.app_type!==appType||v.candidate_sha256!==candidateSha||!sha(v.review_token)||v.verification!=='manual_boolean_format_preview'||v.static_validated!==true||v.formal_plan_changed!==false||v.network_requested!==false||v.platform_checked!==false||v.business_verified!==false||!Array.isArray(v.warnings)||v.warnings.some(w=>typeof w!=='string')||typeof v.note!=='string'||typeof v.plan_text!=='string'||v.plan_text.length>2000000||!Number.isSafeInteger(v.byte_count)||!sha(v.source_sha256)||!c||c.before_type!=='string'||!['true','false'].includes(c.before)||c.after_type!=='boolean'||c.after!==(c.before==='true')||!Array.isArray(p)||p.length!==8||p[0]!=='nodes'||p[2]!=='config'||p[3]!=='cases'||p[5]!=='conditions'||p[7]!=='value'||[p[1],p[4],p[6]].some(n=>!Number.isSafeInteger(n)||Number(n)<0))throw Error('格式预览的归属、修正范围或未验证标志不匹配，未载入。');
  const bytes=new TextEncoder().encode(v.plan_text),hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  if(bytes.length!==v.byte_count||bytes.length>2000000||hash!==v.source_sha256)throw Error('格式预览原文摘要不匹配，未载入。');
  const parsed=JSON.parse(v.plan_text);if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw Error('格式预览不是完整对象，未载入。');
  return v;
 }
 async function read(){if(current.current.blocked||busy)return;const ticket=epoch.current;setBusy(true);setValue(null);setError('');setNotice('');try{const v=await request();if(ticket===epoch.current&&!current.current.blocked)setValue(v)}catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'格式预览未完成。')}finally{if(ticket===epoch.current)setBusy(false)}}
 async function load(){if(!value||current.current.blocked||busy)return;const ticket=epoch.current;setBusy(true);setError('');setNotice('');try{const v=await request(value.review_token);if(ticket!==epoch.current||current.current.blocked)return;if(v.review_token!==value.review_token||v.source_sha256!==value.source_sha256||v.plan_text!==value.plan_text||JSON.stringify(v.change)!==JSON.stringify(value.change))throw Error('格式预览已变化，请重新读取并核对；未载入。');if(current.current.onLoad({taskId,revision,text:v.plan_text}))setNotice('人工格式修正副本已放入未保存草稿；原候选与正式方案保持，请校验、保存并重新确认。')}catch(e){if(ticket===epoch.current){setError(e instanceof Error?e.message:'格式修正未载入。');setValue(null)}}finally{if(ticket===epoch.current)setBusy(false)}}
 if(!['workflow','advanced-chat'].includes(appType))return null;
 return <div className="boolean-format-preview"><p className="hint">仅支持一处明确的布尔字符串格式错误。先看精确差异，再主动载入人工修正副本；不改原候选，不自动保存或运行。</p><button className="secondary" disabled={blocked||busy} onClick={()=>void read()}>预览单处布尔格式修正（仅本机）</button>{busy&&<p role="status">正在本机核对完整图…</p>}{error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}{value&&<><p>{value.note}</p><p>/{value.change.path.join('/')}：JSON字符串 <code>{JSON.stringify(value.change.before)}</code> → JSON布尔 <code>{String(value.change.after)}</code>；其余图字段保持。</p><p>完整图静态校验通过；平台与业务尚未验证。</p>{value.warnings.map((w,i)=><p className="hint" key={i}>{w}</p>)}<details><summary>查看人工格式修正副本</summary><pre>{value.plan_text}</pre></details><button className="secondary" disabled={blocked||busy} onClick={()=>void load()}>将此格式修正放入未保存草稿</button></>}</div>;
}
