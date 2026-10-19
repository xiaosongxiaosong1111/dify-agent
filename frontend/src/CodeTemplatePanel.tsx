import {conversationSources} from './ConversationSources';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Plan={nodes:Node[];edges:unknown[];conversation_variables?:unknown};
type Row={node:Node;outer:number;inner?:number;parent?:string};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
const jsonText=(v:unknown,fallback:unknown)=>typeof v==='string'?v:JSON.stringify(v??fallback,null,2);
const parseDraft=(text:string):unknown=>{try{return JSON.parse(text)}catch{return text}};

export default function CodeTemplatePanel({plan,appType,disabled,onChange}:{plan:Plan|null;appType:string;disabled:boolean;onChange:(plan:Plan)=>void}){
 if(!plan)return null;
 const rows:Row[]=[];
 plan.nodes.forEach((node,outer)=>{
  if(['code','template-transform'].includes(node.type))rows.push({node,outer});
  if(['iteration','loop'].includes(node.type)&&object(node.config)&&Array.isArray(node.config.nodes)){
   node.config.nodes.slice(0,12).forEach((child,inner)=>{
    if(object(child)&&typeof child.id==='string'&&['code','template-transform'].includes(String(child.type)))rows.push({node:child as Node,outer,inner,parent:node.id});
   });
  }
 });
 if(!rows.length)return null;
 const update=(row:Row,field:string,value:unknown)=>{
  const next=structuredClone(plan),outer=next.nodes[row.outer];
  const node=row.inner===undefined?outer:(outer.config?.nodes as Node[])[row.inner];
  // Do not normalize an invalid advanced draft or update another same-ID node.
  if(!object(node.config))return;
  node.config[field]=value;onChange(next);
 };
 return <section className="code-template-panel configuration-proposal"><div className="listhead"><b>代码与模板节点编辑</b><small>只填写流程草稿</small></div><p className="hint">可直接修改代码或模板，包括单层迭代／循环中的业务节点。保存时由后台检查语法、输入引用和输出声明，之后须重新确认配置、构建及验证。这里不会执行代码、渲染模板或调用模型；循环保护代码不进入编辑器。</p>{rows.map(row=>{
  const {node,parent}=row,cfg=object(node.config)?node.config:null,code=node.type==='code',label=`节点 ${node.id}`;const cv=appType==='advanced-chat'?conversationSources(plan):[];
  return <details key={`${row.outer}-${row.inner??'root'}`} data-node-id={node.id}><summary>{node.title||node.id} · {code?'代码':'模板'}{parent?` · 容器 ${parent}`:''}</summary>{!cfg?<div className="callout amber">当前 config 不是对象，已保留原文；请在高级 JSON 中修正，不会自动补成空配置。</div>:<fieldset disabled={disabled}>
   {code?<><label className="field"><span>代码语言</span><select aria-label={`${label} 代码语言`} value={typeof cfg.code_language==='string'?cfg.code_language:''} onChange={e=>update(row,'code_language',e.target.value)}>{!['python3','javascript'].includes(String(cfg.code_language))&&<option value={typeof cfg.code_language==='string'?cfg.code_language:''}>未适配或未选择</option>}<option value="python3">Python 3</option><option value="javascript">JavaScript</option></select></label><p className="hint">切换语言只修改声明，不自动翻译或替换代码；务必同步核对代码内容。</p><label className="field"><span>完整代码</span><textarea aria-label={`${label} 完整代码`} spellCheck={false} rows={10} value={typeof cfg.code==='string'?cfg.code:''} onChange={e=>update(row,'code',e.target.value)}/></label>{cfg.code!==undefined&&typeof cfg.code!=='string'&&<p className="hint">代码原值不是文字；未编辑时原值保留，后台会拒绝无效结构。</p>}</>:<><label className="field"><span>完整模板</span><textarea aria-label={`${label} 完整模板`} spellCheck={false} rows={7} value={typeof cfg.template==='string'?cfg.template:''} onChange={e=>update(row,'template',e.target.value)}/></label><p className="hint">模板引用已绑定的变量名，固定输出为 output；不会在本机执行模板。</p></>}
   <label className="field"><span>输入变量绑定 JSON</span><textarea aria-label={`${label} 输入变量绑定`} spellCheck={false} value={jsonText(cfg.variables,[])} onChange={e=>update(row,'variables',parseDraft(e.target.value))}/></label><p className="hint">每项为 variable 和 value_selector（来源节点ID、输出字段）两个字段；修改别名需同步代码／模板。无效 JSON 保留文字待后台拒绝，不沿用旧值。</p>
   {Array.isArray(cfg.variables)&&cv.length>0&&cfg.variables.map((binding,i)=>object(binding)&&typeof binding.variable==='string'&&Object.keys(binding).every(key=>['variable','value_selector','value_type'].includes(key))?<label className="field" key={i}><span>输入 {binding.variable||i+1} 的会话只读来源{!code?` · 声明${String(binding.value_type??'string')}`:''}</span><select aria-label={`${label} 输入 ${i+1} 会话状态来源`} value={cv.filter(v=>code||v.type===(binding.value_type??'string')).some(v=>JSON.stringify(v.selector)===JSON.stringify(binding.value_selector))?JSON.stringify(binding.value_selector):''} onChange={e=>{const variables=structuredClone(cfg.variables) as Record<string,unknown>[];variables[i]={...variables[i],value_selector:JSON.parse(e.target.value)};update(row,'variables',variables)}}><option value="" disabled>主动选现有绑定，不改别名／代码／类型</option>{cv.filter(v=>code||v.type===(binding.value_type??'string')).map(v=><option key={JSON.stringify(v.selector)} value={JSON.stringify(v.selector)}>{v.label}</option>)}</select></label>:null)}
   {cv.length>0&&<p className="hint">候选只来自声明，不读取运行值。条件及模板声明类型须匹配；代码参数无类型声明时仍须核对逻辑／输出，选择来源不会生成代码或转换值。</p>}
   {code&&<><label className="field"><span>输出声明 JSON</span><textarea aria-label={`${label} 输出声明`} spellCheck={false} value={jsonText(cfg.outputs,{})} onChange={e=>update(row,'outputs',parseDraft(e.target.value))}/></label><p className="hint">每个返回字段须对应 outputs 中的名称和 type；不能只改声明来掩盖实际返回值不匹配，也不能删除业务输出使检查通过。</p></>}
  </fieldset>}</details>;
 })}</section>;
}
