export type ResourceInventory={available:true;mode:'workflow'|'advanced-chat';document_token:string;nodes_scanned:number;
 entries:{category:string;label:string;location:string;identifiers:string[];requirement:string;impact:string}[];
 blockers:string[];warnings:string[];note:string;verification:'source_resource_inventory_only';
 target_resources_verified:false;platform_verified:false;business_verified:false;task_modified:false}|{available:false;reason:string};

export default function WorkflowResourceInventory({inventory}:{inventory:ResourceInventory}){
 return <details className="workflow-resource-inventory"><summary>跨环境资源清单（来源预览）</summary>
  <p className="hint">只整理当前合并文件，不查询目标、不改写DSL或任务，不表示已迁移、资源可用或业务通过。</p>
  {inventory.available?<>
   <p>{inventory.mode==='workflow'?'Workflow':'Chatflow'} · 扫描 {inventory.nodes_scanned} 个节点</p>
   {!!inventory.blockers.length&&<div className="callout amber"><b>尚未完整适配的条件</b><ul>{inventory.blockers.map((s,i)=><li key={i}>{s}</li>)}</ul></div>}
   {inventory.warnings.map((s,i)=><p className="hint" key={i}>{s}</p>)}
   {!inventory.entries.length&&<p>当前未列出结构化资源项，仍须核对代码、外部副作用和环境条件。</p>}
   {inventory.entries.map((entry,i)=><article className="merge-conflict" key={i}>
    <b>{entry.label}</b><p>{entry.location}</p>
    {entry.identifiers.length?<ul>{entry.identifiers.map((s,j)=><li key={j}>{s}</li>)}</ul>:<p className="hint">无可展示标识</p>}
    <p>目标需核对：{entry.requirement}</p><p>体验与投入：{entry.impact}</p>
   </article>)}<p className="hint">{inventory.note}</p>
  </>:<div className="callout amber">资源清单无法完整整理：{inventory.reason} 原文件仍保留，不将其当作空清单。</div>}
 </details>
}
