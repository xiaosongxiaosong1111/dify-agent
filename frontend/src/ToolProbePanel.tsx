import {useOwnedActivity} from './useActivityOwnership';
import {useEffect,useRef,useState} from 'react';
type Receipt={id:string;state:string;ok:boolean;message:string;current_source:boolean;usage?:{total_tokens?:number};latency_ms?:number;estimated_cost_usd?:string;cost_basis?:string};
type Plan={source_token:string;configuration_revision:number;ready:boolean;reason:string;estimated_reservation_usd:string|null;max_output_tokens:number;timeout_seconds:number;note:string;latest_receipt:Receipt|null};
type Provider={id:string;base_url:string;model:string;protocol:string;configuration_revision?:number};
async function request<T>(url:string,body?:unknown):Promise<T>{const response=await fetch(url,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:`请求失败（HTTP ${response.status}）`);return value;}
export default function ToolProbePanel({provider,blocked,onActivity:reportActivity,onRefreshed}:{provider:Provider;blocked:boolean;onActivity:(label:string)=>void;onRefreshed:()=>Promise<void>}){
 const onActivity=useOwnedActivity(reportActivity,`${provider.id}:${provider.configuration_revision}`);
 const [plan,setPlan]=useState<Plan|null>(null),[receipt,setReceipt]=useState<Receipt|null>(null),[requestId,setRequestId]=useState(''),[ack,setAck]=useState(false),[attempted,setAttempted]=useState(false),[error,setError]=useState(''),[working,setWorking]=useState(false),active=useRef(false);
 const path=`/api/providers/${encodeURIComponent(provider.id)}`;
 useEffect(()=>{setPlan(null);setReceipt(null);setRequestId('');setAck(false);setAttempted(false);setError('')},[provider.id,provider.configuration_revision,provider.base_url,provider.model,provider.protocol]);
 const act=async(label:string,work:()=>Promise<void>)=>{if(active.current||blocked)return;active.current=true;setWorking(true);setError('');onActivity(label);try{await work()}catch(e){setError(e instanceof Error?e.message:'测试操作未完成')}finally{active.current=false;setWorking(false);onActivity('')}};
 const prepare=()=>void act('准备工具请求测试',async()=>{const value=await request<Plan>(path+'/tool-probe-plan');setPlan(value);setReceipt(value.latest_receipt);setRequestId(crypto.randomUUID());setAck(false);setAttempted(false)});
 const read=()=>void act('读取本机工具测试回执',async()=>{const id=attempted?requestId:receipt?.id||requestId;if(!id)return;setReceipt(await request<Receipt>(path+'/tool-probes/'+encodeURIComponent(id)))});
 const send=()=>void act('工具请求测试',async()=>{if(!plan||!ack||!requestId)return;setAttempted(true);try{setReceipt(await request<Receipt>(path+'/tool-probe',{request_id:requestId,source_token:plan.source_token,acknowledge_cost:ack}))}catch(e){try{setReceipt(await request<Receipt>(path+'/tool-probes/'+encodeURIComponent(requestId)))}catch{throw e}}finally{setAck(false);await onRefreshed()}});
 const sent=attempted||receipt?.id===requestId;
 return <section className="tool-probe-panel"><button className="secondary" disabled={blocked||working} onClick={prepare}>{plan?'重新准备工具请求测试':'准备工具请求测试（仅本机）'}</button>{error&&<div className="alert error" role="alert">{error}</div>}
  {plan&&<><p className="hint">只向此模型发送固定公开样例，检查一次工具请求的名称和参数。不会执行工具或继续Agent对话。</p><p>预留估算：{plan.estimated_reservation_usd===null?'未知':`${plan.estimated_reservation_usd} USD`} · 最多 {plan.max_output_tokens} 输出tokens / {plan.timeout_seconds}秒</p><p className="hint">{plan.note}</p>{!plan.ready&&<p className="callout amber">{plan.reason}</p>}
   {receipt&&<div className={`callout ${receipt.ok&&receipt.current_source?'':'amber'}`} role="status"><b>{!receipt.current_source?'历史配置的回执':receipt.state==='succeeded'?'本次工具请求符合约定':receipt.state==='running'?'本机记录：测试进行中':receipt.state==='unknown'?'测试终态未知':'本次工具请求未确认通过'}</b><p>{receipt.message}</p><small>{receipt.usage?.total_tokens===undefined?'用量未知':`${receipt.usage.total_tokens} tokens`}{receipt.latency_ms===undefined?'':` · ${receipt.latency_ms} ms`} · 回执 {receipt.id}</small>{receipt.cost_basis==='reserved_unknown_usage'&&<p className="hint">实际用量缺失，旧预留估算保留；不是已知账单或零费用。新测试会是另一次请求。</p>}</div>}
   <label className="tool-probe-ack"><input type="checkbox" aria-label="同意本次单次工具请求测试费用" checked={ack} disabled={blocked||working||!plan.ready||sent||receipt?.state==='running'} onChange={e=>setAck(e.target.checked)}/><span>我同意发送本次一次可能付费的模型请求，已知不会执行工具或自动重试。</span></label>
   <div className="actions"><button className="secondary" disabled={blocked||working||!plan.ready||!ack||sent||receipt?.state==='running'} onClick={send}>发送一次工具请求测试</button>{(receipt||requestId)&&<button className="secondary" disabled={blocked||working} onClick={read}>查询本机测试回执（不重发）</button>}</div>
  </>}
 </section>;
}
