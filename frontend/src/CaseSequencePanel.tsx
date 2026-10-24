import {useEffect,useRef,useState} from 'react';
import type {TestCase,RunRecord} from './AcceptancePanel';
type Preview={task_id:string;revision:number;case_ids:string[];start_count:number;token:string;requested_runs:number;started_runs:number;max_started_runs:number;app_id:string;environment_id:string;network_requested:false;task_changed:false;start_slots_reserved:0;resource_permission_granted:false;note:string};
type Receipt={id:string;kind?:string;status?:string;test_case?:{id:string};evaluation?:{status:string};case_sequence?:{token:string;start_count:number;index:number}};
export function sequenceHistory(runs:RunRecord[]){
 return runs.flatMap((first,start)=>{const p=first.case_sequence;if(first.kind!=='run'||!p||p.index!==0||p.start_count!==start||!/^[a-f0-9]{64}$/.test(p.token)||!Array.isArray(p.case_ids)||p.case_ids.length<1||p.case_ids.length>10||p.case_ids.some(x=>typeof x!=='string'||!x)||new Set(p.case_ids).size!==p.case_ids.length)return [];
  return [{key:p.token,revision:first.revision,rows:p.case_ids.map((id,i)=>{const row=runs[start+i],q=row?.case_sequence,owned=q?.token===p.token&&q.start_count===start&&q.index===i&&JSON.stringify(q.case_ids)===JSON.stringify(p.case_ids)&&row.kind==='run'&&row.test_case?.id===id;
   const state=!row?'未启动':!owned?'本批无对应记录':row.status==='success'?(row.evaluation?.status==='passed'?'规则通过':row.evaluation?.status==='failed'?'规则未通过':row.evaluation?.status==='needs_review'?'需人工判断':'评分未知'):row.status==='failed'?'请求失败':row.status==='unknown'?'结果未知':row.status==='waiting_platform'?'等待平台':row.status==='pending'?'已启动待返回':'记录状态未知';
   return {id,state,runId:owned?row.id:null};})}];
 }).slice(-5);
}
export default function CaseSequencePanel({taskId,revision,appId,environmentId,cases,runs,scope,blocked,onActivity,onStopped}:{taskId:string;revision:number;appId?:string|null;environmentId:string|null;cases:TestCase[];runs:RunRecord[];scope:string;blocked:boolean;onActivity:(label:string|null)=>void;onStopped:()=>void}){
 const [selected,setSelected]=useState<string[]>([]),[preview,setPreview]=useState<Preview|null>(null),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(''),[progress,setProgress]=useState<string[]>([]);
 const epoch=useRef(0),stop=useRef(false),active=useRef(false),activity=useRef(onActivity),finished=useRef(onStopped);activity.current=onActivity;finished.current=onStopped;
 useEffect(()=>{epoch.current++;stop.current=true;setBusy(false);setPreview(null);setAck(false);setError('');setSelected([]);setProgress([]);return()=>{epoch.current++;stop.current=true;if(active.current){active.current=false;activity.current(null)}}},[taskId,revision,scope,blocked]);
 const ordered=cases.filter(c=>selected.includes(c.id)).map(c=>c.id);
 const read=async()=>{if(blocked||busy)return;const ticket=++epoch.current;setBusy(true);setPreview(null);setAck(false);setError('');setProgress([]);try{
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/case-sequence-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,case_ids:ordered})});const p=await r.json() as Preview&{detail?:string};if(ticket!==epoch.current)return;
   if(!r.ok)throw Error(typeof p.detail==='string'?p.detail:'无法准备本批样例。');
   if(p.task_id!==taskId||p.revision!==revision||p.app_id!==appId||p.environment_id!==environmentId||JSON.stringify(p.case_ids)!==JSON.stringify(ordered)||p.requested_runs!==ordered.length||!Number.isInteger(p.start_count)||p.start_count<0||!Number.isInteger(p.started_runs)||p.started_runs<0||!Number.isInteger(p.max_started_runs)||p.max_started_runs<p.started_runs+p.requested_runs||!/^[a-f0-9]{64}$/.test(p.token)||p.network_requested!==false||p.task_changed!==false||p.start_slots_reserved!==0||p.resource_permission_granted!==false)throw Error('批次预览来源或只读标志不匹配，请重新核对。');setPreview(p);
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'批次预览失败。')}finally{if(ticket===epoch.current)setBusy(false)}};
 const start=async()=>{if(!preview||!ack||busy||blocked||active.current)return;const p=preview,ticket=++epoch.current;stop.current=false;active.current=true;setBusy(true);setError('');setProgress([]);setPreview(null);setAck(false);activity.current('顺序样例试跑');
  try{for(let i=0;i<p.case_ids.length;i++){
   if(stop.current||ticket!==epoch.current)break;
   setProgress(xs=>[...xs,`正在启动第${i+1}/${p.case_ids.length}例…`]);
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/run`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,case_id:p.case_ids[i],sequence:{case_ids:p.case_ids,start_count:p.start_count,index:i,token:p.token}})});
   const value=await r.json() as {id:string;revision:number;runs:Receipt[];detail?:string};if(ticket!==epoch.current)break;
   if(!r.ok)throw Error(typeof value.detail==='string'?value.detail:'本例未明确返回，已停止后续；请核对原记录，不重复派发。');
   const row=value.runs?.at(-1);if(value.id!==taskId||value.revision!==revision||value.runs?.length!==p.start_count+i+1||row?.kind!=='run'||row.test_case?.id!==p.case_ids[i]||row.case_sequence?.token!==p.token||row.case_sequence.start_count!==p.start_count||row.case_sequence.index!==i)throw Error('返回记录与本批顺序不匹配，停止后续并核对原记录。');
   if(row.status!=='success'||row.evaluation?.status!=='passed')throw Error(`第${i+1}例未明确通过（${row.status||'未知'}/${row.evaluation?.status||'未评分'}），已停止后续。`);
   setProgress(xs=>[...xs,`第${i+1}例已按原样例规则通过。`]);
  }if(ticket===epoch.current)setProgress(xs=>[...xs,stop.current?'已停止后续；已派发请求仍保留原记录。':'本批所选样例已依次返回；业务验收范围仍以原批准和规则为准。']);
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'请求未明确返回，已停止后续；请核对原记录，不自动重试。')}
  finally{if(ticket===epoch.current)setBusy(false);if(active.current){active.current=false;activity.current(null)}if(ticket===epoch.current)finished.current()}
 };
 return <details className="case-sequence-panel configuration-proposal"><summary>选择样例并依次试跑</summary><p className="hint">仅支持已保存的普通单轮标量样例，按下列保存顺序运行，最多10例。首个失败、未知或需人工判断即停止；刷新或离开不续跑，也不取消已派发请求。此处不扩大原批准的运行次数或费用。</p>
  {cases.map((c,i)=><label className="field" key={c.id}><span><input type="checkbox" aria-label={`顺序试跑选择 ${c.name}`} checked={selected.includes(c.id)} disabled={busy||blocked} onChange={e=>{epoch.current++;setSelected(xs=>e.target.checked?[...xs,c.id]:xs.filter(x=>x!==c.id));setPreview(null);setAck(false);setError('');setProgress([])}}/>{i+1}. {c.name}{c.followups?.length?'（多轮，须用专用入口）':''}</span></label>)}
  <button className="secondary" disabled={busy||blocked||ordered.length<1||ordered.length>10} onClick={()=>void read()}>核对所选顺序与本批上限</button>
  {preview&&<><p role="status">将向当前App {preview.app_id} 依次运行{preview.requested_runs}例；累计已启动{preview.started_runs}次，有限次数上限{preview.max_started_runs}次。</p><p className="hint">{preview.note}</p><label className="field"><span><input type="checkbox" checked={ack} disabled={busy||blocked} onChange={e=>setAck(e.target.checked)}/>我已核对本批外部调用范围与费用批准，并确认按所选顺序启动</span></label><button className="primary" disabled={busy||blocked||!ack} onClick={()=>void start()}>开始所选{preview.requested_runs}例顺序试跑</button></>}
  {active.current&&<button className="secondary" onClick={()=>{stop.current=true;setProgress(xs=>[...xs,'已请求停止后续，等待已派发例返回。'])}}>停止后续样例</button>}
  {progress.length>0&&<div role="status">{progress.map((x,i)=><p key={i}>{x}</p>)}</div>}{error&&<p role="alert" className="callout amber">{error}</p>}
  {sequenceHistory(runs).map(group=><section className="sequence-history" key={group.key}><b>已启动批次 · 原修订{group.revision??'未知'}</b><p className="hint">最近5批的已保存记录，未启动项不当失败或通过；不自动续跑，也不继承为当前修订验收。输入/输出见下方原运行记录。</p><table><thead><tr><th>顺序／样例ID</th><th>本批记录</th></tr></thead><tbody>{group.rows.map((row,i)=><tr key={row.id}><td>{i+1}. {row.id}</td><td>{row.state}{row.runId&&<small> · {row.runId}</small>}</td></tr>)}</tbody></table></section>)}
 </details>;
}
