import {upstreamNodes} from './PlanSources';
import {declared} from './PlanDeclarations';
import {conversationSources} from './ConversationSources';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:unknown[];conversation_variables?:unknown};
type Row={node:Node;outer:number;inner?:number;parent?:string;edges:unknown[]};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
// Pinned scalar UI table plus runtime-native null spellings from Condition.
const operators:Record<string,string[]>={file:['exists','not exists'],'array[file]':['empty','not empty'],string:['contains','not contains','start with','end with','is','is not','empty','not empty','null','not null'],number:['=','≠','>','<','≥','≤','empty','not empty','null','not null'],boolean:['is','is not','null','not null']};
const names:Record<string,string>={exists:'存在文件（非null）','not exists':'未提供文件（null）',contains:'包含','not contains':'不包含','start with':'以此开头','end with':'以此结尾',is:'等于','is not':'不等于',empty:'为空','not empty':'不为空',null:'为空值（null）','not null':'非空值（not null）'};
const text=(v:unknown)=>typeof v==='string'?v:v===undefined?'':JSON.stringify(v);
const parse=(value:string):unknown=>{try{return JSON.parse(value)}catch{return value}};
const simple=(v:unknown)=>object(v)&&Object.keys(v).every(k=>['id','variable_selector','varType','comparison_operator','value'].includes(k))&&Array.isArray(v.variable_selector)&&v.variable_selector.length===2&&v.variable_selector.every(x=>typeof x==='string')&&typeof v.varType==='string'&&Object.hasOwn(operators,v.varType)&&Object.hasOwn(v,'value')&&(!object(v.value)&&!Array.isArray(v.value)||['empty','not empty','null','not null','exists','not exists'].includes(String(v.comparison_operator)));

