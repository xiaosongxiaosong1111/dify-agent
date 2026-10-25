import {useEffect,useRef,useState} from 'react';

type Source={kind:'sierra_adapter'|'upstream_tag';version:string;path?:string;url?:string};
type Entry={id:string;node_type:string;label:string;app_type:string;rules:string[];limitations:string[];sources:Source[];content_sha256:string;example_kind:string;example_plan:Record<string,unknown>;example_configuration:Record<string,unknown>;example_note:string};
type Guidance={schema_version:number;app_type:string;target_dify_version:string;target_dsl_version:string;verification:string;runtime_verified:boolean;complete_catalog:boolean;available_node_types:string[];missing_node_types:string[];items:Entry[];notes:string[]};
const strings=(v:unknown):v is string[]=>Array.isArray(v)&&v.every(x=>typeof x==='string');
function valid(v:Guidance,appType:string,version:string,nodeType:string){
 return v&&v.schema_version===1&&v.app_type===appType&&v.target_dify_version===version&&v.target_dsl_version==='0.7.0'&&v.verification==='static_guidance'&&v.runtime_verified===false&&v.complete_catalog===false&&strings(v.available_node_types)&&strings(v.missing_node_types)&&strings(v.notes)&&Array.isArray(v.items)&&v.items.length<=4&&v.items.every(r=>r&&typeof r.id==='string'&&r.app_type===appType&&typeof r.label==='string'&&typeof r.node_type==='string'&&(!nodeType||r.node_type===nodeType)&&strings(r.rules)&&strings(r.limitations)&&typeof r.content_sha256==='string'&&/^[a-f0-9]{64}$/.test(r.content_sha256)&&r.example_kind==='synthetic_plan'&&r.example_plan&&typeof r.example_plan==='object'&&!Array.isArray(r.example_plan)&&r.example_configuration&&typeof r.example_configuration==='object'&&typeof r.example_note==='string'&&Array.isArray(r.sources)&&r.sources.length>0&&r.sources.every(s=>s&&s.version===version&&(s.kind==='sierra_adapter'&&typeof s.path==='string'||s.kind==='upstream_tag'&&typeof s.url==='string'&&s.url.startsWith(`https://github.com/langgenius/dify/blob/${version}/`))));
}

export default function NodeGuidancePanel({appType,version,nodes}:{appType:string;version:string;nodes:{type:string;label:string}[]}){
 const [open,setOpen]=useState(false),[nodeType,setNodeType]=useState(''),[reload,setReload]=useState(0),[value,setValue]=useState<{key:string;data:Guidance}|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),generation=useRef(0);
 const key=JSON.stringify([appType,version,nodeType]);
 useEffect(()=>{
  setValue(null);setError('');setLoading(false);
  if(!open||appType==='agent')return;
  const ticket=++generation.current,controller=new AbortController(),timer=setTimeout(()=>controller.abort(),12000);setLoading(true);
  const query=new URLSearchParams({app_type:appType,dify_version:version});if(nodeType)query.set('node_types',nodeType);
  fetch('/api/node-guidance?'+query,{signal:controller.signal}).then(async response=>{
   if(!response.ok)throw Error(`节点规则读取失败（HTTP ${response.status}），未使用旧规则代替。`);
   const data=await response.json();if(!valid(data,appType,version,nodeType))throw Error('节点规则类型、版本或格式不匹配，未采用该结果。');
   if(generation.current===ticket)setValue({key,data});
  }).catch(e=>{if(generation.current===ticket)setError(controller.signal.aborted?'节点规则读取超时，请核对本机服务后再读取。':e instanceof Error?e.message:'节点规则读取失败。')}).finally(()=>{clearTimeout(timer);if(generation.current===ticket)setLoading(false)});
  return()=>{generation.current++;clearTimeout(timer);controller.abort()};
 },[appType,version,nodeType,open,reload,key]);
 if(appType==='agent')return <p className="hint">节点专项规则首批适用于Workflow／Chatflow；原生Agent使用独立方案，不套用这些节点示例。</p>;
 const data=value?.key===key?value.data:null;
 return <details className="node-guidance" open={open} onToggle={event=>setOpen(event.currentTarget.open)}><summary>查看节点规则与合成示例</summary><p className="hint">按所选类型和适配目标Dify {version}读取；只读、不调用模型或Dify，不改当前计划。首批覆盖知识检索、条件、Python代码和文字大模型。</p><label>查询节点规则<select aria-label="查询节点规则" value={nodeType} onChange={event=>setNodeType(event.target.value)}><option value="">首批全部专项规则</option>{nodes.map(n=><option key={n.type} value={n.type}>{n.label}</option>)}</select></label>{loading&&<p role="status">正在读取节点规则…</p>}{error&&<div role="alert" className="callout amber">{error}</div>}{data&&<>{data.missing_node_types.length>0&&<p className="callout amber">此节点暂无专项条目（{data.missing_node_types.join('、')}），不代表节点不受支持。请结合当前生成范围及完整契约核对。</p>}{data.items.map(row=><article className="node-guidance-entry" key={row.id}><h4>{row.label} · {row.node_type}</h4><ul>{row.rules.map(rule=><li key={rule}>{rule}</li>)}</ul>{row.limitations.map(note=><p className="hint" key={note}>{note}</p>)}<details><summary>完整示例与来源（不自动应用）</summary><p className="hint">{row.example_note} 配置中的EXAMPLE值只是占位资源，不是真实ID。</p><b>示例配置</b><pre style={{overflowX:'auto'}}>{JSON.stringify(row.example_configuration,null,2)}</pre><label>合成Workflow Plan<textarea aria-label={row.label+'合成Plan示例'} readOnly rows={16} value={JSON.stringify(row.example_plan,null,2)} style={{width:'100%',boxSizing:'border-box',fontSize:13,fontFamily:'monospace',resize:'vertical'}}/></label><ul>{row.sources.map((source,index)=><li key={index}>{source.kind==='upstream_tag'?<a href={source.url} target="_blank" rel="noreferrer">Dify {source.version}固定源码</a>:<span>Sierra适配依据：<code>{source.path}</code>（目标{source.version}）</span>}</li>)}</ul><p className="hint" style={{overflowWrap:'anywhere'}}>条目 {row.id} · 内容摘要 {row.content_sha256}</p></details></article>)}{data.notes.map(note=><p className="hint" key={note}>{note}</p>)}</>}<button className="secondary" disabled={loading} onClick={()=>setReload(n=>n+1)}>重新读取节点规则</button></details>;
}
