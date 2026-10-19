type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};type Plan={nodes:Node[];edges:unknown[]};
export function bodyScope(plan:Plan,parent:Node):Plan{
 const cfg=parent.config??{},nodes=Array.isArray(cfg.nodes)?cfg.nodes as Node[]:[];let id='__ui_body_sources';while([...plan.nodes,...nodes].some(n=>n.id===id))id+='_';
 const graph='edges' in cfg||'entry_node_id' in cfg,edges=graph?Array.isArray(cfg.edges)?cfg.edges:[]:nodes.slice(1).map((n,i)=>({source:nodes[i].id,target:n.id})),entry=graph?cfg.entry_node_id:nodes[0]?.id;
 return {nodes:[{id,type:'start',config:{variables:[]}},...nodes],edges:[{source:id,target:entry},...edges]};
}
export function textStateSources(parent:Node){
 const cfg=parent.config??{},rows:{selector:string[];label:string}[]=[];
 if(parent.type==='iteration'&&cfg.iterator_input_type==='array[string]')rows.push({selector:[parent.id,'item'],label:`本项文字 · ${parent.id}.item`});
 if(parent.type==='loop'&&Array.isArray(cfg.loop_variables))for(const state of cfg.loop_variables)if(state&&typeof state==='object'&&state.var_type==='string'&&typeof state.label==='string')rows.push({selector:[parent.id,state.label],label:`本轮文字状态 · ${parent.id}.${state.label}`});
 return rows;
}