export default function ConditionNodePanel({plan,appType,disabled,onChange}:{plan:Plan|null;appType:string;disabled:boolean;onChange:(plan:Plan)=>void}){
 if(!plan)return null;
 const rows:Row[]=[];
 plan.nodes.forEach((node,outer)=>{
  if(node.type==='if-else')rows.push({node,outer,edges:plan.edges});
  if(['iteration','loop'].includes(node.type)&&object(node.config)&&Array.isArray(node.config.nodes))node.config.nodes.slice(0,12).forEach((child,inner)=>{
   if(object(child)&&child.type==='if-else'&&typeof child.id==='string')rows.push({node:child as Node,outer,inner,parent:node.id,edges:Array.isArray(node.config!.edges)?node.config!.edges:[]});
  });
 });
 if(!rows.length)return null;
 const update=(row:Row,apply:(cfg:Record<string,unknown>)=>void)=>{
  const next=structuredClone(plan),outer=next.nodes[row.outer],node=row.inner===undefined?outer:(outer.config?.nodes as Node[])[row.inner];
  if(!object(node.config))return;apply(node.config);onChange(next);
 };
 const caseField=(row:Row,i:number,key:string,value:unknown)=>update(row,cfg=>{(cfg.cases as Record<string,unknown>[])[i][key]=value});
 const conditionField=(row:Row,i:number,j:number,key:string,value:unknown)=>update(row,cfg=>{(((cfg.cases as Record<string,unknown>[])[i].conditions) as Record<string,unknown>[])[j][key]=value});
 return <section className="condition-node-panel configuration-proposal"><div className="listhead"><b>条件分支配置</b><small>只填写流程草稿</small></div><p className="hint">逐个检查分支顺序、全部／任一条件和实际出口。修改只进入草稿，保存后需重新确认并验证边界输入、无匹配输入；不修改连接、分支标识或自动猜业务规则。新增／删除／重排分支及复杂条件仍用高级 JSON，并同时核对连接。</p>{rows.map(row=>{
  const {node,parent}=row,cfg=object(node.config)?node.config:null,cases=cfg?.cases;
  const target=(handle:string)=>row.edges.filter(e=>object(e)&&e.source===node.id&&(e.source_handle??'source')===handle).map(e=>String((e as Record<string,unknown>).target)).join('、')||'没有可核对出口';
  return <details key={`${row.outer}-${row.inner??'root'}`} data-node-id={node.id}><summary>{node.title||node.id} · 条件分支{parent?` · 容器 ${parent}`:''}</summary>{!cfg?<div className="callout amber">config 结构无效，原文保持，请在高级 JSON 核对。</div>:<fieldset disabled={disabled}>
   {Array.isArray(cases)&&cases.length<=32?cases.map((item,i)=>{
    if(!object(item))return <p className="hint" key={i}>分支 {i+1} 不是对象，不能安全简化；原值保持。</p>;
    const conditions=item.conditions,caseId=typeof item.case_id==='string'?item.case_id:'未声明',label=`节点 ${node.id} 分支 ${i+1}`;
    return <div className="condition-case" key={i}><b>分支 {i+1} · {caseId}</b><small>现有出口：{target(caseId)}</small><label className="field"><span>条件组合</span><select aria-label={`${label} 条件组合`} value={typeof item.logical_operator==='string'?item.logical_operator:''} onChange={e=>caseField(row,i,'logical_operator',e.target.value)}>{!['and','or'].includes(String(item.logical_operator))&&<option value={typeof item.logical_operator==='string'?item.logical_operator:''}>未适配或未选择</option>}<option value="and">全部条件满足（AND）</option><option value="or">任一条件满足（OR）</option></select></label>
    {Array.isArray(conditions)&&conditions.length<=64?conditions.map((condition,j)=>{
     if(!simple(condition))return <p className="hint" key={j}>条件 {j+1} 未适配简易编辑（文件属性／其他数组／嵌套／变量右值或结构无效），原文保持；请在本分支条件 JSON 中核对。</p>;
     const c=condition as Record<string,unknown>,selector=c.variable_selector as string[],type=c.varType as string,cv=appType==='advanced-chat'?conversationSources(plan,type):[],fv=['file','array[file]'].includes(type)&&row.inner===undefined?upstreamNodes(plan,row.node.id).flatMap(n=>declared(n).filter(v=>v.type===type&&(type==='array[file]'&&n.type==='http-request'&&v.field==='files'||n.type==='start'&&Array.isArray(n.config?.variables)&&n.config.variables.some(r=>object(r)&&r.variable===v.field&&r.type===(type==='file'?'file':'file-list')&&typeof r.required==='boolean'&&(type==='file'||r.required===true)))).map(v=>({selector:[n.id,v.field],label:`${n.title||n.id} · ${n.id}.${v.field}`}))):[],op=typeof c.comparison_operator==='string'?c.comparison_operator:'',prefix=`${label} 条件 ${j+1}`;
     return <div className="condition-item" key={j}><small>条件 {j+1}</small>{['file','array[file]'].includes(type)&&<><label className="field"><span>明确文件来源（不自动选择）</span><select aria-label={`${prefix} ${type==='file'?'单文件来源':'文件列表来源'}`} value={fv.some(v=>JSON.stringify(v.selector)===JSON.stringify(selector))?JSON.stringify(selector):''} onChange={e=>conditionField(row,i,j,'variable_selector',JSON.parse(e.target.value))}><option value="" disabled>请选择本作用域必经文件列表，原值保持</option>{fv.map(v=><option key={JSON.stringify(v.selector)} value={JSON.stringify(v.selector)}>{v.label}</option>)}</select></label><p className="hint">仅检查单文件是否存在或列表是否为空，不证明归属、远端有效期、格式或文字。缺失路径及两个出口须明确；可选单文件提取须受独立存在分支保护。仅五根节点可选单文件纯提取／明确说明图可另准备试跑方案并确认分支；其他条件文件图暂不试跑，不沿用普通文件试跑批准。</p></>}{cv.length>0&&<label className="field"><span>匹配类型的会话状态（只读）</span><select aria-label={`${prefix} 会话状态来源`} value={cv.some(v=>JSON.stringify(v.selector)===JSON.stringify(selector))?JSON.stringify(selector):''} onChange={e=>conditionField(row,i,j,'variable_selector',JSON.parse(e.target.value))}><option value="" disabled>主动选择，保留类型／比较值／运算</option>{cv.map(v=><option key={JSON.stringify(v.selector)} value={JSON.stringify(v.selector)}>{v.label}</option>)}</select></label>}<label className="field"><span>来源节点 ID</span><input aria-label={`${prefix} 来源节点`} value={selector[0]} onChange={e=>conditionField(row,i,j,'variable_selector',[e.target.value,selector[1]])}/></label><label className="field"><span>输出字段</span><input aria-label={`${prefix} 输出字段`} value={selector[1]} onChange={e=>conditionField(row,i,j,'variable_selector',[selector[0],e.target.value])}/></label><label className="field"><span>变量声明类型</span><select aria-label={`${prefix} 变量类型`} value={type} onChange={e=>conditionField(row,i,j,'varType',e.target.value)}><option value="string">文字（string）</option><option value="number">数值（number）</option><option value="boolean">布尔（boolean）</option><option value="file">单文件（file，仅存在检查）</option><option value="array[file]">文件列表（array[file]，仅空检查）</option></select></label><p className="hint">类型须与实际来源一致；切换类型保留原运算和值，请明确重新核对，不自动转换。</p><label className="field"><span>比较运算</span><select aria-label={`${prefix} 比较运算`} value={op} onChange={e=>conditionField(row,i,j,'comparison_operator',e.target.value)}>{!operators[type].includes(op)&&<option value={op}>当前运算需核对：{op||'未选择'}</option>}{operators[type].map(v=><option key={v} value={v}>{names[v]||v}</option>)}</select></label>
     {['empty','not empty','null','not null','exists','not exists'].includes(op)?<><p className="hint">此运算不需要右值；原 value 已保留，切回其他运算时需核对。文件条件仅接受空文本或 null，不会忽略旧比较值后通过。</p>{['file','array[file]'].includes(type)&&c.value!==''&&c.value!==null&&<button className="secondary" onClick={()=>conditionField(row,i,j,'value','')}>明确清空本条件比较值</button>}</>:type==='boolean'?<label className="field"><span>比较值</span><select aria-label={`${prefix} 比较值`} value={typeof c.value==='boolean'?String(c.value):'unknown'} onChange={e=>conditionField(row,i,j,'value',e.target.value==='true')}><option disabled value="unknown">当前不是明确布尔值，请选择</option><option value="true">true（真）</option><option value="false">false（假）</option></select></label>:<label className="field"><span>{type==='number'?'比较值（数值文本）':'比较值（文字）'}</span><input aria-label={`${prefix} 比较值`} value={text(c.value)} onChange={e=>conditionField(row,i,j,'value',e.target.value)}/></label>}
     </div>;
    }):<p className="hint">conditions 结构无效或超过 64 条简易显示上限；不截断原文，请用条件 JSON 核对。</p>}
    <details><summary>本分支条件 JSON</summary><label className="field"><span>完整 conditions 数组</span><textarea aria-label={`${label} 条件 JSON`} spellCheck={false} value={typeof conditions==='string'?conditions:JSON.stringify(conditions??[],null,2)} onChange={e=>caseField(row,i,'conditions',parse(e.target.value))}/></label><p className="hint">无效 JSON 保留文字待后台拒绝；不重置为旧条件，也不自动删除未适配字段。</p></details></div>;
   }):<p className="hint">cases 结构无效或超过 32 个简易显示上限；原值保持，请在高级 JSON 核对。</p>}
   <div className="callout">无条件匹配时的 false 出口：{target('false')}。请明确该路径的业务处理，并纳入验收样例。</div>
  </fieldset>}</details>;
 })}</section>;
}
