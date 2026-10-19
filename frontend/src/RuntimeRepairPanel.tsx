import {useEffect,useRef,useState} from 'react';
import type {Diagnostic} from './RunDiagnosticPanel';
import RepairFollowupPanel,{type ReplayRecipe} from './RepairFollowupPanel';
import ModelRepairPanel from './ModelRepairPanel';
type Repair={id:string;run_id:string;revision:number;result_revision?:number;diagnostic_id:string;status:string;verification:string;note:string;kind?:string;summary?:string;changes:{node_id:string;module?:string;inserted_line?:number;reason?:string;before:string;after:string}[];validation:{warnings:string[]}};
export default function RuntimeRepairPanel({taskId,runId,revision,report,eligible,blocked,onActivity,onUpdated,onPrepareRun}:{taskId:string;runId:string;revision:number;report?:Diagnostic;eligible:boolean;blocked:boolean;onActivity:(label:string)=>void;onUpdated:(task:unknown)=>void;onPrepareRun?:(recipe:ReplayRecipe)=>void}){
 const [record,setRecord]=useState<Repair|null>(null),[active,setActive]=useState(false),[error,setError]=useState('');
 const [historyRefresh,setHistoryRefresh]=useState(0),[businessReview,setBusinessReview]=useState(false);
 useEffect(()=>setBusinessReview(false),[record?.id]);
 const generation=useRef(0);
 useEffect(()=>{let live=true;const current=++generation.current;setRecord(null);setError('');void fetch(`/api/tasks/${taskId}/runtime-repairs`).then(async response=>{const value=await response.json();if(!response.ok)throw Error('修复历史读取失败，请刷新运行页。');if(live&&current===generation.current)setRecord((value.records as Repair[]).find(r=>r.run_id===runId)||null)}).catch(e=>{if(live&&current===generation.current)setError(e instanceof Error?e.message:'修复历史读取失败')});return()=>{live=false}},[taskId,runId,revision,report?.id,historyRefresh]);
 const request=async(path:string,body:unknown)=>{const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:`修复操作失败（HTTP ${response.status}）`);return value};
 const preview=async()=>{if(!report)return;++generation.current;setActive(true);setError('');onActivity('生成本机小修复候选');try{setRecord(await request(`/api/tasks/${taskId}/runs/${runId}/repair-preview`,{revision,diagnostic_id:report.id}))}catch(e){setError(e instanceof Error?e.message:'修复候选生成失败')}finally{setActive(false);onActivity('')}};
 const apply=async()=>{if(!record)return;++generation.current;setActive(true);setError('');onActivity('采纳修复为新修订');try{const model=record.kind==='model_code_proposal';const value=await request(`/api/tasks/${taskId}/runtime-repairs/${record.id}/${model?'model-apply':'apply'}`,model?{revision,acknowledge_business_review:businessReview}:{revision});setRecord(value.repair);onUpdated(value.task)}catch(e){setError(e instanceof Error?e.message:'修复候选采纳失败')}finally{setActive(false);onActivity('')}};
 const current=!!record&&record.revision===revision&&record.diagnostic_id===report?.id;
 return <section className="runtime-repair-panel"><b>本机小修复</b><p className="hint">支持 Python 代码明确报 NameError，且 math／re 在代码中未绑定、仅通过属性使用的缺导入情况。先查看候选，不会自动改方案或重跑；其他错误说明条件并转人工处理。</p>
 <button className="secondary" disabled={blocked||active||!eligible} onClick={()=>void preview()}>生成修复候选并查看差异</button>
 {!eligible&&<p className="hint">需要明确失败的运行及当前来源的完整节点轨迹。旧记录、结果未知或来源不一致不能启动修复。</p>}
 {active&&<p role="status">正在处理本机修复，无模型或 Dify 请求。</p>}{error&&<div className="alert error" role="alert">{error}</div>}
 {record&&<><small>源修订 v{record.revision}{record.result_revision?` → 新修订 v${record.result_revision}`:''} · {record.status==='applied'?'已采纳，仍待重新验证':'未采纳候选'} · 仅静态检查</small>{!current&&record.status!=='applied'&&<p className="hint">候选来自旧修订或旧诊断，仅供查看；不能采纳到当前方案。</p>}
 {record.summary&&<p>{record.summary}</p>}{record.changes.map((change,index)=><details key={index}><summary>节点 {change.node_id}：{record.kind==='model_code_proposal'?'模型代码候选（需核对行为）':`第 ${change.inserted_line} 行补 import ${change.module}`}</summary><p className="hint">{record.kind==='model_code_proposal'?'模型可能改变代码业务行为；输入输出声明、节点资源与连接保持，须核对实际差异。':'原文与候选仅在本机显示，业务表达式、节点资源和输入输出不变。'}</p>{change.reason&&<p>{change.reason}</p>}<b>修复前</b><pre>{change.before}</pre><b>修复候选</b><pre>{change.after}</pre></details>)}
 {record.validation.warnings.map((warning,index)=><p className="hint" key={index}>静态检查提示：{warning}</p>)}<p className="hint">{record.note}</p>
 {record.kind==='model_code_proposal'&&record.status==='ready'&&<label className="repair-ack"><input type="checkbox" checked={businessReview} disabled={blocked||active} onChange={e=>setBusinessReview(e.target.checked)}/><span>我已核对代码差异及业务行为，同意采纳并重新确认需求和配置；不把静态通过当作运行成功。</span></label>}
 <button className="primary" disabled={blocked||active||!eligible||!current||record.status!=='ready'||record.kind==='model_code_proposal'&&!businessReview} onClick={()=>void apply()}>采纳为新修订，重新确认配置</button><p className="hint">采纳会保存旧版本、失效配置确认和成果绑定，保留原失败记录；模型候选还需重新确认需求。随后构建、核对资源方案并试跑，不覆盖现有 Dify 应用。</p>{record.status==='applied'&&<RepairFollowupPanel taskId={taskId} repairId={record.id} revision={revision} blocked={blocked||active} onActivity={onActivity} onPrepareRun={onPrepareRun}/>}</>}
 <ModelRepairPanel taskId={taskId} runId={runId} revision={revision} diagnosticId={report?.id} eligible={eligible} blocked={blocked||active} onActivity={onActivity} onSaved={value=>{setHistoryRefresh(x=>x+1);onUpdated(value)}}/>
 </section>;
}
