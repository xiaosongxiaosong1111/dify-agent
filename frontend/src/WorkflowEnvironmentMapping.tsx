import {useCallback,useEffect,useRef,useState} from 'react';
import MappingResourceCatalog from './MappingResourceCatalog';
import WorkflowMappingProgress,{type MappingInputs} from './WorkflowMappingProgress';
import WorkflowResourceChecks from './WorkflowResourceChecks';
export type WorkflowMappingSource={available:false;reason:string}|{available:true;node_models_json:Record<string,string>;dataset_ids:string[];node_rerankers:Record<string,{provider:string;model:string}>;dependencies:string[];retained_settings:boolean;note:string};
type Binding={revision:number;reference_id:string;merge_token:string;document_token:string;choices:Record<string,string>;parallel_reviews:Record<string,unknown>;loop_reviews:Record<string,unknown>};
type Environment={id:string;name:string;base_url:string;version:string;connection_revision?:string|null};
type Parallel={id:string;title:string;root_token:string;parallel_nums:number};
type Loop={id:string;title:string;root_token:string;loop_count:number;variables:string[]};
type Review={reason:string;ack:boolean;variables:string[];limit:string};
type Result={revision:number;reference_id:string;source_document_token:string;target_environment:Environment;document_token:string;preview_token:string;content:string;changes:unknown[];retained_conditions:unknown[];target_parallel_candidates:Parallel[];target_loop_candidates:Loop[];can_download:boolean;can_apply:boolean;validation:{valid:boolean;errors:string[];warnings:string[]};verification:string;task_modified:boolean;platform_verified:boolean;business_verified:boolean;target_resources_verified:boolean;warnings:string[];note:string};
type Props={taskId:string;sourceEnvironmentId?:string|null;binding:Binding;source:WorkflowMappingSource;environments:Environment[];disabled:boolean;onDirty:(v:boolean)=>void;onActivity:(v:boolean)=>void};

