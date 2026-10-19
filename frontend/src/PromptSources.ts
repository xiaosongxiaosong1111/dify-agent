import {upstreamNodes} from './PlanSources';
import {bodyScope,textStateSources} from './ContainerSources';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:unknown[]};
type Source={selector:string[];label:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const name=(v:unknown):v is string=>typeof v==='string'&&/^[A-Za-z0-9_-]{1,200}$/.test(v);
/** Only explicitly declared text sources on all paths; no file/array/object conversion. */
export function promptTextSources(plan:Plan,target:string,parentId?:string):Source[]{
 try{
  let upstream:Node[],states:Source[]=[];
  if(parentId){
   const parents=plan.nodes.filter(n=>n.id===parentId&&['iteration','loop'].includes(n.type));if(parents.length!==1)return [];
   const parent=parents[0],outer=upstreamNodes(plan,parentId),inner=upstreamNodes(bodyScope(plan,parent),target);
   if(!outer.some(n=>n.type==='start'||n.type==='trigger-schedule')||!inner.some(n=>n.type==='start'))return [];
   upstream=[...outer,...inner];states=textStateSources(parent);
  }else upstream=upstreamNodes(plan,target);
  if(new Set(upstream.map(n=>n.id)).size!==upstream.length)return [];
  const sources:Source[]=[],seen=new Set<string>();
  const add=(selector:string[],label:string)=>{if(selector.length!==2||!selector.every(name))return;const key=JSON.stringify(selector);if(seen.has(key))return;seen.add(key);sources.push({selector,label})};
  for(const node of upstream){
   const cfg=node.config;if(!name(node.id)||!object(cfg))continue;
   const label=typeof node.title==='string'?node.title:node.id;
   if(node.type==='start'&&Array.isArray(cfg.variables))for(const field of cfg.variables){
    if(!object(field)||!name(field.variable)||!['text-input','paragraph','select'].includes(String(field.type))||field.required!==true&&typeof field.default!=='string')continue;
    add([node.id,field.variable],`${typeof field.label==='string'?field.label:field.variable} · ${node.id}.${field.variable}`);
   }
   if(node.type==='llm')add([node.id,'text'],`${label} · ${node.id}.text`);
   if(node.type==='template-transform'&&typeof cfg.template==='string')add([node.id,'output'],`${label} · ${node.id}.output`);
   if(node.type==='document-extractor'&&cfg.input_type==='file')add([node.id,'text'],`${label} · ${node.id}.text`);
   if(node.type==='code'&&object(cfg.outputs))for(const [key,value] of Object.entries(cfg.outputs))if(object(value)&&value.type==='string')add([node.id,key],`${label} · ${node.id}.${key}`);
  }
  for(const state of states)add(state.selector,state.label);
  return sources;
 }catch{return []}
}
