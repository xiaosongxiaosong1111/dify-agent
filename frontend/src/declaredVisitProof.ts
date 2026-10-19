export type Node={id:string;type:string;config?:Record<string,unknown>};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const count=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
const keys=['model_nodes','retrieval_nodes','http_nodes'] as const;
type Groups=Record<typeof keys[number],number|null>;
const empty=():Groups=>({model_nodes:0,retrieval_nodes:0,http_nodes:0});
const container=(kind:string)=>kind==='iteration'||kind==='loop';
const group=(kind:string)=>['llm','question-classifier','parameter-extractor'].includes(kind)?'model_nodes':kind==='knowledge-retrieval'?'retrieval_nodes':kind==='http-request'?'http_nodes':null;
const sameGroups=(actual:unknown,expected:Groups)=>object(actual)&&Object.keys(actual).length===3&&keys.every(k=>Object.hasOwn(actual,k)&&actual[k]===expected[k]);
/** Declaration arithmetic only; no connectivity, final DSL, execution or price proof. */
export function declaredVisitProof(value:unknown,nodes:Node[],counts:Record<string,number>):boolean{
 if(!object(value)||!Array.isArray(nodes)||!object(counts)||!Array.isArray(value.containers))return false;
 if(nodes.some(n=>!object(n)||typeof n.id!=='string'||typeof n.type!=='string'))return false;
 const ids=new Set(nodes.map(n=>n.id));if(ids.size!==nodes.length)return false;
 const iterations=new Set(nodes.filter(n=>n.type==='iteration').map(n=>n.id));
 if(Object.entries(counts).some(([id,n])=>!iterations.has(id)||!count(n)||n>100000))return false;
 const totals=empty(),rows:Record<string,unknown>[]=[];let declared=nodes.length,unknown=false;
 for(const node of nodes){
  const kind=group(node.type);if(kind&&totals[kind]!==null)totals[kind]++;
  if(!container(node.type))continue;
  if(!object(node.config)||!Array.isArray(node.config.nodes))return false;
  const body=node.config.nodes,local=empty(),bodyIds=new Set<string>();
  for(const child of body){
   if(!object(child)||typeof child.id!=='string'||typeof child.type!=='string'||container(child.type)||bodyIds.has(child.id))return false;
   bodyIds.add(child.id);const key=group(child.type);if(key)local[key]!++;
  }
  const multiplier=node.type==='loop'?node.config.loop_count:Object.hasOwn(counts,node.id)?counts[node.id]:null;
  if(multiplier!==null&&!count(multiplier))return false;
  for(const key of keys){const n=local[key]!;if(n&&multiplier===null)totals[key]=null;else if(totals[key]!==null)totals[key]+=n*(multiplier||0);if(totals[key]!==null&&!count(totals[key]))return false;}
  if(multiplier===null)unknown=true;else declared+=body.length*multiplier;
  if(!count(declared))return false;
  rows.push({node_id:node.id,node_type:node.type,body_declared_nodes:body.length,multiplier,basis:node.type==='loop'?'declared_loop_count':multiplier===null?'unknown_item_count':'manual_item_count',body_nodes_per_round:local});
 }
 if(value.declared_root_nodes!==nodes.length||value.max_declared_node_visits!==(unknown?null:declared)||value.has_unknown_item_count!==unknown||!sameGroups(value.max_resource_node_visits,totals)||value.containers.length!==rows.length)return false;
 return value.containers.every((row,i)=>object(row)&&['node_id','node_type','body_declared_nodes','multiplier','basis'].every(k=>Object.hasOwn(row,k)&&row[k]===rows[i][k])&&sameGroups(row.body_nodes_per_round,rows[i].body_nodes_per_round as Groups));
}