export default function WorkflowEnvironmentMapping({taskId,sourceEnvironmentId,binding,source,environments,disabled,onDirty,onActivity}:Props){
 const [target,setTarget]=useState(''),[models,setModels]=useState<Record<string,string>>({}),[datasets,setDatasets]=useState<Record<string,string>>({});
 const [rerankers,setRerankers]=useState<Record<string,{provider:string;model:string}>>({}),[dependencies,setDependencies]=useState<Record<string,string>>({}),[additional,setAdditional]=useState('');
 const [ack,setAck]=useState(false),[retainedAck,setRetainedAck]=useState(false),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[discard,setDiscard]=useState(false);
 const [result,setResult]=useState<Result|null>(null),[resultSignature,setResultSignature]=useState(''),[error,setError]=useState(''),[reviews,setReviews]=useState<Record<string,Review>>({});
 const [catalogNode,setCatalogNode]=useState(''),[catalogDirty,setCatalogDirty]=useState(false);
 const [progressBusy,setProgressBusy]=useState(false),[progressPending,setProgressPending]=useState(false),[lastPayload,setLastPayload]=useState<MappingInputs|null>(null);
 const [checksBusy,setChecksBusy]=useState(false);
 const [consolidationAck,setConsolidationAck]=useState(false);
 const reportCatalog=useCallback((value:boolean)=>setCatalogDirty(value),[]);
 const currentContext=JSON.stringify({taskId,sourceEnvironmentId,binding,source}),[origin,setOrigin]=useState(currentContext),live=useRef(true),context=useRef(currentContext);
 context.current=currentContext;const stale=origin!==currentContext,locked=busy||disabled||stale||catalogDirty||progressBusy||progressPending||checksBusy;
 const selected=environments.find(e=>e.id===target),scope=JSON.stringify(selected),previousScope=useRef(scope);
 const liveScope=useRef(scope);liveScope.current=scope;
 const modelText=(id:string)=>Object.hasOwn(models,id)?models[id]:'';
 const reranker=(id:string)=>Object.hasOwn(rerankers,id)?rerankers[id]:{provider:'',model:''};
 const dependencyText=(id:string)=>Object.hasOwn(dependencies,id)?dependencies[id]:'';
 const groupedDependencies=new Map<string,string[]>();if(source.available)for(const id of source.dependencies){const value=dependencyText(id);if(/^[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+:[^\s:]+$/.test(value))groupedDependencies.set(value,[...(groupedDependencies.get(value)||[]),id])}
 const repeatedDependencies=[...groupedDependencies].filter(([,ids])=>ids.length>1);
 const stateSignature=JSON.stringify({target,models,datasets,rerankers,dependencies,additional,ack,retainedAck,consolidationAck,reviews,scope});
 const liveSignature=useRef(stateSignature);liveSignature.current=stateSignature;
 useEffect(()=>{live.current=true;return()=>{live.current=false}},[]);
 useEffect(()=>{onDirty(dirty||catalogDirty||progressPending)},[dirty,catalogDirty,progressPending,onDirty]);
 useEffect(()=>{if(previousScope.current!==scope){setAck(false);setRetainedAck(false);setConsolidationAck(false);setResult(null);setReviews({});previousScope.current=scope}},[scope]);
 const edit=()=>{setDirty(true);setAck(false);setRetainedAck(false);setConsolidationAck(false);setResult(null);setReviews({});setError('');setDiscard(false)};
 const reset=()=>{if(!discard||busy||catalogDirty||progressBusy||progressPending||checksBusy)return;setTarget('');setCatalogNode('');setConsolidationAck(false);setModels({});setDatasets({});setRerankers({});setDependencies({});setAdditional('');setAck(false);setRetainedAck(false);setResult(null);setLastPayload(null);setReviews({});setError('');setDirty(false);setDiscard(false);setOrigin(currentContext)};
 const review=(id:string,patch:Partial<Review>)=>{setDirty(true);setReviews(v=>({...v,[id]:{...(v[id]??{reason:'',ack:false,variables:[],limit:''}),...patch}}))};
 const prepare=async(withTargetReview=false)=>{
  if(locked||!source.available||!selected||!ack||source.retained_settings&&!retainedAck)return;
  setBusy(true);setError('');setResultSignature('');onActivity(true);const expectedContext=currentContext,expectedScope=scope,signature=stateSignature;
  try{
   const targetParallel:Record<string,unknown>={},targetLoops:Record<string,unknown>={};
   if(withTargetReview&&result){
    for(const row of result.target_parallel_candidates){const r=reviews['p:'+row.id];if(!r?.ack||!r.reason.trim())throw Error('请逐项填写目标并行独立性说明并确认。');targetParallel[row.id]={root_token:row.root_token,acknowledge_independence:true,reason:r.reason}}
    for(const row of result.target_loop_candidates){const r=reviews['l:'+row.id];if(!r?.ack||!r.reason.trim()||!r.variables.length||!/^([2-9]|10)$/.test(r.limit))throw Error('请明确目标循环进度字段、2—10次无进展上限、说明并确认。');targetLoops[row.id]={root_token:row.root_token,progress_variables:r.variables,no_progress_limit:Number(r.limit),progress_reason:r.reason,acknowledge_behavior:true}}
   }
   const payload={...binding,target_environment_id:target,expected_target_connection_revision:selected.connection_revision??null,
    node_models_json:Object.fromEntries(Object.keys(source.node_models_json).map(id=>[id,modelText(id)])),dataset_mapping:Object.fromEntries(source.dataset_ids.map(id=>[id,datasets[id]||''])),
    node_rerankers:Object.fromEntries(Object.keys(source.node_rerankers).map(id=>[id,reranker(id)])),dependency_mapping:Object.fromEntries(source.dependencies.map(id=>[id,dependencyText(id)])),
    additional_dependencies:additional.split('\n').map(s=>s.trim()).filter(Boolean),acknowledge_unverified_target:true,acknowledge_retained_external_settings:retainedAck,acknowledge_dependency_consolidation:consolidationAck,
    ...(withTargetReview&&result?{target_document_token:result.document_token,target_parallel_reviews:targetParallel,target_loop_reviews:targetLoops}:{})};
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/workflow-environment-mapping/preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   const value=await response.json() as Result&{detail?:unknown};if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'映射未完成，原输入保持。');
   if(value.revision!==binding.revision||value.reference_id!==binding.reference_id||value.source_document_token!==binding.document_token||value.target_environment?.id!==selected.id||value.target_environment.base_url!==selected.base_url||value.target_environment.version!==selected.version||value.verification!=='static_workflow_mapping_preview'||value.task_modified!==false||value.platform_verified!==false||value.business_verified!==false||value.target_resources_verified!==false||value.can_apply!==false||typeof value.validation?.valid!=='boolean'||value.can_download!==value.validation.valid||!Array.isArray(value.target_parallel_candidates)||!Array.isArray(value.target_loop_candidates)||!Array.isArray(value.changes)||typeof value.content!=='string'||!/^[0-9a-f]{64}$/.test(value.document_token))throw Error('目标映射回执身份或验证范围不一致，未采用结果；原输入保持。');
   if(live.current&&context.current===expectedContext&&expectedScope===liveScope.current){setResult(value);setLastPayload(payload);setResultSignature(signature)}
  }catch(e){if(live.current)setError(e instanceof Error?e.message:'连接中断，原输入保持；请核对后主动继续。')}
  finally{onActivity(false);if(live.current)setBusy(false)}
 };
 const download=()=>{if(!result?.can_download||resultSignature!==stateSignature||locked)return;const url=URL.createObjectURL(new Blob([result.content],{type:'application/yaml;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='sierra-workflow-target-unverified.yml';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
 return <section className="workflow-environment-mapping"><h3>Workflow／Chatflow 逐节点目标映射</h3>
  <p className="hint">只生成待验证文件，不更换本机任务环境、不导入运行。完整候选输入可另存本机；未保存文字可跨工作台页面保留，刷新前仍须保存或另存。</p>
  {stale&&<div className="callout amber">来源预览已变化，保留原输入只供核对；请另存需要的文字后明确清除，再按新来源填写。</div>}
  {!source.available?<p className="callout amber">{source.reason}</p>:<>
   <p className="hint">{source.note}</p><fieldset disabled={locked}>
   <label className="field"><span>独立目标环境</span><select aria-label="流程映射目标环境" value={target} onChange={e=>{edit();setTarget(e.target.value)}}><option value="">请选择目标</option>{environments.filter(e=>e.id!==sourceEnvironmentId).map(e=><option key={e.id} value={e.id}>{e.name} · {e.version}</option>)}</select></label></fieldset>
   {selected&&<div className="workflow-mapping-catalog"><label className="field"><span>接收模型参数草稿的节点（只填这一项）</span><select aria-label="流程目录接收模型节点" value={catalogNode} disabled={locked} onChange={e=>setCatalogNode(e.target.value)}><option value="">请先指定一个节点</option>{Object.keys(source.node_models_json).map(id=><option key={id} value={id}>{id}</option>)}</select></label><p className="hint">目录不证明可运行。先明确一个接收节点，再选型号、填参数和确认覆盖；知识库仍须逐一指定源ID，重排与插件标识另外核对。</p>
   <MappingResourceCatalog key={target} target={selected} disabled={busy||disabled||stale||progressBusy||progressPending||checksBusy} sourceIds={source.dataset_ids} modelDraftDisabled={!catalogNode||!Object.hasOwn(source.node_models_json,catalogNode)} modelDraftContext={JSON.stringify([taskId,binding.document_token,catalogNode])} onDraftDirty={reportCatalog} onModelDraft={text=>{if(busy||disabled||stale||!catalogNode||!Object.hasOwn(source.node_models_json,catalogNode)){setError('接收节点或来源上下文已变化，候选保留；未覆盖任何模型。');return false}edit();setModels(v=>({...v,[catalogNode]:text}));return true}} onDataset={(id,value)=>{if(busy||disabled||stale||!source.dataset_ids.includes(id))return;edit();setDatasets(v=>({...v,[id]:value}))}}/>
   </div>}
   <fieldset disabled={locked}>
   {Object.entries(source.node_models_json).map(([id,template])=><div className="merge-conflict" key={id}><b>模型节点 {id}</b><button className="secondary" disabled={!!modelText(id)} onClick={()=>{edit();setModels(v=>({...v,[id]:template}))}}>复制来源模型 {id} 作为待编辑模板</button><label className="field"><span>完整目标模型JSON · {id}</span><textarea aria-label={'流程目标模型 '+id} maxLength={30000} value={modelText(id)} onChange={e=>{edit();setModels(v=>({...v,[id]:e.target.value}))}}/></label></div>)}
   {source.dataset_ids.map(id=><label className="field" key={id}><span>来源库 {id} 对应的目标UUID</span><input aria-label={'流程目标知识库 '+id} value={datasets[id]||''} onChange={e=>{edit();setDatasets(v=>({...v,[id]:e.target.value}))}}/></label>)}
   {Object.entries(source.node_rerankers).map(([id,original])=><div className="merge-conflict" key={id}><b>重排节点 {id}（来源 {original.provider} / {original.model}）</b>{(['provider','model'] as const).map(key=><label className="field" key={key}><span>目标重排{key==='provider'?'供应商':'型号'}</span><input aria-label={`流程目标重排 ${id} ${key}`} maxLength={256} value={reranker(id)[key]} onChange={e=>{edit();setRerankers(v=>({...v,[id]:{provider:'',model:'',...(Object.hasOwn(v,id)?v[id]:{}),[key]:e.target.value}}))}}/></label>)}</div>)}
   {source.dependencies.map(id=><label className="field" key={id}><span>源固定插件 {id} 的完整目标标识</span><input aria-label={'流程目标插件 '+id} maxLength={256} value={dependencyText(id)} onChange={e=>{edit();setDependencies(v=>({...v,[id]:e.target.value}))}}/></label>)}
   <label className="field"><span>新增目标市场插件完整标识（每行一个，不猜测版本）</span><textarea aria-label="流程新增目标插件" maxLength={30000} value={additional} onChange={e=>{edit();setAdditional(e.target.value)}}/></label>
   {!!repeatedDependencies.length&&<div className="merge-conflict dependency-consolidation"><b>多个源插件对应同一完整目标标识</b>{repeatedDependencies.map(([value,ids])=><div key={value}><p>目标：{value}</p><ul>{ids.map(id=><li key={id}>来源：{id}</li>)}</ul></div>)}<p className="hint">可明确合并重复的目标声明，或调整对应关系。仅合并清单，不证明原插件功能等价替代；目标模型、兼容性、费用与人工迁移仍须核对。不同版本不能靠本项合并。</p><label className="case-required"><input type="checkbox" aria-label="确认合并相同目标插件依赖" checked={consolidationAck} onChange={e=>{edit();setConsolidationAck(e.target.checked)}}/>已核对上方全部对应，明确接受合并为各一个完整目标依赖；旧确认不沿用</label></div>}
   <label className="case-required"><input type="checkbox" checked={ack} aria-label="确认流程目标资源仍待验证" onChange={e=>{setDirty(true);setAck(e.target.checked);setResult(null);setReviews({})}}/>目标模型、资料等价、插件、费用与业务仍须验证；本次不是资源批准</label>
   {source.retained_settings&&<label className="case-required"><input type="checkbox" checked={retainedAck} aria-label="确认保留原外部设置待目标核对" onChange={e=>{setDirty(true);setRetainedAck(e.target.checked);setResult(null);setReviews({})}}/>已核对来源资源清单，接受保留代码、HTTP、变量及触发／人审的原设置；目标需另核对，不复制凭据</label>}
   <button className="secondary" disabled={!target||!ack||source.retained_settings&&!retainedAck} onClick={()=>void prepare()}>准备逐节点目标映射预览</button>
   </fieldset>
  </>}
  {selected&&source.available&&(Object.keys(source.node_models_json).length>0||source.dataset_ids.length>0)&&<WorkflowResourceChecks target={selected} scope={currentContext} modelNode={catalogNode} modelText={modelText(catalogNode)} datasetIds={source.dataset_ids.map(id=>datasets[id]||'')} disabled={busy||disabled||stale||catalogDirty||progressBusy||progressPending} onActivity={value=>{setChecksBusy(value);onActivity(value)}}/>}
  <WorkflowMappingProgress taskId={taskId} disabled={busy||disabled||catalogDirty||stale||checksBusy} payload={lastPayload} previewToken={result?.preview_token||null} canSave={!!result&&resultSignature===stateSignature&&!locked} onBusy={value=>{setProgressBusy(value);onActivity(value)}} onPending={setProgressPending} onSaved={()=>{if(liveSignature.current===resultSignature)setDirty(false)}} onRestore={p=>{
   if(context.current!==currentContext||busy||disabled||catalogDirty||stale||progressPending||!source.available||p.revision!==binding.revision||p.reference_id!==binding.reference_id||p.merge_token!==binding.merge_token||p.document_token!==binding.document_token||JSON.stringify(Object.keys(p.node_models_json).sort())!==JSON.stringify(Object.keys(source.node_models_json).sort())||JSON.stringify(Object.keys(p.dataset_mapping).sort())!==JSON.stringify([...source.dataset_ids].sort()))return false;
   setTarget(p.target_environment_id);setModels(p.node_models_json);setDatasets(p.dataset_mapping);setRerankers(p.node_rerankers);setDependencies(p.dependency_mapping);setAdditional(p.additional_dependencies.join('\n'));setCatalogNode('');setConsolidationAck(false);setAck(false);setRetainedAck(false);setResult(null);setLastPayload(null);setReviews({});setDirty(true);setDiscard(false);setError('');return true;
  }}/>
  {error&&<p className="callout amber" role="alert">{error}</p>}
  {result&&!stale&&<div className="workflow-mapping-result"><b>目标文件：资源待验证</b>{resultSignature!==stateSignature&&<p className="hint">本次输入或复核尚未通过新检查；上次候选只供参考，下载已禁用。</p>}<p>{result.note}</p>{result.warnings.map((w,i)=><p className="hint" key={i}>{w}</p>)}
   {!result.validation.valid&&<div className="callout amber">目标静态检查尚未通过：{result.validation.errors.join('；')}。不能下载为静态通过成果。</div>}
   <details><summary>完整逐项变更</summary><pre>{JSON.stringify(result.changes,null,2)}</pre></details><details><summary>目标候选完整YAML</summary><pre>{result.content}</pre></details>
   {!!(result.target_parallel_candidates.length||result.target_loop_candidates.length)&&<fieldset disabled={locked}><legend>目标文件的独立容器复核</legend><p className="hint">来源声明不沿用。按上方完整目标图重新核对；次数不是费用硬上限，不代表已运行。</p>
    {result.target_parallel_candidates.map(row=><div key={'p:'+row.id}><b>目标并行 {row.title} · {row.parallel_nums}</b><textarea aria-label={'目标并行说明 '+row.id} maxLength={2000} value={reviews['p:'+row.id]?.reason||''} onChange={e=>review('p:'+row.id,{reason:e.target.value,ack:false})}/><label><input type="checkbox" aria-label={'确认目标并行 '+row.id} checked={!!reviews['p:'+row.id]?.ack} onChange={e=>review('p:'+row.id,{ack:e.target.checked})}/>明确核对独立性、顺序、外部副作用及并发费用</label></div>)}
    {result.target_loop_candidates.map(row=><div key={'l:'+row.id}><b>目标循环 {row.title} · 最大{row.loop_count}次</b>{row.variables.map(name=><label key={name}><input type="checkbox" aria-label={`目标循环进度 ${row.id}.${name}`} checked={!!reviews['l:'+row.id]?.variables.includes(name)} onChange={e=>{const v=reviews['l:'+row.id]?.variables||[];review('l:'+row.id,{variables:e.target.checked?[...v,name]:v.filter(s=>s!==name),ack:false})}}/>{name}</label>)}<input aria-label={'目标循环无进展上限 '+row.id} value={reviews['l:'+row.id]?.limit||''} onChange={e=>review('l:'+row.id,{limit:e.target.value,ack:false})}/><textarea aria-label={'目标循环说明 '+row.id} maxLength={2000} value={reviews['l:'+row.id]?.reason||''} onChange={e=>review('l:'+row.id,{reason:e.target.value,ack:false})}/><label><input type="checkbox" aria-label={'确认目标循环 '+row.id} checked={!!reviews['l:'+row.id]?.ack} onChange={e=>review('l:'+row.id,{ack:e.target.checked})}/>明确核对进度、停止和无进展保护、外部副作用及费用</label></div>)}
    <button className="secondary" onClick={()=>void prepare(true)}>复核目标容器并重新检查</button></fieldset>}
   <button className="secondary" disabled={locked||!result.can_download||resultSignature!==stateSignature} onClick={download}>下载待验证流程DSL</button>
  </div>}
  {dirty&&<details><summary>明确清除本页流程映射输入</summary><label><input type="checkbox" disabled={busy||catalogDirty||progressBusy||progressPending||checksBusy} checked={discard} onChange={e=>setDiscard(e.target.checked)}/>已另存需要的输入，同意清除本页未保存映射</label><button className="secondary" disabled={busy||catalogDirty||progressBusy||progressPending||checksBusy||!discard} onClick={reset}>清除流程映射输入</button></details>}
 </section>
}
