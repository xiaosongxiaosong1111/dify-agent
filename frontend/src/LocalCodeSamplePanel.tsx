import {useEffect,useRef,useState} from 'react';
import {useOwnedActivity} from './useActivityOwnership';
type Node={id:string;type:string;title?:string;config?:Record<string,unknown>};
type Result={status:string;output_json?:string;error_category?:string;cleanup_verified:boolean};
type Row={schema_version:number;id:string;task_id:string;revision:number;node_id:string;state:string;review_token:string;code_sha256:string;input_text_sha256:string;image_id:string;profile:string;limits:Record<string,unknown>;verification:string;business_verified:boolean;dify_sandbox_verified:boolean;task_changed:boolean;result?:Result;note:string};
const LIMITS={"wall_seconds":3,"cpu_seconds":4,"host_wait_seconds":8,"memory_bytes":134217728,"cpus":1,"pids":32,"code_bytes":32768,"input_bytes":65536,"output_bytes":32768,"printed_bytes":4096,"network":"none","host_mounts":false,"read_only_root":true,"user":"65534:65534","capabilities":"drop_all","no_new_privileges":true,"image_pulled":false};
const IMAGE='sha256:ceede5b903afaa20348f7ad80ebf847379dc56d886a99b9ec6a08913dacd7732';
const sha=async(text:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(x=>x.toString(16).padStart(2,'0')).join('');
const label:Record<string,string>={prepared:'已准备，未执行',executing:'已派发，等待原回执',passed:'本机样例返回且顶层输出合同通过',failed:'本机样例未通过',unknown:'本机状态待核对，不能据此重跑'};
const resultLabel:Record<string,string>={timeout:'计算超过时限',output_limit:'输出超过范围',code_error:'代码计算异常',invalid_output:'返回不是受支持的普通JSON',output_mismatch:'返回与顶层输出声明不匹配',technical_error:'本机隔离执行异常',unknown:'清理或执行状态未确认'};
export default function LocalCodeSamplePanel({taskId,revision,plan,sourceScope,blocked,onActivity}:{taskId:string;revision:number;plan:{nodes:Node[]}|null|undefined;sourceScope:string;blocked:boolean;onActivity?:(value:boolean,owner?:object)=>void}){
 const [nodeId,setNodeId]=useState(''),[input,setInput]=useState('{}'),[proposal,setProposal]=useState<Row|null>(null),[result,setResult]=useState<Row|null>(null),[ack,setAck]=useState(false),[sent,setSent]=useState(false),[working,setWorking]=useState(''),[error,setError]=useState('');
 const choices=(plan?.nodes||[]).filter(n=>n.type==='code'&&n.config?.code_language==='python3'),selected=choices.find(n=>n.id===nodeId),code=typeof selected?.config?.code==='string'?selected.config.code:'';
 const source=JSON.stringify([taskId,revision,plan,nodeId,input,sourceScope]),current=useRef(source);current.current=source;
 const blockedRef=useRef(blocked);blockedRef.current=blocked;
 const active=useRef(false),ticket=useRef(0),report=useOwnedActivity(onActivity,taskId+':'+revision);
 useEffect(()=>{ticket.current++;active.current=false;setProposal(null);setResult(null);setAck(false);setSent(false);setError('');setWorking('');return()=>{ticket.current++;report(false)}},[source,blocked,report]);
 function basic(row:Row){return row&&row.schema_version===1&&row.task_id===taskId&&row.revision===revision&&row.node_id===nodeId&&typeof row.id==='string'&&/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(row.id)&&/^[a-f0-9]{64}$/.test(row.code_sha256)&&/^[a-f0-9]{64}$/.test(row.input_text_sha256)&&typeof row.review_token==='string'&&!!row.review_token&&row.image_id===IMAGE&&row.profile==='pure-python-v1'&&row.verification==='local_sample_only'&&row.business_verified===false&&row.dify_sandbox_verified===false&&row.task_changed===false&&!!label[row.state]}
 async function act(kind:'prepare'|'execute'|'history'){
  if(blockedRef.current||active.current||working||!selected)return;
  if(kind==='prepare'&&sent)return;
  if(kind==='execute'&&(sent||!proposal||!ack||proposal.state!=='prepared'))return;
  active.current=true;const stamp=source,id=++ticket.current;setWorking(kind);setError('');report(true);
  if(kind==='execute'){setAck(false);setSent(true);setResult(null)}
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),kind==='execute'?60000:15000);
  const still=()=>ticket.current===id&&current.current===stamp&&!blockedRef.current;
  try{
   const payload=kind==='prepare'?{revision,node_id:nodeId,input_text:input}:kind==='execute'?{revision,proposal_id:proposal!.id,review_token:proposal!.review_token,input_text:input,acknowledge_limits:true}:null;
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/code-samples${kind==='history'?'':'/'+kind}`,{...(payload?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}:{cache:'no-store' as RequestCache}),signal:controller.signal});
   const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'本机样例请求未完成，请核对原回执。');
   if(!still())return;
   const [codeHash,inputHash]=await Promise.all([sha(code),sha(input)]);if(!still())return;
   const rows=kind==='history'?(Array.isArray(value.records)?value.records:[]):[value];
   const row=rows.find((r:Row)=>(kind!=='history'||!proposal||r.id===proposal.id)&&basic(r)&&r.code_sha256===codeHash&&r.input_text_sha256===inputHash);
   if(!row)throw Error(kind==='history'?'没有匹配当前代码与输入原文的保存回执，未采用其他节点/修订成绩。':'回执来源或验证范围不匹配，未采用结果。');
   if(!row.limits||Object.keys(row.limits).length!==Object.keys(LIMITS).length||Object.entries(LIMITS).some(([key,value])=>row.limits[key]!==value))throw Error('回执资源边界不匹配，未提供执行确认。');
   if(kind==='execute'&&row.id!==proposal!.id)throw Error('执行回执不属于此次准备方案。');
   if(row.result&&(!resultLabel[row.result.status]&&row.result.status!=='passed'||typeof row.result.cleanup_verified!=='boolean'||row.result.output_json!==undefined&&(typeof row.result.output_json!=='string'||new TextEncoder().encode(row.result.output_json).length>32768)))throw Error('本机结果协议不完整，未显示不确定成绩。');
   setProposal(row);setResult(kind==='prepare'?null:row);setAck(false);setSent(['executing','unknown'].includes(row.state));
  }catch(e){if(still())setError(e instanceof Error&&e.name!=='AbortError'?e.message:'读取中断或超时；已派发本机工作可能仍在完成/清理，请只读核对原回执，不自动重发。')}
  finally{clearTimeout(timer);if(ticket.current===id){active.current=false;setWorking('');report(false)}}
 }
 return <details className="local-code-sample configuration-proposal"><summary>本机受限Python样例 · 不调用模型或Dify</summary>
  <p className="hint">仅已保存的Workflow根Python同步main纯计算。开放限定math/json；不支持文件、网络、系统导入、私有属性、动态入口或嵌套节点。输入是你明确填写的JSON参数，不读取真实上游。不会改变原确认、构建或平台成绩。</p>
  <fieldset disabled={blocked||!!working}>
   <label className="field"><span>根Python代码节点</span><select aria-label="本机样例代码节点" value={nodeId} onChange={e=>setNodeId(e.target.value)}><option value="">请明确选择已保存节点</option>{choices.map(n=><option value={n.id} key={n.id}>{n.title||n.id} · {n.id}</option>)}</select></label>
   {!choices.length&&<p className="hint">当前没有可选的已保存根Python节点；不会把编辑草稿、JavaScript或容器内节点转换后执行。</p>}
   {selected&&<><small>参数别名：{Array.isArray(selected.config?.variables)?selected.config.variables.map((v:Record<string,unknown>)=>String(v.variable)).join('、'):'声明待核对'}</small><details><summary>核对保存代码全文</summary><pre style={{whiteSpace:'pre-wrap',maxHeight:250,overflow:'auto'}}>{code}</pre></details></>}
   <label className="field"><span>独立样例参数JSON原文</span><textarea aria-label="本机样例参数JSON" rows={5} spellCheck={false} value={input} onChange={e=>setInput(e.target.value)}/></label>
   <div className="actions"><button className="secondary" disabled={!selected||sent} onClick={()=>void act('prepare')}>准备本机样例方案</button><button className="secondary" disabled={!selected} onClick={()=>void act('history')}>只读核对本机样例回执</button></div>
   {proposal&&<div className="callout" style={{display:'block'}}><b>{sent&&proposal.state==='prepared'?'执行已请求，请只读核对保存回执':label[proposal.state]}</b><p>固定已安装镜像 {proposal.image_id.slice(0,20)}；非root、只读根文件系统、无网络及宿主挂载、capabilities全部移除。1 CPU／128MiB／32进程，计算3秒、CPU硬限4秒、宿主等待8秒；准备和清理另有控制超时。输出32KiB，超限不截成成功。</p><p>代码摘要 {proposal.code_sha256.slice(0,12)} · 输入原文 {proposal.input_text_sha256.slice(0,12)}</p>{proposal.state==='prepared'&&!sent&&<><label className="repair-ack"><input aria-label="确认本机代码样例范围" type="checkbox" checked={ack} onChange={e=>setAck(e.target.checked)}/>已核对代码、输入和本机隔离范围；不作为目标Dify或业务通过。</label><button className="primary" disabled={!ack} onClick={()=>void act('execute')}>仅执行一次本机样例</button></>}</div>}
  </fieldset>
  {working&&<p role="status">{working==='execute'?'正在执行本机隔离样例并核对清理…':'正在读取/准备本机样例…'} 切换或新编辑后不采用旧回执，已派发工作仍可能完成。</p>}
  {error&&<div role="alert" className="callout amber">{error}</div>}
  {result&&<div className="callout" style={{display:'block'}}><strong>{label[result.state]}</strong>{result.result&&<><p>{resultLabel[result.result.status]||'仅顶层JSON输出合同通过'}{result.result.error_category?' · '+result.result.error_category:''}</p>{result.result.output_json!==undefined&&<pre style={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{result.result.output_json}</pre>}<p>{result.result.cleanup_verified?'本次临时容器已核对清理。':`清理未确认；保留原回执，本次预期容器sierra-code-${result.id}，不要据此重跑。`}</p></>}<p>本机样例证据，不代表目标Sandbox、完整流程、业务规则或新修订通过。</p></div>}
 </details>;
}
