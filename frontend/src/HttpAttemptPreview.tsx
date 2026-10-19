type Node={id:string;type:string;config?:Record<string,unknown>};
type Row={node_id:string;scope_id:string|null;logical_visits:number|null;attempts_per_visit:number;max_attempts:number|null;retry_enabled:boolean;max_retries:number;retry_interval_ms:number};
export type HttpAttempts={total:number|null;nodes:Row[];basis:'declared_http_node_retries_only';actual_http_requests_known:false;internal_requests_counted:false};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const count=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
export function httpAttemptProof(value:unknown,nodes:Node[],counts:Record<string,number>):value is HttpAttempts{
 if(!object(value)||value.basis!=='declared_http_node_retries_only'||value.actual_http_requests_known!==false||value.internal_requests_counted!==false||!Array.isArray(value.nodes))return false;
 const expected:Row[]=[];
 const add=(node:Node,scope:string|null,multiplier:number|null)=>{
  if(node.type!=='http-request')return true;
  const raw=node.config?.retry_config,r=raw===undefined?{retry_enabled:false,max_retries:0,retry_interval:0}:raw;
  if(!object(r)||Object.keys(r).length!==3||typeof r.retry_enabled!=='boolean'||!count(r.max_retries)||r.max_retries>10||r.retry_enabled&&r.max_retries===0||!count(r.retry_interval)||r.retry_interval>5000)return false;
  const factor=r.retry_enabled?1+r.max_retries:1,attempts=multiplier===null?null:multiplier*factor;
  if(attempts!==null&&!count(attempts))return false;
  expected.push({node_id:node.id,scope_id:scope,logical_visits:multiplier,attempts_per_visit:factor,max_attempts:attempts,retry_enabled:r.retry_enabled,max_retries:r.max_retries,retry_interval_ms:r.retry_interval});return true;
 };
 for(const node of nodes){if(!add(node,null,1))return false;if(['iteration','loop'].includes(node.type)){
  const body=node.config?.nodes;if(!Array.isArray(body))return false;
  const multiplier=node.type==='loop'?node.config?.loop_count:Object.hasOwn(counts,node.id)?counts[node.id]:null;
  if(multiplier!==null&&!count(multiplier))return false;
  for(const child of body){if(!object(child)||typeof child.id!=='string'||typeof child.type!=='string'||!add(child as Node,node.id,multiplier))return false}
 }}
 if(value.nodes.length!==expected.length)return false;
 const keys: (keyof Row)[]=['node_id','scope_id','logical_visits','attempts_per_visit','max_attempts','retry_enabled','max_retries','retry_interval_ms'];
 if(!value.nodes.every((row,i)=>object(row)&&keys.every(k=>row[k]===expected[i][k])))return false;
 const total=expected.some(r=>r.max_attempts===null)?null:expected.reduce((n,r)=>n+(r.max_attempts||0),0);
 return value.total===total&&(total===null||count(total));
}
const show=(n:number|null)=>n===null?'未知':n.toLocaleString('zh-CN');
export default function HttpAttemptPreview({value}:{value:HttpAttempts|undefined}){
 if(value===undefined)return <p className="hint">服务未提供HTTP重试声明明细，不能推断声明尝试量。</p>;
 return <div className="http-attempt-preview"><p><b>HTTP节点声明尝试量：{show(value.total)}</b></p><p className="hint">仅按当前图、次数假设及“首次＋已启用节点重试”计算。不是实际HTTP请求次数、耗时或费用硬上限；不包含重定向、客户端／代理重试、代码或插件内部请求，0也不证明没有外部调用。</p>
  {!!value.nodes.length&&<details><summary>逐项HTTP尝试量依据</summary>{value.nodes.map(row=><div className="merge-conflict" key={JSON.stringify([row.scope_id,row.node_id])}><b>{row.scope_id?'容器 '+row.scope_id:'根流程'} · {row.node_id}</b><p>逻辑访问 {show(row.logical_visits)} × 每次最多 {row.attempts_per_visit} 次尝试 = {show(row.max_attempts)}</p><p className="hint">{row.retry_enabled?`已启用最多 ${row.max_retries} 次额外节点重试，声明间隔 ${row.retry_interval_ms} 毫秒。`:`节点重试关闭；保留的次数 ${row.max_retries} 和间隔 ${row.retry_interval_ms} 毫秒不增加尝试量。`}</p></div>)}</details>}
 </div>
}
