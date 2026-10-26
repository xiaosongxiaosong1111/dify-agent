import {useEffect,useRef,useState} from 'react';
export type EmbeddingEnvironment={id:string;name?:string;base_url:string;version:string;connection_revision?:string|null;console_workspace_id?:string};
export type EmbeddingChoice={scope:string;provider:string;model:string;observed_at:string};
type Embedding={provider:string;provider_label:string;model:string;status:string;selectable:boolean;model_type:'text-embedding'};
export const embeddingSource=(taskId:string,revision:number,environmentId:string|null,environment:EmbeddingEnvironment|null)=>JSON.stringify([taskId,revision,environmentId,environment?.id,environment?.base_url,environment?.version,environment?.connection_revision??null,environment?.console_workspace_id??null]);
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const text=(v:unknown,limit:number):v is string=>typeof v==='string'&&v.length>0&&v.length<=limit*2&&Array.from(v).length<=limit;
const invalid=()=>Error('Embedding目录的环境归属、连接版本、类型或完整候选无法核对，未沿用旧目录或自动重试。');
export default function EmbeddingCatalogPicker({environmentId,environment,scope,disabled,onChoice}:{environmentId:string|null;environment:EmbeddingEnvironment|null;scope:string;disabled:boolean;onChoice:(choice:EmbeddingChoice|null)=>void}){
 const [rows,setRows]=useState<Embedding[]|null>(null),[selected,setSelected]=useState(''),[observed,setObserved]=useState(''),[working,setWorking]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),currentScope=useRef(scope),choice=useRef(onChoice);currentScope.current=scope;choice.current=onChoice;
 useEffect(()=>{epoch.current++;controller.current?.abort();setRows(null);setSelected('');setObserved('');setWorking(false);setError('');choice.current(null);return()=>{epoch.current++;controller.current?.abort()}},[scope]);
 async function read(){
  if(disabled||working)return;const ticket=++epoch.current,abort=new AbortController();controller.current?.abort();controller.current=abort;setRows(null);setSelected('');setObserved('');setError('');setWorking(true);choice.current(null);
  const current=()=>ticket===epoch.current&&currentScope.current===scope&&!abort.signal.aborted,timer=setTimeout(()=>abort.abort(),15000);
  try{
   if(!environmentId||!environment||environment.id!==environmentId||!text(environment.base_url,2000)||!text(environment.version,100)||!(environment.connection_revision==null||text(environment.connection_revision,200)))throw Error('请先保存并核对当前Dify环境信息，再主动读取Embedding目录。');
   const response=await fetch(`${import.meta.env.VITE_API_BASE||'/api'}/environments/${encodeURIComponent(environmentId)}/models?model_type=text-embedding`,{cache:'no-store',signal:abort.signal});const value=await response.json();if(!current())return;
   if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Embedding目录读取失败，未使用旧候选。');
   if(!object(value)||value.source!=='console'||value.model_type!=='text-embedding'||value.environment_id!==environmentId||value.connection_revision!==(environment.connection_revision??null)||typeof value.observed_at!=='string'||!Number.isFinite(Date.parse(value.observed_at))||!Array.isArray(value.data)||value.data.length>1000||new TextEncoder().encode(JSON.stringify(value.data)).length>2_000_000)throw invalid();
   const seen=new Set<string>();
   for(const row of value.data){
    if(!object(row)||!text(row.provider,256)||!text(row.model,256)||!text(row.provider_label,512)||!text(row.status,100)||typeof row.selectable!=='boolean'||row.model_type!=='text-embedding')throw invalid();
    const key=JSON.stringify([row.provider,row.model]);if(seen.has(key))throw invalid();seen.add(key);
   }
   setRows(value.data as Embedding[]);setObserved(value.observed_at);
  }catch(e){if(current()||abort.signal.aborted&&ticket===epoch.current)setError(abort.signal.aborted?'Embedding读取已停止或超时，未自动重试。':e instanceof Error&&!(e instanceof TypeError||e instanceof SyntaxError||e instanceof DOMException)?e.message:'Embedding目录或网络响应无法核对，请保留表单后明确重读。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 return <div className="embedding-catalog-picker"><button className="secondary full" disabled={disabled||working} onClick={()=>void read()}>{working?'正在读取当前环境Embedding目录…':'读取实际 Embedding 模型'}</button><label className="field"><span>Embedding 模型</span><select aria-label="知识库 Embedding 模型" value={selected} disabled={disabled||working||rows===null} onChange={e=>{const item=rows?.find(row=>JSON.stringify([row.provider,row.model])===e.target.value&&row.selectable);setSelected(item?e.target.value:'');choice.current(item?{scope,provider:item.provider,model:item.model,observed_at:observed}:null)}}><option value="">请明确选择本次目录中的模型</option>{rows?.map(row=><option key={JSON.stringify([row.provider,row.model])} value={JSON.stringify([row.provider,row.model])} disabled={!row.selectable}>{row.provider_label} · {row.model} · {row.status}</option>)}</select></label>{error&&<p role="alert" className="callout amber">{error}</p>}{rows!==null&&<><p className="hint">本次目录{rows.length}项，来源环境{environment?.name||environmentId}，观察时间{new Date(observed).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false})}（北京时间）。观察不保证持续可用，生成方案前后台仍会再次核对。</p>{!rows.some(row=>row.selectable)&&<p>本次目录没有可选Embedding模型；未自动改用经济索引。</p>}<details><summary>核对目录来源</summary><p>环境{environmentId} · 连接版本{environment?.connection_revision??'旧记录未提供'} · 类型text-embedding</p><p className="hint">Task/修订、环境URL/版本/连接与工作空间记录变化会清除本页目录及选择；友好名称变化不清除。不对缺失、重复或超过1000项/2MB的候选截断后作为完整目录。</p></details></>}</div>;
}
