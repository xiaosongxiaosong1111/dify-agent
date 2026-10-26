export type GraphNode={id:string;type:string;title?:string;config?:Record<string,unknown>};
export type GraphEdge={source:string;target:string;source_handle?:string};
export type GraphPlan={nodes:GraphNode[];edges:GraphEdge[]};

/** Structural reachability in the displayed scope, never condition evaluation. */
export function traceConnections(nodes:GraphNode[],edges:GraphEdge[],selected:string,direction:'upstream'|'downstream'){
 const allowed=new Set(nodes.map(n=>n.id)),reached=new Set<string>(),active=new Set<GraphEdge>();
 if(!allowed.has(selected)||allowed.size!==nodes.length)return {reached,active};
 reached.add(selected);const queue=[selected];
 for(let i=0;i<queue.length;i++)for(const e of edges){
  if(!allowed.has(e.source)||!allowed.has(e.target))continue;
  const from=direction==='upstream'?e.target:e.source,to=direction==='upstream'?e.source:e.target;
  if(from!==queue[i])continue;active.add(e);
  if(!reached.has(to)){reached.add(to);queue.push(to)}
 }
 return {reached,active};
}

type Binding={path:string;selector:string[]|null};
function bindings(config:Record<string,unknown>){
 const found:Binding[]=[];let visited=0,limited=false;
 function walk(value:unknown,path:string,depth:number){
  if(++visited>2000||depth>16||found.length>=40){limited=true;return}
  if(Array.isArray(value)){for(let i=0;i<value.length;i++){if(visited>2000||found.length>=40){limited=true;break}walk(value[i],`${path}/${i}`,depth+1)}return}
  if(!value||typeof value!=='object')return;
   for(const key of Object.keys(value)){
   const item=(value as Record<string,unknown>)[key];
   if(visited>2000||found.length>=40){limited=true;break}
   const next=`${path}/${key.replace(/~/g,'~0').replace(/\//g,'~1')}`;
   // Nested containers have their own graph/scope; do not misattribute child bindings.
   if(key==='nodes'||key==='edges')continue;
   if(key==='value_selector'||key==='variable_selector'||key==='input_selector'||key==='iterator_selector'||key==='output_selector'){
    found.push({path:next,selector:Array.isArray(item)&&item.length>=2&&item.every(x=>typeof x==='string'&&!!x)?item as string[]:null});visited++;
   }else walk(item,next,depth+1);
  }
 }
 walk(config,'/config',0);return {found,limited};
}

export default function PlanConnections({plan,nodes,edges,node,onSelect}:{plan:GraphPlan;nodes:GraphNode[];edges:GraphEdge[];node:GraphNode;onSelect:(id:string)=>void}){
 const ids=new Set(nodes.map(n=>n.id)),unique=new Set(plan.nodes.map(n=>n.id)).size===plan.nodes.length;
 const all=plan.edges.filter(e=>e.source===node.id||e.target===node.id),shown=all.slice(0,60),values=bindings(node.config||{});
 const link=(id:string,binding=false)=>{if(binding&&(id==='sys'||id==='conversation'))return <span>{id} · 系统／会话作用域，非当前层节点</span>;const candidates=plan.nodes.filter(n=>n.id===id),target=candidates[0];if(!target)return <span className="callout amber">{id} · 当前层节点不存在</span>;if(!unique)return <span>{id} · ID重复，不能可靠定位</span>;if(!ids.has(id))return <span>{target.title||id}（{id}）· 超出当前绘图范围</span>;return <button type="button" className="secondary" onClick={()=>onSelect(id)} aria-label={`定位连接节点：${id}`}>{target.title||id}（{id}）</button>};
 return <div className="plan-connections"><b>当前层连接与变量来源</b><p className="hint">按当前草稿逐项列出原始连接。结构可达不表示条件命中、先后执行或分支变量可用；容器按单个节点看，不穿透内外层。只预览，不修改或执行。</p>
  <details open><summary>进出连接 · {all.length} 条</summary>{!all.length&&<p>当前层没有进出连接。</p>}{shown.map((e,i)=><div className="graph-connection-row" key={i}><span>{e.target===node.id?'进入':'离开'}：{e.source} → {e.target}</span><small>原始分支handle：{e.source_handle===undefined?'未设置':JSON.stringify(e.source_handle)}{e.source_handle==='false'&&plan.nodes.find(n=>n.id===e.source)?.type==='if-else'?'（条件默认分支）':''} · {edges.includes(e)?'已绘制':'未绘制，须核对原始JSON'}</small>{link(e.target===node.id?e.source:e.target)}</div>)}{all.length>shown.length&&<p className="callout amber">仅列前60条，未列部分保留在原始JSON；不能据此认为已检查全部连接。</p>}</details>
  <details><summary>显式变量选择器 · {values.found.length} 项{values.limited?'（范围受限）':''}</summary>{!values.found.length&&<p>未找到首批识别的显式选择器；不代表没有变量引用。提示词内联引用、隐式绑定和子容器另行核对。</p>}{values.found.map((binding,i)=><div className="graph-connection-row" key={i}><code>{binding.path}</code>{binding.selector?<><code>{JSON.stringify(binding.selector)}</code>{link(binding.selector[0],true)}<small>只定位同层同名节点，不证明变量字段存在、数据类型正确或分支可用。sys/conversation、父层或未出现的节点须另查。</small></>:<p className="callout amber">选择器不是至少两项非空文字数组，未猜测或定位。</p>}</div>)}{values.limited&&<p className="callout amber">选择器查找达到40项／2000结构项／16层上限；未覆盖部分须核对原文，不当作没有引用。</p>}</details>
 </div>;
}
