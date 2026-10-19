import {upstreamNodes,extractionSuccessAvailable} from './PlanSources';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};type Plan={nodes:Node[];edges:unknown[]};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const shape=(v:unknown,keys:string[]):v is Record<string,unknown>=>object(v)&&Object.keys(v).length===keys.length&&keys.every(k=>Object.hasOwn(v,k));
const types=['array[string]','array[number]','array[boolean]'];
export function arrayCandidates(plan:Plan,target:string,kind:unknown){
 const result:{selector:string[];label:string}[]=[];
 for(const node of upstreamNodes(plan,target)){
  const cfg=node.config||{},add=(field:string,type:unknown)=>{if(types.includes(String(type))&&type===kind)result.push({selector:[node.id,field],label:`${node.title||node.id} · ${node.id}.${field}（${type}）`})};
  if(node.type==='code'&&object(cfg.outputs))for(const [field,schema] of Object.entries(cfg.outputs))if(object(schema))add(field,schema.type);
  if(node.type==='list-operator')add('result',cfg.input_type);
  if(node.type==='document-extractor')add('text','array[string]');
  if(node.type==='iteration'||node.type==='variable-aggregator')add('output',cfg.output_type);
  if(node.type==='parameter-extractor'&&extractionSuccessAvailable(plan,node,target)&&Array.isArray(cfg.parameters))for(const row of cfg.parameters)if(object(row)&&typeof row.name==='string')add(row.name,row.type);
 }
 return result;
}
const operators:Record<string,[string,string][]>={
 'array[string]':[['contains','包含'],['not contains','不包含'],['start with','开头是'],['end with','结尾是'],['is','相等'],['is not','不等'],['empty','为空'],['not empty','非空']],
 'array[number]':[['=','等于'],['≠','不等于'],['<','小于'],['>','大于'],['≥','大于等于'],['≤','小于等于']],
 'array[boolean]':[['is','等于'],['is not','不等于']],
};
export default function ListOperatorControls({plan,node,extraSources=[],onChange}:{plan:Plan;node:Node;extraSources?:{selector:string[];label:string}[];onChange:(field:string,value:unknown)=>void}){
 const cfg=node.config||{},prefix=`节点 ${node.id}`,sourceChoices=[...arrayCandidates(plan,node.id,cfg.input_type),...extraSources],source=JSON.stringify(cfg.variable),chosen=sourceChoices.some(c=>JSON.stringify(c.selector)===source)?source:'',filter=cfg.filter_by,order=cfg.order_by,extract=cfg.extract_by,limit=cfg.limit;
 const setField=(field:string,key:string,value:unknown)=>{if(object(cfg[field]))onChange(field,{...cfg[field], [key]:value})};
 const numeric=(value:string)=>/^-?\d+$/.test(value)&&Number.isSafeInteger(Number(value))?Number(value):value;
 const rows=object(filter)&&Array.isArray(filter.conditions)?filter.conditions:null;
 const rowEdit=(index:number,key:string,value:unknown)=>{if(!rows)return;const next=structuredClone(rows);if(object(next[index])){next[index][key]=value;setField('filter_by','conditions',next)}};
 return <div className="list-operator-controls"><label className="field"><span>类型一致、所有路径上游的数组候选</span><select aria-label={`${prefix} 数组来源候选`} value={chosen} onChange={e=>onChange('variable',JSON.parse(e.target.value))}><option disabled value="">明确选择来源（不自动选）</option>{sourceChoices.map((c,i)=><option key={i} value={JSON.stringify(c.selector)}>{c.label}</option>)}</select></label>{!chosen&&<p className="hint">当前来源没有对应的已声明、全路径可用候选，原值保持。核对类型、成功分支或完整 variable JSON，不会自动转换。</p>}
 {shape(filter,['enabled','conditions'])&&typeof filter.enabled==='boolean'&&rows&&<><label className="repair-ack"><input type="checkbox" aria-label={`${prefix} 启用筛选`} checked={filter.enabled} onChange={e=>setField('filter_by','enabled',e.target.checked)}/><span>启用筛选（多条件为 AND，关闭不删除条件）</span></label>{rows.length<=20&&rows.map((row,i)=>{
  if(!shape(row,['key','comparison_operator','value'])||row.key!==''||typeof row.comparison_operator!=='string')return <p className="hint" key={i}>条件 {i+1} 不能安全简化，原值保持，请用完整JSON核对。</p>;
  const options=operators[String(cfg.input_type)]||[],known=options.some(([op])=>op===row.comparison_operator),label=`${prefix} 筛选 ${i+1}`;
  return <div className="condition-case" key={i}><label className="field"><span>条件 {i+1} 比较方式</span><select aria-label={`${label} 运算`} value={known?row.comparison_operator:''} onChange={e=>rowEdit(i,'comparison_operator',e.target.value)}><option value="" disabled>{row.comparison_operator?`当前运算 ${row.comparison_operator} 未适配此类型`:'请选择运算'}</option>{options.map(([op,label])=><option key={op} value={op}>{label}</option>)}</select></label>{cfg.input_type==='array[boolean]'?<label className="field"><span>实际布尔值</span><select aria-label={`${label} 布尔值`} value={typeof row.value==='boolean'?String(row.value):''} onChange={e=>rowEdit(i,'value',e.target.value==='true')}><option value="" disabled>请选择 true 或 false（不转换文字值）</option><option value="true">true</option><option value="false">false</option></select></label>:typeof row.value==='string'?<label className="field"><span>{cfg.input_type==='array[number]'?'有限数字字面值（保留文字格式）':'文字字面值（空／非空运算须留空）'}</span><input aria-label={`${label} 字面值`} value={row.value} onChange={e=>rowEdit(i,'value',e.target.value)}/></label>:<p className="hint">右值无法安全简化，请用完整JSON核对，未自动改类型。</p>}<button className="secondary" aria-label={`${label} 删除`} onClick={()=>setField('filter_by','conditions',rows.filter((_,j)=>j!==i))}>删除此条件</button></div>;
 })}{rows.length<20&&<button className="secondary" onClick={()=>setField('filter_by','conditions',[...rows,{key:'',comparison_operator:'',value:''}])}>添加筛选条件</button>}</>}
 {shape(order,['enabled','key','value'])&&typeof order.enabled==='boolean'&&order.key===''&&typeof order.value==='string'&&<><label className="repair-ack"><input type="checkbox" aria-label={`${prefix} 启用排序`} checked={order.enabled} onChange={e=>setField('order_by','enabled',e.target.checked)}/><span>启用排序</span></label><label className="field"><span>排序方向（文字按字符、布尔 False 在 True 前）</span><select aria-label={`${prefix} 排序方向`} value={['asc','desc'].includes(order.value)?order.value:''} onChange={e=>setField('order_by','value',e.target.value)}><option disabled value="">方向未适配，原文保持</option><option value="asc">升序</option><option value="desc">降序</option></select></label></>}
 {shape(extract,['enabled','serial'])&&typeof extract.enabled==='boolean'&&typeof extract.serial==='string'&&<><label className="repair-ack"><input type="checkbox" aria-label={`${prefix} 启用序号提取`} checked={extract.enabled} onChange={e=>setField('extract_by','enabled',e.target.checked)}/><span>启用筛后序号提取（发生在排序之前）</span></label><label className="field"><span>筛后序号（1—10000，越界不能自动换首项）</span><input aria-label={`${prefix} 筛后序号`} inputMode="numeric" value={extract.serial} onChange={e=>setField('extract_by','serial',e.target.value)}/></label></>}
 {shape(limit,['enabled','size'])&&typeof limit.enabled==='boolean'&&(typeof limit.size==='number'||typeof limit.size==='string')&&<><label className="repair-ack"><input type="checkbox" aria-label={`${prefix} 启用数量截取`} checked={limit.enabled} onChange={e=>setField('limit','enabled',e.target.checked)}/><span>启用数量截取</span></label><label className="field"><span>最多保留数量（0—10000；0返回空数组）</span><input aria-label={`${prefix} 保留数量`} inputMode="numeric" value={String(limit.size)} onChange={e=>setField('limit','size',numeric(e.target.value))}/></label>{limit.size===-1&&<p className="hint">原生 -1 哨兵仅能保持关闭，启用前必须明确修改数量。</p>}</>}
 <p className="hint">表单和完整JSON编辑的是同一份未确认草稿。类型切换不改原条件，开启不清除旧值；后台仍会拒绝不兼容设置。没有操作不会自动改计划。</p></div>;
}
