import {useEffect,useMemo,useRef,useState} from 'react';

type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Props={taskId:string;revision:number;appType:string;plan:{nodes:Node[]}|null;text:string;dependencies:string[];disabled:boolean;
 onAdopt:(draft:{taskId:string;revision:number;sourceText:string;text:string})=>boolean};
type Proposal={task_id:string;revision:number;request_nonce:string;node_id:string;dependency:string;input_selector:string[];plan_text:string;
 source_text_sha256:string;records_text_sha256:string;proposal_sha256:string;verification:string;only_selected_code_config_changed:boolean;
 task_changed:boolean;network_requested:boolean;code_executed:boolean;platform_checked:boolean;business_verified:boolean};
const digest=async(value:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(value))),v=>v.toString(16).padStart(2,'0')).join('');

export default function MockOrderTemplatePanel({taskId,revision,appType,plan,text,dependencies,disabled,onAdopt}:Props){
 const nodes=plan?.nodes.filter(node=>node.type==='code')||[];
 const sources=useMemo(()=>{
  const start=plan?.nodes.find(node=>node.type==='start');
  const variables=start?.config?.variables;
  const rows=Array.isArray(variables)?variables.filter((v):v is {variable:string;type:string}=>!!v&&typeof v==='object'&&typeof v.variable==='string'&&['text-input','paragraph'].includes(v.type)).map(v=>({value:JSON.stringify([start!.id,v.variable]),label:`${start!.id}.${v.variable}`})):[];
  for(const node of plan?.nodes||[]){
   const parameters=node.config?.parameters;
   if(node.type==='parameter-extractor'&&Array.isArray(parameters))for(const parameter of parameters){
    if(parameter&&typeof parameter==='object'&&parameter.type==='string'&&typeof parameter.name==='string'&&!parameter.name.startsWith('__'))rows.push({value:JSON.stringify([node.id,parameter.name]),label:`${node.id}.${parameter.name} · 提取文字（须在成功分支使用）`});
   }
  }
  if(appType==='advanced-chat')rows.push({value:JSON.stringify(['sys','query']),label:'sys.query · 整条消息直接作为订单号'});
  return rows;
 },[plan,appType]);
 const [nodeId,setNodeId]=useState(''),[selector,setSelector]=useState(''),[dependency,setDependency]=useState(''),[records,setRecords]=useState('');
 const [ack,setAck]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState(''),[reading,setReading]=useState(false),[readNotice,setReadNotice]=useState('');
 const [result,setResult]=useState<(Proposal&{sourceText:string;recordsText:string})|null>(null);
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),depKey=JSON.stringify(dependencies);
 useEffect(()=>{epoch.current++;controller.current?.abort();setWorking(false);setReading(false);setReadNotice('');setAck(false);setError('');setResult(null);return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,appType,text,disabled,depKey]);
 function edit(){epoch.current++;controller.current?.abort();setWorking(false);setReading(false);setReadNotice('');setAck(false);setError('');setResult(null)}
 const ready=!disabled&&ack&&nodes.some(node=>node.id===nodeId)&&sources.some(source=>source.value===selector)&&dependencies.includes(dependency)&&!!records.trim();
 async function readExisting(){
  if(disabled||working||!nodes.some(n=>n.id===nodeId)||!dependencies.includes(dependency))return;
  const ticket=++epoch.current,nonce=crypto.randomUUID(),abort=new AbortController();controller.current=abort;setWorking(true);setReading(true);setAck(false);setError('');setReadNotice('');setResult(null);
  const timer=setTimeout(()=>abort.abort(),15000);
  try{
   const sourceHash=await digest(text);if(ticket!==epoch.current)return;
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/mock-order-template/read`,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,plan_text:text,node_id:nodeId,dependency,request_nonce:nonce})});
   if(ticket!==epoch.current)return;const value=await response.json();
   if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'无法读取原模板，现有表单和计划保持。');
   const fields='business_verified,code_executed,dependency,input_selector,network_requested,node_id,platform_checked,record_count,records_text,records_text_sha256,request_nonce,revision,source_text_sha256,task_changed,task_id,verification';
   if(!value||Object.keys(value).sort().join(',')!==fields||value.task_id!==taskId||value.revision!==revision||value.request_nonce!==nonce||value.node_id!==nodeId||value.dependency!==dependency||value.source_text_sha256!==sourceHash||value.verification!=='read_exact_mock_order_template_v1'||['task_changed','network_requested','code_executed','platform_checked','business_verified'].some(k=>value[k]!==false)||typeof value.records_text!=='string'||new TextEncoder().encode(value.records_text).length>20000||await digest(value.records_text)!==value.records_text_sha256||!Array.isArray(value.input_selector)||!sources.some(s=>s.value===JSON.stringify(value.input_selector)))throw Error('读取结果与当前模板或输入来源不匹配，未填入表单。');
   const data=JSON.parse(value.records_text);if(!data||typeof data!=='object'||Array.isArray(data)||!Number.isInteger(value.record_count)||value.record_count<1||value.record_count>10||Object.keys(data).length!==value.record_count||Object.entries(data).some(([key,v])=>!/^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(key)||typeof v!=='string'||!v.trim()||Array.from(v).length>500))throw Error('原模板合成表结构无效，未填入表单。');
   if(ticket===epoch.current){setRecords(value.records_text);setSelector(JSON.stringify(value.input_selector));setReadNotice(`已载入${value.record_count}条合成样例及原订单号来源；仅替换本页表单，未更改流程。修改后请重新确认范围并准备建议。`)}
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'无法读取原模板，原内容保持。')}
  finally{clearTimeout(timer);if(ticket===epoch.current){setWorking(false);setReading(false)}}
 }
 async function prepare(){
  if(!ready||working)return;
  const ticket=++epoch.current,nonce=crypto.randomUUID(),abort=new AbortController();controller.current=abort;setWorking(true);setReading(false);setReadNotice('');setError('');setResult(null);
  const timer=setTimeout(()=>abort.abort(),15000);
  try{
   const [sourceHash,recordsHash]=await Promise.all([digest(text),digest(records)]);
   if(ticket!==epoch.current)return;
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/mock-order-template`,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,plan_text:text,node_id:nodeId,input_selector:JSON.parse(selector),records_text:records,dependency,acknowledge_mock:ack,request_nonce:nonce})});
   if(ticket!==epoch.current)return;
   if(!response.ok){const failure=await response.json();throw Error(typeof failure.detail==='string'?failure.detail:'模板预览请求未通过，请核对填写内容。')}
   const value=await response.json() as Proposal;
   const expected='business_verified,code_executed,dependency,input_selector,network_requested,node_id,only_selected_code_config_changed,plan_text,platform_checked,proposal_sha256,records_text_sha256,request_nonce,revision,source_text_sha256,task_changed,task_id,verification';
   if(!value||Object.keys(value).sort().join(',')!==expected||value.task_id!==taskId||value.revision!==revision||value.request_nonce!==nonce||value.node_id!==nodeId||value.dependency!==dependency||JSON.stringify(value.input_selector)!==selector||value.source_text_sha256!==sourceHash||value.records_text_sha256!==recordsHash||value.verification!=='local_mock_order_template'||value.only_selected_code_config_changed!==true||['task_changed','network_requested','code_executed','platform_checked','business_verified'].some(key=>value[key as keyof Proposal]!==false)||typeof value.plan_text!=='string'||new TextEncoder().encode(value.plan_text).length>2000000||await digest(value.plan_text)!==value.proposal_sha256)throw Error('模板响应与当前输入不匹配，未采用。');
   if(ticket===epoch.current)setResult({...value,sourceText:text,recordsText:records});
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'无法准备模板，原计划保持。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 const visible=result&&ready&&result.sourceText===text&&result.recordsText===records?result:null;
 return <section className="mock-order-template-panel configuration-proposal" aria-label="订单查询模拟模板">
  <div className="listhead"><b>订单查询模拟模板</b><small>本机建议 · 不保存</small></div>
  <p className="hint">只替换选中代码节点的完整代码、输入绑定及输出声明；其余节点和连接保持。输入须是明确订单号，可选已有参数提取节点的文字结果，本模板不新增或调用提取模型。固定输出result和status，明确标记模拟；引用或成功保护不兼容则拒绝建议。</p>
  {!dependencies.length&&<p className="callout amber">请先在配置页声明并保存模拟依赖；这里不自动接受模拟范围。</p>}
  <fieldset disabled={disabled||working}>
   <label className="field"><span>已声明模拟依赖</span><select aria-label="订单模板模拟依赖" value={dependency} onChange={e=>{edit();setDependency(e.target.value)}}><option value="">请明确选择</option>{dependencies.map((value,index)=><option key={index} value={value}>{value}</option>)}</select></label>
   <label className="field"><span>替换的代码节点</span><select aria-label="订单模板代码节点" value={nodeId} onChange={e=>{edit();setNodeId(e.target.value)}}><option value="">请明确选择根代码节点</option>{nodes.map(node=><option key={node.id} value={node.id}>{node.title||node.id} · {node.id}</option>)}</select></label>
   <button className="secondary" disabled={!nodes.some(n=>n.id===nodeId)||!dependencies.includes(dependency)||working} onClick={()=>void readExisting()}>载入选中模板的合成表（替换本表单）</button>
   <p className="hint">仅识别当前代码与声明完全匹配Sierra v1订单模板的内容；读取表中固定文字及原绑定，不执行代码、不保存计划，也不证明历史来源或运行通过。手改逻辑或声明不匹配时保留原稿，不猜测复原。</p>
   <label className="field"><span>订单号文字来源</span><select aria-label="订单模板订单号来源" value={selector} onChange={e=>{edit();setSelector(e.target.value)}}><option value="">请明确选择文字字段</option>{sources.map(source=><option key={source.value} value={source.value}>{source.label}</option>)}</select></label>
   <p className="hint">提取参数必须通过现有__is_success成功检查，且订单代码位于该成功路径；失败或公共汇合路径不能使用默认提取值。静态检查不证明真实提取质量，后续实际提取调用仍计费用并需原范围批准。</p>
   <p className="hint">输入会去除两端空白后按大小写精确匹配；空值返回缺少订单号，未知编号返回未命中，数字等其它类型报错。若入口字段必填，Sierra可能在派发前拒绝缺失输入；本模板不改变入口规则。</p>
   <label className="field"><span>合成订单表JSON</span><textarea aria-label="订单模板合成订单表" rows={5} spellCheck={false} maxLength={20000} value={records} placeholder={'例如：{"DEMO-001":"合成样例：已发货。"}'} onChange={e=>{edit();setRecords(e.target.value)}}/></label>
   <p className="hint">1—10个订单号，每个对应最多500字的固定说明。仅填合成样例，不填客户资料或凭据；不会请求订单服务。</p>
   <label><input type="checkbox" aria-label="接受订单模拟模板替换范围" checked={ack} onChange={e=>{edit();setAck(e.target.checked)}}/>我接受用上述合成数据替换选中节点的代码、绑定与输出；这不是实际订单接入或运行批准。</label>
  </fieldset>
  <button className="secondary" disabled={!ready||working} onClick={()=>void prepare()}>准备订单模拟模板（不保存）</button>
  {working&&<p role="status">{reading?'正在读取原模板合成表…':'正在核对单节点模板...'}</p>}{readNotice&&<p className="hint" role="status">{readNotice}</p>}{error&&<p role="alert">{error}</p>}
  {visible&&<><p>仅更新{visible.node_id}的代码配置，输出result/status；本机已做完整计划静态检查，尚未执行或发布。</p><details><summary>查看订单模板完整建议</summary><pre>{visible.plan_text}</pre></details>
   <button className="secondary" onClick={()=>{if(!onAdopt({taskId,revision,sourceText:text,text:visible.plan_text}))setError('任务或原稿已变化，未采用；请保留草稿后重新准备。')}}>将订单模板放入未保存草稿</button>
  </>}
 </section>;
}
