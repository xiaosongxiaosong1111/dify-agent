import {useEffect,useRef,useState} from 'react';
import type {RunRecord} from './AcceptancePanel';
type Value={state:'saved'|'missing'|'unavailable';text:string};
type Result={schema_version:1;task_id:string;revision:number;before_run_id:string;after_run_id:string;snapshot_token:string;
 records:Record<string,string|number|null>[];conditions_same:Record<string,boolean|null>;
 sections:{field:string;comparison:string;before:Value;after:Value}[];warnings:string[];verification:string;
 task_changed:boolean;network_requested:boolean;automatic_execution:boolean;business_verified:boolean};
const labels:Record<string,string>={input:'实际输入',expectation:'运行时预期',output:'保存的实际输出'};
const names:Record<string,string>={same:'保存值相同',changed:'保存值不同',missing:'字段未完整保存',unavailable:'未作比较'};
const conditions:Record<string,string>={revision:'修订',environment_id:'环境',app_id:'App',environment_binding:'连接快照',case_id:'样例ID'};
const statuses:Record<string,string>={success:'请求成功',failed:'请求失败',unknown:'结果未知',pending:'执行中',running:'执行中',waiting_platform:'平台等待处理',platform_finished:'平台已结束，业务未验收'};
const types:Record<string,string>={workflow:'Workflow','advanced-chat':'Chatflow',agent:'原生Agent'};
export default function RunComparisonPanel({taskId,revision,runs,blocked}:{taskId:string;revision:number;runs:RunRecord[];blocked:boolean}){
 const choices=runs.filter(r=>r.kind==='run').slice(-200).reverse();
 const [left,setLeft]=useState(''),[right,setRight]=useState(''),[result,setResult]=useState<(Result&{observedRuns:RunRecord[]})|null>(null),[error,setError]=useState(''),[working,setWorking]=useState(false);
 const epoch=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{epoch.current++;controller.current?.abort();setResult(null);setError('');setWorking(false);return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,runs,left,right,blocked]);
 useEffect(()=>{setLeft('');setRight('')},[taskId]);
 async function read(){
  if(blocked||working||!left||!right||left===right)return;
  const ticket=++epoch.current,abort=new AbortController();controller.current=abort;setWorking(true);setError('');setResult(null);
  const timer=setTimeout(()=>abort.abort(),15000);
  try{
   const query=new URLSearchParams({revision:String(revision),before_run_id:left,after_run_id:right});
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/run-comparison?${query}`,{signal:abort.signal,cache:'no-store'});
   if(ticket!==epoch.current)return;const value=await response.json();
   if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'读取运行对照失败，原记录保持。');
   if(value.schema_version!==1||value.task_id!==taskId||value.revision!==revision||value.before_run_id!==left||value.after_run_id!==right||!/^[a-f0-9]{64}$/.test(value.snapshot_token)||value.verification!=='saved_single_turn_records_only'||['task_changed','network_requested','automatic_execution','business_verified'].some(k=>value[k]!==false)||!Array.isArray(value.records)||value.records.length!==2||!value.conditions_same||!Array.isArray(value.warnings)||value.warnings.some((x:unknown)=>typeof x!=='string')||!Array.isArray(value.sections)||value.sections.length!==3||value.sections.some((s:Result['sections'][number],i:number)=>s.field!==['input','expectation','output'][i]||!names[s.comparison]||[s.before,s.after].some(v=>!v||!['saved','missing','unavailable'].includes(v.state)||typeof v.text!=='string'||v.text.length>17000)))throw Error('运行对照响应与所选记录不匹配，未显示。');
   if(value.records.some((r:Result['records'][number],i:number)=>r?.id!==[left,right][i]||!['workflow','advanced-chat','agent'].includes(String(r.app_type))||['app_id','environment_id','status'].some(k=>r[k]!==null&&typeof r[k]!=='string'))||Object.keys(conditions).some(k=>![true,false,null].includes(value.conditions_same[k])))throw Error('运行对照归属或条件字段无效，未显示。');
   if(ticket===epoch.current)setResult({...value,observedRuns:runs});
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'读取运行对照失败，未重试。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 if(!choices.length)return null;
 const visible=result&&result.observedRuns===runs&&result.task_id===taskId&&result.revision===revision&&result.before_run_id===left&&result.after_run_id===right&&!blocked?result:null;
 const select=(value:string,set:(s:string)=>void,label:string)=><label className="field"><span>{label}</span><select aria-label={label} value={value} disabled={blocked||working} onChange={e=>set(e.target.value)}><option value="">请明确选择记录</option>{choices.map(r=><option key={r.id} value={r.id}>{r.test_case?.name||r.label||'自由试跑'} · r{r.revision??'未知'} · {statuses[r.status||'']||'状态未识别'} · {r.id}</option>)}</select></label>;
 return <section className="run-comparison-panel configuration-proposal"><div className="listhead"><b>修改前后试跑对照</b><small>仅读本机记录</small></div><p className="hint">明确选择左右两条普通单轮记录，对照原输入、原预期和保存输出。不会重跑、重新评判或继承旧通过；修订／App／环境不同会提示，输出差异不等于质量提升。多轮、复用会话、文件及缺类型旧记录请分别查看。</p>
 {select(left,setLeft,'修改前或基准记录（左）')}{select(right,setRight,'修改后或待核对记录（右）')}
 {runs.filter(r=>r.kind==='run').length>200&&<p className="hint">此处仅列最近200条普通试跑，旧记录仍保留。</p>}
 {blocked&&<p className="hint">请先保存或处理未保存编辑，当前不读取对照。</p>}
 <button className="secondary" disabled={blocked||working||!left||!right||left===right} onClick={()=>void read()}>读取所选两次试跑对照</button>
 {working&&<p role="status">读取本机保存结果…</p>}{error&&<p role="alert">{error}</p>}
 {visible&&<><div className="callout" style={{display:'block'}}><b>记录条件对照</b>{visible.records.map((r,i)=><p key={i}>{i===0?'左':'右'}：r{r.revision??'未知'} · {types[String(r.app_type)]} · App {r.app_id||'缺失'} · 环境 {r.environment_id||'缺失'} · {statuses[String(r.status)]||'状态未识别'}</p>)}<p>{Object.entries(conditions).map(([key,label])=>`${label}：${visible.conditions_same[key]===true?'相同':visible.conditions_same[key]===false?'不同':'缺少依据'}`).join('；')}</p></div>
 {visible.sections.map(s=><details key={s.field} open={s.comparison!=='same'}><summary>{labels[s.field]} · {names[s.comparison]}</summary><b>左侧保存值</b><pre>{s.before.text}</pre><b>右侧保存值</b><pre>{s.after.text}</pre></details>)}{visible.warnings.map((note,i)=><p className="hint" key={i}>{note}</p>)}</>}
 </section>;
}
