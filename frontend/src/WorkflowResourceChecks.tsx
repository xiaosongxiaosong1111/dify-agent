import {useEffect,useRef,useState} from 'react';
import DatasetConfigurationResult,{validDatasetGuidance,type DatasetCheck} from './DatasetConfigurationResult';
type Target={id:string;base_url:string;version:string;connection_revision?:string|null};
type ModelResult={status:'invalid'|'needs_review'|'matches_known_rules';matches_known_rules:boolean;environment_id:string;connection_revision?:string|null;model_document_token:string;observed_at:string;errors:string[];unresolved:string[];rules:unknown[];note:string};
type DatasetResult=DatasetCheck&{environment_id:string;connection_revision?:string|null;selection_token:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const strings=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(x=>typeof x==='string');
const flags=(v:Record<string,unknown>)=>['task_modified','platform_verified','business_verified','target_resources_verified'].every(k=>v[k]===false);
export function modelReply(v:unknown,target:Target,token:string):v is ModelResult{
 if(!object(v)||!flags(v)||v.model_calls!==0||v.verification!=='directory_model_rules_only'||v.environment_id!==target.id||(v.connection_revision??null)!==(target.connection_revision??null)||v.model_document_token!==token||!strings(v.errors)||!strings(v.unresolved)||!Array.isArray(v.rules)||typeof v.observed_at!=='string'||typeof v.note!=='string')return false;
 const expected=v.errors.length?'invalid':v.unresolved.length?'needs_review':'matches_known_rules';return v.status===expected&&v.matches_known_rules===(expected==='matches_known_rules');
}
export function datasetReply(v:unknown,target:Target,token:string,ids:string[],source:string):v is DatasetResult{
 if(!object(v)||!flags(v)||v.verification!=='dataset_directory_metadata_only'||v.retrieval_tested!==false||v.model_calls!==0||v.environment_id!==target.id||(v.connection_revision??null)!==(target.connection_revision??null)||v.selection_token!==token||v.source!==source||!Array.isArray(v.rows)||v.rows.length!==ids.length||!Number.isInteger(v.pages_read)||Number(v.pages_read)<1||Number(v.pages_read)>3||typeof v.catalog_complete!=='boolean'||typeof v.search_complete_for_selected!=='boolean'||typeof v.status_label!=='string'||typeof v.observed_at!=='string'||typeof v.note!=='string'||!strings(v.warnings))return false;
 return v.rows.every((row,i)=>{if(!object(row)||row.id!==ids[i]||typeof row.status_label!=='string'||!object(row.metadata)||!strings(row.issues)||!strings(row.unavailable_fields)||!validDatasetGuidance(row.guidance))return false;const metadata=row.metadata;
  return ['name','indexing_technique','embedding_model','embedding_model_provider'].every(k=>metadata[k]===undefined||typeof metadata[k]==='string')&&['document_count','available_document_count'].every(k=>metadata[k]===undefined||Number.isSafeInteger(metadata[k])&&Number(metadata[k])>=0)});
}
async function hash(text:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(n=>n.toString(16).padStart(2,'0')).join('')}
async function request(path:string,body:unknown){const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(typeof value?.detail==='string'?value.detail:'目录核对未完成，输入保持。');return value}
export default function WorkflowResourceChecks({target,scope,modelNode,modelText,datasetIds,disabled,onActivity}:{target:Target;scope:string;modelNode:string;modelText:string;datasetIds:string[];disabled:boolean;onActivity:(v:boolean)=>void}){
 const [busy,setBusy]=useState(''),[source,setSource]=useState<'console'|'service'>('console'),[model,setModel]=useState<(ModelResult&{signature:string})|null>(null),[datasets,setDatasets]=useState<(DatasetResult&{signature:string})|null>(null),[modelError,setModelError]=useState(''),[datasetError,setDatasetError]=useState('');
 const alive=useRef(true),active=useRef(false),modelScope=JSON.stringify([scope,target,modelNode,modelText]),datasetScope=JSON.stringify([scope,target,datasetIds,source]),current=useRef({modelScope,datasetScope});current.current={modelScope,datasetScope};
 useEffect(()=>{alive.current=true;return()=>{alive.current=false}},[]);useEffect(()=>{setModel(null);setModelError('')},[modelScope]);useEffect(()=>{setDatasets(null);setDatasetError('')},[datasetScope]);
 const check=async(kind:'model'|'datasets')=>{
  if(disabled||active.current)return;active.current=true;setBusy(kind);onActivity(true);const expected=kind==='model'?modelScope:datasetScope;
  if(kind==='model'){setModel(null);setModelError('')}else{setDatasets(null);setDatasetError('')}
  try{
   if(kind==='model'){
    if(!modelNode||!modelText.trim())throw Error('请先在目录辅助中指定一个模型节点，并填写它的完整目标JSON。');
    const token=await hash(modelText),value=await request(`/api/environments/${encodeURIComponent(target.id)}/model-configuration-check`,{model_json:modelText,expected_connection_revision:target.connection_revision??null});
    if(!modelReply(value,target,token))throw Error('节点模型核对回执与当前节点原文或目标连接不一致，未采用结果。');
    if(alive.current&&current.current.modelScope===expected)setModel({...value,signature:expected});
   }else{
    if(!datasetIds.length||new Set(datasetIds).size!==datasetIds.length||datasetIds.some(id=>!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(id)))throw Error('请先逐一填写完整且不重复的目标知识库UUID；不会按名称猜测。');
    const token=await hash(JSON.stringify({dataset_ids:datasetIds,source,max_pages:3})),value=await request(`/api/environments/${encodeURIComponent(target.id)}/dataset-configuration-check`,{dataset_ids:datasetIds,source,max_pages:3,expected_connection_revision:target.connection_revision??null});
    if(!datasetReply(value,target,token,datasetIds,source))throw Error('知识库核对回执与当前目标ID、连接或范围不一致，未采用结果。');
    if(alive.current&&current.current.datasetScope===expected)setDatasets({...value,signature:expected});
   }
  }catch(e){if(alive.current&&(kind==='model'?current.current.modelScope:current.current.datasetScope)===expected){const message=e instanceof TypeError?'本机目录核对连接中断，原输入保持；请核对后主动重读。':e instanceof SyntaxError?'目录核对没有返回完整JSON，原输入保持。':e instanceof Error?e.message:'目录核对未完成。';if(kind==='model')setModelError(message);else setDatasetError(message)}}
  finally{active.current=false;onActivity(false);if(alive.current)setBusy('')}
 };
 return <details className="workflow-resource-checks"><summary>核对目标节点模型与指定知识库（只读）</summary><p className="hint">只核对读取时目录规则与索引计数，不调用模型、检索、读全文或创建资源，不保存或确认配置；静态文件可下载也不代表目标资源通过。重排型号、固定插件及其费用仍须另行核对。</p>
  <fieldset disabled={disabled||!!busy}><p>当前目录辅助模型节点：{modelNode||'尚未指定'}</p><button className="secondary" disabled={!modelNode||!modelText.trim()} onClick={()=>void check('model')}>核对当前节点完整目标模型（只读）</button>
  <label className="field"><span>目标知识库目录认证来源</span><select aria-label="流程知识库核对认证来源" value={source} onChange={e=>setSource(e.target.value as 'console'|'service')}><option value="console">管理连接</option><option value="service">知识库 Key</option></select></label><button className="secondary" disabled={!datasetIds.length||datasetIds.some(id=>!id.trim())} onClick={()=>void check('datasets')}>核对流程目标知识库目录与索引计数</button></fieldset>
  {busy&&<p role="status">正在核对目录，原模型、知识库与资源确认保持…</p>}{modelError&&<p className="callout amber" role="alert">{modelError}</p>}{datasetError&&<p className="callout amber" role="alert">{datasetError}</p>}
  {model&&model.signature===modelScope&&<div className="workflow-node-model-check callout amber"><b>节点 {modelNode}：{model.status==='matches_known_rules'?'读取时已知模型规则一致':model.status==='invalid'?'模型参数与目标目录规则不符':'模型规则仍待明确'}</b><p className="hint">读取于 {model.observed_at}。{model.note}</p>{model.errors.map((s,i)=><p key={'e'+i}>不符：{s}</p>)}{model.unresolved.map((s,i)=><p key={'u'+i}>待核对：{s}</p>)}<details><summary>完整模型参数规则依据</summary><pre>{JSON.stringify(model.rules,null,2)}</pre></details></div>}
  {datasets&&datasets.signature===datasetScope&&<DatasetConfigurationResult result={datasets}/>}
 </details>
}
