import {useEffect,useRef,useState} from 'react';
import type {RunRecord} from './AcceptancePanel';
export type InputCopyDraft={taskId:string;revision:number;currentInput:string;selectionScope:string;text:string};
type Candidate={schema_version:1;task_id:string;revision:number;run_id:string;source_revision:number;source_status:string;input_text:string;input_sha256:string;numeric_review_required:boolean;warnings:string[];verification:string;task_changed:boolean;network_requested:boolean;automatic_execution:boolean;business_verified:boolean;case_copied:boolean;conversation_copied:boolean;current_schema_checked:boolean};
const digest=async(s:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))),x=>x.toString(16).padStart(2,'0')).join('');
export default function SavedRunInputCopy({taskId,revision,run,input,selectionScope,blocked,onAdopt}:{taskId:string;revision:number;run:RunRecord;input:string;selectionScope:string;blocked:boolean;onAdopt:(draft:InputCopyDraft)=>boolean}){
 const [candidate,setCandidate]=useState<(Candidate&{observedRun:RunRecord;input:string;scope:string})|null>(null),[error,setError]=useState(''),[working,setWorking]=useState(false);
 const epoch=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{epoch.current++;controller.current?.abort();setCandidate(null);setError('');setWorking(false);return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,run,input,selectionScope,blocked]);
 async function read(){
  if(blocked||working)return;const ticket=++epoch.current,abort=new AbortController();controller.current=abort;setWorking(true);setError('');setCandidate(null);const timer=setTimeout(()=>abort.abort(),15000);
  try{
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/runs/${encodeURIComponent(run.id)}/input-copy-preview?revision=${revision}`,{signal:abort.signal,cache:'no-store'});if(ticket!==epoch.current)return;const v=await r.json();
   if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:'无法读取原输入，当前草稿保持。');
   if(v.schema_version!==1||v.task_id!==taskId||v.revision!==revision||v.run_id!==run.id||!['success','failed'].includes(v.source_status)||v.verification!=='saved_scalar_input_draft_only'||typeof v.input_text!=='string'||new TextEncoder().encode(v.input_text).length>128000||await digest(v.input_text)!==v.input_sha256||typeof v.numeric_review_required!=='boolean'||!Array.isArray(v.warnings)||v.warnings.some((s:unknown)=>typeof s!=='string')||['task_changed','network_requested','automatic_execution','business_verified','case_copied','conversation_copied','current_schema_checked'].some(k=>v[k]!==false))throw Error('输入预览与当前来源或验证等级不符，未采用。');
   if(ticket===epoch.current)setCandidate({...v,observedRun:run,input,scope:selectionScope});
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'读取失败，未重试。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 if(run.kind!=='run')return null;
 const visible=candidate&&candidate.observedRun===run&&candidate.task_id===taskId&&candidate.revision===revision&&candidate.input===input&&candidate.scope===selectionScope&&!blocked?candidate:null;
 return <section className="saved-run-input-copy configuration-proposal"><b>沿用这次输入准备新草稿</b><p className="hint">只复制已确认结束的单轮标量输入；不带旧样例选择、预期、通过结论或会话。采用会替换当前自由试跑JSON并切为新会话，不会运行。</p><button className="secondary" disabled={blocked||working} onClick={()=>void read()}>预览此记录的输入（不运行）</button>{working&&<p role="status">读取本机原输入…</p>}{error&&<p role="alert">{error}</p>}{visible&&<><p>来源修订r{visible.source_revision} · {visible.source_status==='success'?'请求成功':'请求失败'}；未检查当前入口。</p><pre>{visible.input_text}</pre>{visible.warnings.map((s,i)=><p className="hint" key={i}>{s}</p>)}<button className="secondary" disabled={blocked} onClick={()=>{if(!onAdopt({taskId,revision,currentInput:input,selectionScope,text:visible.input_text}))setError('当前任务、输入或选择已变化，未替换。')}}>载入为自由试跑草稿（不运行）</button></>}</section>;
}
