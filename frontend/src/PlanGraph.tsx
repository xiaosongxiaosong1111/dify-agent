import {useEffect,useId,useMemo,useState} from 'react';
import PlanConnections,{traceConnections} from './PlanConnections';

type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:{source:string;target:string;source_handle?:string}[]};
type Point={x:number;y:number};
const names:Record<string,string>={start:'开始','trigger-schedule':'定时触发','human-input':'人工审核',llm:'大模型','knowledge-retrieval':'知识检索','if-else':'条件分支',code:'代码','template-transform':'模板','http-request':'HTTP 请求',iteration:'迭代',loop:'循环','variable-aggregator':'变量聚合',end:'结束',answer:'回答'};
const colors:Record<string,string>={start:'#64748b','trigger-schedule':'#64748b','human-input':'#d39320',end:'#64748b',answer:'#64748b',llm:'#7762e8','knowledge-retrieval':'#169981','if-else':'#d39320',code:'#4283d8','template-transform':'#4283d8','http-request':'#c76750',iteration:'#9963c5',loop:'#bf7354','variable-aggregator':'#189b91'};

function arrange(plan:Plan){
 const nodes=plan.nodes.slice(0,100),ids=new Set(nodes.map(n=>n.id)),edges=plan.edges.filter(e=>ids.has(e.source)&&ids.has(e.target)).slice(0,250),degree=new Map(nodes.map(n=>[n.id,0])),rank=new Map(nodes.map(n=>[n.id,0])),visited=new Set<string>();
 for(const e of edges)degree.set(e.target,(degree.get(e.target)||0)+1);
 const queue=nodes.filter(n=>degree.get(n.id)===0).map(n=>n.id);
 for(let i=0;i<queue.length;i++){
  const id=queue[i];if(visited.has(id))continue;visited.add(id);
  for(const e of edges.filter(e=>e.source===id)){rank.set(e.target,Math.max(rank.get(e.target)||0,(rank.get(id)||0)+1));degree.set(e.target,(degree.get(e.target)||0)-1);if(degree.get(e.target)===0)queue.push(e.target)}
 }
 const cyclic=nodes.filter(n=>!visited.has(n.id));const maxRank=Math.max(0,...rank.values());cyclic.forEach(n=>rank.set(n.id,maxRank+1));
 const rows=new Map<number,number>(),points=new Map<string,Point>();
 for(const n of nodes){const col=rank.get(n.id)||0,row=rows.get(col)||0;points.set(n.id,{x:28+col*220,y:28+row*104});rows.set(col,row+1)}
 const warnings:string[]=[];
 if(plan.nodes.length>100)warnings.push('当前只绘制前 100 个顶层节点，未绘制部分仍保留在 JSON 编辑器；不代表已完整预览。');
 if(plan.edges.length!==edges.length)warnings.push(`${plan.edges.length-edges.length} 条连接未绘制：引用未显示／不存在节点或超过 250 条预览上限，请核对原始 JSON。`);
 if(cyclic.length)warnings.push('存在环或依赖环的节点，暂放在右侧；此预览不认可循环结构，须以后端检查为准。');
 if(new Set(plan.nodes.map(n=>n.id)).size!==plan.nodes.length)warnings.push('节点 ID 重复，不能可靠预览或选中，请先修正。');
 return {nodes,edges,points,warnings,width:Math.max(440,...[...points.values()].map(p=>p.x+196)),height:Math.max(160,...[...points.values()].map(p=>p.y+86))};
}

