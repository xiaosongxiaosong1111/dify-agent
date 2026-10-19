const rootEntry=(n:{type:string})=>['start','trigger-schedule'].includes(n.type);
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:unknown[]};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);

export function upstreamNodes(plan:Plan,target:string){
 const ids=new Set(plan.nodes.map(n=>n.id)),starts=plan.nodes.filter(rootEntry);
 if(ids.size!==plan.nodes.length||starts.length!==1)return [];
 const predecessors=new Map([...ids].map(id=>[id,new Set<string>()])),successors=new Map([...ids].map(id=>[id,new Set<string>()]));
 for(const edge of plan.edges){if(!object(edge)||typeof edge.source!=='string'||typeof edge.target!=='string'||!ids.has(edge.source)||!ids.has(edge.target))return [];predecessors.get(edge.target)!.add(edge.source);successors.get(edge.source)!.add(edge.target)}
 const start=starts[0].id,reached=new Set([start]),pending=[start];
 while(pending.length)for(const next of successors.get(pending.pop()!)!)if(!reached.has(next)){reached.add(next);pending.push(next)}
 if(!reached.has(target))return [];
 const degree=new Map([...reached].map(id=>[id,[...predecessors.get(id)!].filter(p=>reached.has(p)).length])),queue=[...degree].filter(([,n])=>n===0).map(([id])=>id),topology:string[]=[];
 while(queue.length){const current=queue.pop()!;topology.push(current);for(const next of successors.get(current)!)if(degree.has(next)){degree.set(next,degree.get(next)!-1);if(degree.get(next)===0)queue.push(next)}}
 if(topology.length!==reached.size)return [];
 const dominators=new Map<string,Set<string>>();
 for(const id of topology){const parents=[...predecessors.get(id)!].filter(p=>reached.has(p)),common=id===start?new Set<string>():parents.length?new Set(dominators.get(parents[0])):new Set<string>();for(const p of parents.slice(1))for(const ancestor of common)if(!dominators.get(p)?.has(ancestor))common.delete(ancestor);common.add(id);dominators.set(id,common)}
 return plan.nodes.filter(n=>n.id!==target&&dominators.get(target)?.has(n.id));
}

/** Branch producers for aggregation; unlike ordinary references, need not dominate. */
export function ancestorNodes(plan:Plan,target:string){
 if(!upstreamNodes(plan,target).some(rootEntry))return [];
 const reached=new Set<string>(),forward=[plan.nodes.find(rootEntry)!.id];
 while(forward.length){const id=forward.pop()!;if(reached.has(id))continue;reached.add(id);for(const edge of plan.edges)if(object(edge)&&edge.source===id&&typeof edge.target==='string'&&!reached.has(edge.target))forward.push(edge.target)}
 const pending=[target],visited=new Set<string>();
 while(pending.length){const id=pending.pop()!;for(const edge of plan.edges)if(object(edge)&&edge.target===id&&typeof edge.source==='string'&&!visited.has(edge.source)){visited.add(edge.source);pending.push(edge.source)}}
 return plan.nodes.filter(node=>node.id!==target&&visited.has(node.id)&&reached.has(node.id));
}

export function extractionSuccessAvailable(plan:Plan,source:Node,target:string){
 const policy=source.config?.failure_policy;if(!object(policy))return false;
 const guard=plan.nodes.find(node=>node.id===policy.guard_node_id),cases=guard?.config?.cases;
 if(guard?.type!=='if-else'||!Array.isArray(cases)||cases.length!==1||!object(cases[0]))return false;
 const row=cases[0],conditions=row.conditions;
 if(policy.behavior!=='explicit_success_branch'||row.case_id!==policy.success_case_id||row.logical_operator!=='and'||!Array.isArray(conditions)||conditions.length!==1||!object(conditions[0]))return false;
 const condition=conditions[0];
 if(JSON.stringify(condition.variable_selector)!==JSON.stringify([source.id,'__is_success'])||condition.varType!=='number'||condition.comparison_operator!=='='||condition.value!=='1')return false;
 const exits=plan.edges.filter(edge=>object(edge)&&edge.source===source.id);
 if(exits.length!==1||!object(exits[0])||exits[0].target!==guard.id)return false;
 const success=plan.edges.filter(edge=>object(edge)&&edge.source===policy.guard_node_id&&(edge.source_handle??edge.sourceHandle)===policy.success_case_id);
 if(success.length!==1||!object(success[0])||typeof success[0].target!=='string')return false;
 const next=success[0].target;if(next!==target&&!upstreamNodes(plan,target).some(node=>node.id===next))return false;
 // Dominance alone misses a failure path that rejoins the nominal success node.
 // The actual success edge must be necessary to reach the consumer.
 const starts=plan.nodes.filter(node=>node.type==='start');if(starts.length!==1)return false;
 const pending=[starts[0].id],visited=new Set<string>();
 while(pending.length){const id=pending.pop()!;if(id===target)return false;if(visited.has(id))continue;visited.add(id);for(const edge of plan.edges){if(edge===success[0])continue;if(!object(edge)||typeof edge.source!=='string'||typeof edge.target!=='string')return false;if(edge.source===id&&!visited.has(edge.target))pending.push(edge.target)}}
 return true;
}

