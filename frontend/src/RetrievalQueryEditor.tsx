import {upstreamNodes,extractionSuccessAvailable} from './PlanSources';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:unknown[]};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);

export function querySources(plan:Plan,target:string,appType?:string){
 const upstream=upstreamNodes(plan,target),choices:{selector:string[];label:string}[]=[];
 for(const source of upstream){
  const c=object(source.config)?source.config:{},add=(field:string)=>choices.push({selector:[source.id,field],label:`${source.title||source.id} · ${source.id}.${field}`});
  if(source.type==='start'&&appType==='advanced-chat')choices.push({selector:['sys','query'],label:'当前对话输入 · sys.query'});
  if(source.type==='start'&&appType!=='advanced-chat'&&Array.isArray(c.variables))for(const variable of c.variables)if(object(variable)&&typeof variable.variable==='string'&&['text-input','paragraph','select'].includes(String(variable.type??'text-input')))add(variable.variable);
  if(source.type==='llm')add('text');
  if(source.type==='question-classifier')for(const field of ['class_id','class_name','class_label'])add(field);
  if(source.type==='parameter-extractor'&&extractionSuccessAvailable(plan,source,target)&&Array.isArray(c.parameters))for(const row of c.parameters)if(object(row)&&row.type==='string'&&typeof row.name==='string')add(row.name);
  if(source.type==='template-transform')add('output');
  if(source.type==='http-request')add('body');
  if(source.type==='variable-aggregator'&&c.output_type==='string')add('output');
  if(source.type==='code'&&object(c.outputs))for(const [name,schema] of Object.entries(c.outputs))if(object(schema)&&schema.type==='string')add(name);
  if(source.type==='loop'&&Array.isArray(c.loop_variables))for(const variable of c.loop_variables)if(object(variable)&&variable.var_type==='string'&&typeof variable.label==='string')add(variable.label);
 }
 return choices;
}

export default function RetrievalQueryEditor({plan,node,appType,disabled,onChange,extraSources=[],requireExplicit=false}:{plan:Plan;node:Node;appType?:string;disabled:boolean;onChange:(value:unknown,remove?:boolean)=>void;extraSources?:{selector:string[];label:string}[];requireExplicit?:boolean}){
 const cfg=node.config||{},selector=cfg.query_variable_selector,independent=selector!==undefined&&selector!==null,start=plan.nodes.filter(n=>n.type==='start'),defaultSelector=appType==='advanced-chat'?['sys','query']:start.length===1?[start[0].id,'query']:null,valid=Array.isArray(selector)&&selector.length===2&&selector.every(v=>typeof v==='string');
 const choices=[...querySources(plan,node.id,appType),...extraSources];
 const encoded=valid&&choices.some(c=>JSON.stringify(c.selector)===JSON.stringify(selector))?JSON.stringify(selector):'',label=`节点 ${node.id}`;
 return <div className="retrieval-query-editor"><label className="field"><span>检索问题来源</span><select aria-label={`${label} 问题来源方式`} value={independent?'node':'default'} disabled={disabled} onChange={e=>onChange(e.target.value==='node'?['','']:undefined,e.target.value==='default')}><option value="default" disabled={requireExplicit}>{requireExplicit?"容器必须明确本项／本轮问题，当前原值保持":"使用应用默认问题输入"}</option><option value="node">明确选择节点问题来源</option></select></label>{!independent?requireExplicit?<p className="hint">容器检索必须明确本项／本轮文字来源，请主动选择。不自动选item、状态或应用query；未明确来源不能保存。</p>:<p className="hint">默认实际引用：{defaultSelector?.join('.')||'当前草稿没有唯一 start，无法核对默认来源'}。Workflow 默认是实际 start 的 query 字段；若已改用其他输入名，需要明确选择。继承不表示字段已存在，保存仍会检查。</p>:<>
  <label className="field"><span>所有路径上游的文字变量候选</span><select aria-label={`${label} 问题变量候选`} value={encoded} disabled={disabled} onChange={e=>onChange(JSON.parse(e.target.value))}><option disabled value="">{choices.length?'选择候选（不自动选择）':'没有可安全列出的上游文字候选'}</option>{choices.map((choice,i)=><option key={i} value={JSON.stringify(choice.selector)}>{choice.label}</option>)}</select></label><p className="hint">可选择原始问题、LLM 改写文字、模板或明确声明的文字输出。候选只基于草稿声明与路径，不证明实际输出是有效问题；不会调用模型、查询知识库或自动转换数组／对象。</p>
  {valid?<><label className="field"><span>实际问题来源节点 ID</span><input aria-label={`${label} 问题来源节点`} value={selector[0]} disabled={disabled} onChange={e=>onChange([e.target.value,selector[1]])}/></label><label className="field"><span>实际问题输出字段</span><input aria-label={`${label} 问题输出字段`} value={selector[1]} disabled={disabled} onChange={e=>onChange([selector[0],e.target.value])}/></label></>:<p className="hint">当前 selector 结构无法简化，原值保持；请用 JSON 修正，不退回默认输入。</p>}
  <label className="field"><span>完整问题 selector JSON</span><textarea aria-label={`${label} 问题 selector`} disabled={disabled} spellCheck={false} value={typeof selector==='string'?selector:JSON.stringify(selector,null,2)} onChange={e=>{let value:unknown=e.target.value;try{value=JSON.parse(e.target.value)}catch{}onChange(value)}}/></label>
 </>}</div>;
}