export default function PlanGraph({plan,nested=false}:{plan:Plan|null;nested?:boolean}){
 const id=useId().replace(/[^a-zA-Z0-9_-]/g,''),[zoom,setZoom]=useState(1),[selected,setSelected]=useState(''),[direction,setDirection]=useState<'adjacent'|'upstream'|'downstream'>('adjacent');
 const layout=useMemo(()=>plan?arrange(plan):null,[plan]);
 useEffect(()=>{setSelected('');setZoom(1);setDirection('adjacent')},[plan]);
 const unique=!!layout&&new Set(layout.nodes.map(n=>n.id)).size===layout.nodes.length&&!!plan&&new Set(plan.nodes.map(n=>n.id)).size===plan.nodes.length;
 const trace=useMemo(()=>layout&&selected&&unique&&direction!=='adjacent'?traceConnections(layout.nodes,layout.edges,selected,direction):null,[layout,selected,unique,direction]);
 if(!plan||!layout)return null;
 const node=plan.nodes.find(n=>n.id===selected),body=node&&['iteration','loop'].includes(node.type)&&Array.isArray(node.config?.nodes)?node.config.nodes as Node[]:[];
 const innerEdges=Array.isArray(node?.config?.edges)&&node.config.edges.every(e=>e&&typeof e==='object'&&typeof (e as {source?:unknown}).source==='string'&&typeof (e as {target?:unknown}).target==='string'&&((e as {source_handle?:unknown}).source_handle===undefined||typeof (e as {source_handle?:unknown}).source_handle==='string'))?node.config.edges as Plan['edges']:null;
 return <section className="plan-graph" aria-label="流程图预览"><div className="listhead"><b>流程图预览</b><div className="actions"><button className="secondary" disabled={zoom<=.5} aria-label="缩小流程图" onClick={()=>setZoom(v=>Math.max(.5,v-.25))}>−</button><span>{Math.round(zoom*100)}%</span><button className="secondary" disabled={zoom>=2} aria-label="放大流程图" onClick={()=>setZoom(v=>Math.min(2,v+.25))}>＋</button><button className="secondary" onClick={()=>{setZoom(1);setSelected('');setDirection('adjacent')}}>重置图预览</button></div></div>
  <p className="hint">根据当前编辑器草稿绘制，点击节点查看配置，横向滚动浏览连接。布局、选择和缩放只影响预览，不修改 DSL；不代表静态校验、导入或运行通过。</p>{layout.warnings.map((w,i)=><p className="callout amber" key={i}>{w}</p>)}
  <div className="plan-graph-scroll"><svg role="group" aria-label="当前流程节点与连接" viewBox={`0 0 ${layout.width} ${layout.height}`} style={{width:layout.width*zoom,height:layout.height*zoom}}>
   <defs><marker id={`arrow-${id}`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8a91b2"/></marker></defs>
   {layout.edges.map((e,i)=>{const a=layout.points.get(e.source)!,b=layout.points.get(e.target)!,active=trace?trace.active.has(e):selected===e.source||selected===e.target,x1=a.x+168,y1=a.y+29,x2=b.x,y2=b.y+29;const path=x2>x1?`M ${x1} ${y1} C ${x1+24} ${y1} ${x2-24} ${y2} ${x2-5} ${y2}`:`M ${x1} ${y1} C ${x1+35} ${y1+55} ${x2-35} ${y2+55} ${x2-5} ${y2}`;return <g key={i} opacity={trace&&!active?0.3:1} data-traced={trace?active:undefined}><title>{`${e.source} → ${e.target}${e.source_handle?`（${e.source_handle}）`:''}`}</title><path d={path} fill="none" stroke={active?'#7155d8':'#b5bdd1'} strokeWidth={active?2.5:1.5} markerEnd={`url(#arrow-${id})`}/>{e.source_handle&&e.source_handle!=='source'&&<text x={(x1+x2)/2} y={(y1+y2)/2-7} fill="#637087" fontSize="10" textAnchor="middle">{e.source_handle==='false'&&plan.nodes.find(n=>n.id===e.source)?.type==='if-else'?'默认分支':e.source_handle.slice(0,25)}</text>}</g>})}
   {layout.nodes.map((n,i)=>{const p=layout.points.get(n.id)!;return <g key={`${n.id}-${i}`} role="button" tabIndex={unique?0:-1} aria-disabled={!unique} opacity={trace&&!trace.reached.has(n.id)?0.3:1} data-traced={trace?trace.reached.has(n.id):undefined} aria-label={`查看节点：${n.title||names[n.type]||n.id}（${n.id}）`} aria-pressed={selected===n.id} className="graph-node" onClick={()=>{if(unique)setSelected(n.id)}} onKeyDown={e=>{if(unique&&(e.key==='Enter'||e.key===' ')){e.preventDefault();setSelected(n.id)}}} transform={`translate(${p.x},${p.y})`}>
    <title>{n.title||n.id} · {n.type} · 点击查看配置</title><rect width="168" height="62" rx="8" fill={selected===n.id?'#f0edff':'#fff'} stroke={selected===n.id?'#745bd6':'#dce0ed'} strokeWidth={selected===n.id?2:1}/><rect x="0" y="7" width="4" height="48" rx="2" fill={colors[n.type]||'#999'}/><text x="13" y="23" fill="#242d46" fontSize="12" fontWeight="600">{(n.title||names[n.type]||n.type).slice(0,15)}</text><text x="13" y="44" fill="#697691" fontSize="10">{n.id.slice(0,23)} · {n.type==='iteration'?n.config?.is_parallel===true?'并行':'顺序':names[n.type]||n.type}</text>
   </g>})}
  </svg></div>
  {node&&<div className="graph-node-detail"><b>当前节点：{node.title||node.id}（{node.id} / {node.type}）</b><p className="hint">配置为当前草稿原文；可能尚未校验或含未支持字段。修改请使用 JSON 编辑器，查看不会采纳任何变更。</p><div className="graph-trace-controls"><label>结构追踪范围<select aria-label="节点结构追踪范围" value={direction} onChange={e=>setDirection(e.target.value as typeof direction)}><option value="adjacent">仅相邻连接</option><option value="upstream">全部结构上游</option><option value="downstream">全部结构下游</option></select></label>{trace&&<p className="hint">当前绘图范围内结构可达 {trace.reached.size} 个节点、{trace.active.size} 条连接（含当前节点）；所有可能分支都会包含，不模拟条件、迭代次数或执行路径。</p>}</div><PlanConnections plan={plan} nodes={layout.nodes} edges={layout.edges} node={node} onSelect={setSelected}/><details open><summary>当前节点配置原文</summary><pre>{JSON.stringify(node.config||{},null,2)}</pre></details>{!!body.length&&<details><summary>{node.type==="loop"?"循环":"迭代"}内部{node.config?.edges!==undefined?'条件与连接':'顺序步骤'} · {body.length} 个</summary>{!nested&&innerEdges&&<><p className="hint">内部入口：{String(node.config?.entry_node_id||'未明确')}；按实际内部连接预览，不按节点列表顺序执行。仍须后台检查与实际试跑。</p><PlanGraph nested plan={{nodes:body,edges:innerEdges}}/></>}{node.config?.edges!==undefined&&!innerEdges&&<p className="callout amber">内部连接结构无法预览，请核对 edges 的字段；不会当作已验证。</p>}{body.map((child,i)=><div key={`${child.id}-${i}`}><b>{i+1}. {child.title||child.id} · {child.type}</b><pre>{JSON.stringify(child.config||{},null,2)}</pre></div>)}</details>}</div>}
 </section>;
}
