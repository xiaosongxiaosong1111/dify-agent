import {conversationSources} from './ConversationSources';
import {upstreamNodes,extractionSuccessAvailable} from './PlanSources';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:unknown[];conversation_variables?:unknown};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const parse=(text:string):unknown=>{try{return JSON.parse(text)}catch{return text}};
function choices(plan:Plan,id:string,mode:string){
 const rows:{selector:string[];label:string}[]=[];
 for(const node of upstreamNodes(plan,id)){
  const cfg=object(node.config)?node.config:{},add=(field:string)=>rows.push({selector:[node.id,field],label:`${node.title||node.id} · ${node.id}.${field}`});
  if(node.type==='start'){if(mode==='advanced-chat')rows.push({selector:['sys','query'],label:'当前对话输入 · sys.query'});if(Array.isArray(cfg.variables))for(const v of cfg.variables)if(object(v)&&typeof v.variable==='string')add(v.variable)}
  if(node.type==='llm'){for(const field of ['text','usage','finish_reason'])add(field);if(cfg.structured_output_enabled===true&&object(cfg.structured_output)&&object(cfg.structured_output.schema)&&cfg.structured_output.schema.type==='object')add('structured_output')}
  if(node.type==='question-classifier')for(const field of ['class_id','class_name','class_label','usage'])add(field);
  if(node.type==='parameter-extractor'){
   for(const field of ['__is_success','__usage'])add(field);
   if(extractionSuccessAvailable(plan,node,id)&&Array.isArray(cfg.parameters))for(const row of cfg.parameters)if(object(row)&&typeof row.name==='string')add(row.name);
  }
  if(node.type==='template-transform'||node.type==='variable-aggregator'||node.type==='iteration')add('output');
  if(node.type==='list-operator')add('result');
  if(node.type==='document-extractor')add('text');
  if(node.type==='knowledge-retrieval')add('result');
  if(node.type==='http-request')for(const field of ['status_code','body','headers','files'])add(field);
  if(node.type==='code'&&object(cfg.outputs))for(const field of Object.keys(cfg.outputs))add(field);
  if(node.type==='loop'&&Array.isArray(cfg.loop_variables))for(const v of cfg.loop_variables)if(object(v)&&typeof v.label==='string')add(v.label);
 }
 return rows;
}
export default function TerminalNodePanel({plan,appType,disabled,onChange}:{plan:Plan|null;appType:string;disabled:boolean;onChange:(plan:Plan)=>void}){
 if(!plan)return null;const nodes=plan.nodes.map((node,index)=>({node,index})).filter(({node})=>['end','answer'].includes(node.type));if(!nodes.length)return null;
 const update=(index:number,field:string,value:unknown)=>{const next=structuredClone(plan);if(!object(next.nodes[index].config))return;next.nodes[index].config![field]=value;onChange(next)};
 return <section className="terminal-node-panel configuration-proposal"><div className="listhead"><b>最终回答与返回字段</b><small>只填写流程草稿</small></div><p className="hint">逐个终点检查实际返回内容，尤其是默认分支与异常分支。只编辑当前节点，不改连线或其他终点；保存后须重新确认并按样例验证，不通过删字段或改输出类型掩盖业务问题。</p>{nodes.map(({node,index})=>{
  const cfg=object(node.config)?node.config:null,list=cfg?.outputs,candidates=choices(plan,node.id,appType),entry=candidates.filter(c=>c.selector[0]==='sys'||plan.nodes.some(n=>n.id===c.selector[0]&&n.type==='start')),cv=appType==='advanced-chat'?conversationSources(plan):[],label=`节点 ${node.id}`;
  const setRow=(i:number,key:string,value:unknown)=>{const rows=structuredClone(list) as Record<string,unknown>[];rows[i][key]=value;update(index,'outputs',rows)};
  return <details key={index} data-node-id={node.id}><summary>{node.title||node.id} · {node.type==='answer'?'对话回答':'任务返回'}</summary>{!cfg?<p className="hint">配置不是对象，原文保持，请用高级 JSON 核对。</p>:<fieldset disabled={disabled}>
   {node.type==='answer'?<><label className="field"><span>完整回答内容</span><textarea aria-label={`${label} 完整回答`} rows={7} spellCheck={false} value={typeof cfg.answer==='string'?cfg.answer:''} onChange={e=>update(index,'answer',e.target.value)}/></label><p className="hint">可写固定文字与 {'{{#来源节点.输出字段#}}'} 引用；请明确数组／对象的展示方式，不能把引用存在当成最终回答正确。</p>{entry.length>0&&<label className="field"><span>主动追加开始输入引用</span><select aria-label={`${label} 开始输入引用`} value="" disabled={typeof cfg.answer!=='string'} onChange={e=>{const selector=JSON.parse(e.target.value) as string[];update(index,'answer',String(cfg.answer)+(cfg.answer?'\n':'')+`{{#${selector[0]}.${selector[1]}#}}`)}}><option value="" disabled>选择输入，仅追加到当前回答</option>{entry.map(v=><option key={JSON.stringify(v.selector)} value={JSON.stringify(v.selector)}>{v.label}</option>)}</select></label>}{cv.length>0&&<label className="field"><span>主动追加会话只读状态引用</span><select aria-label={`${label} 会话状态引用`} value="" disabled={typeof cfg.answer!=='string'} onChange={e=>{const selector=JSON.parse(e.target.value) as string[];update(index,'answer',String(cfg.answer)+(cfg.answer?'\n':'')+`{{#${selector[0]}.${selector[1]}#}}`)}}><option value="" disabled>选择声明状态，仅追加到当前回答</option>{cv.map(v=><option key={JSON.stringify(v.selector)} value={JSON.stringify(v.selector)}>{v.label}</option>)}</select></label>}{cv.length>0&&<p className="hint">仅追加当前状态的展示引用，不改变状态值或其他分支。数值／真假按原生文本展示，不是业务类型转换；实际更新顺序及回答须试跑。</p>}{cfg.answer!==undefined&&typeof cfg.answer!=='string'&&<p className="hint">当前回答不是文字，未编辑时原值保留；后台会拒绝无效结构。</p>}</>:<>
    {Array.isArray(list)&&list.length<=64?list.map((row,i)=>{
     const simple=object(row)&&Object.keys(row).every(k=>['variable','value_selector','value_type'].includes(k))&&typeof row.variable==='string'&&Array.isArray(row.value_selector)&&row.value_selector.length===2&&row.value_selector.every(v=>typeof v==='string');
     if(!simple)return <p className="hint" key={i}>返回字段 {i+1} 无法安全简化，原值保持；请用完整 outputs JSON 修正。</p>;
     const r=row as Record<string,unknown>,selector=r.value_selector as string[],chosen=candidates.some(c=>JSON.stringify(c.selector)===JSON.stringify(selector))?JSON.stringify(selector):'',prefix=`${label} 返回 ${i+1}`;
     return <div className="condition-case" key={i}><label className="field"><span>返回字段名称</span><input aria-label={`${prefix} 名称`} value={r.variable as string} onChange={e=>setRow(i,'variable',e.target.value)}/></label><label className="field"><span>所有路径上游变量候选</span><select aria-label={`${prefix} 候选`} value={chosen} onChange={e=>setRow(i,'value_selector',JSON.parse(e.target.value))}><option disabled value="">选择候选（不自动选择）</option>{candidates.map((c,j)=><option value={JSON.stringify(c.selector)} key={j}>{c.label}</option>)}</select></label><label className="field"><span>实际来源节点 ID</span><input aria-label={`${prefix} 来源节点`} value={selector[0]} onChange={e=>setRow(i,'value_selector',[e.target.value,selector[1]])}/></label><label className="field"><span>实际输出字段</span><input aria-label={`${prefix} 输出字段`} value={selector[1]} onChange={e=>setRow(i,'value_selector',[selector[0],e.target.value])}/></label>{Object.hasOwn(r,'value_type')&&<p className="hint">原 value_type：{JSON.stringify(r.value_type)}（保持原文，不自动转换或脱敏；调整请用 outputs JSON）。</p>}<button className="secondary" onClick={()=>update(index,'outputs',list.filter((_,j)=>j!==i))} aria-label={`${prefix} 删除`}>删除这个返回字段</button></div>;
    }):<p className="hint">outputs 结构无效或超过 64 个简易显示上限，原文保持，不截断。</p>}
    {Array.isArray(list)&&list.length<64&&<button className="secondary" onClick={()=>update(index,'outputs',[...list,{variable:'',value_selector:['','']}])}>添加返回字段</button>}
    <label className="field"><span>完整 outputs JSON</span><textarea aria-label={`${label} 返回字段 JSON`} spellCheck={false} value={typeof list==='string'?list:JSON.stringify(list??[],null,2)} onChange={e=>update(index,'outputs',parse(e.target.value))}/></label><p className="hint">无效 JSON 保留文字，重复名称由后台拒绝，不静默覆盖、改名或删除。候选仅按草稿路径列出，实际字段是否有值仍须验证；引用不完整不能保存。</p>
   </>}
  </fieldset>}</details>;
 })}</section>;
}
