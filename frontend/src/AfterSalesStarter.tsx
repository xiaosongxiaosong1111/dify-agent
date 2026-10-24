import {useEffect,useRef,useState} from 'react';
type Draft={taskId:string;revision:number;sourceText:string;text:string};
type Props={taskId:string;revision:number;appType:string;text:string;hasExisting:boolean;dependencies:string[];blocked:boolean;onAdopt:(draft:Draft)=>boolean};
const digest=async(s:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s))),x=>x.toString(16).padStart(2,'0')).join('');
export default function AfterSalesStarter({taskId,revision,appType,text,hasExisting,dependencies,blocked,onAdopt}:Props){
 const [dependency,setDependency]=useState(''),[records,setRecords]=useState(''),[noHit,setNoHit]=useState('知识库暂无相关信息，请联系人工客服。'),[missing,setMissing]=useState('请提供订单号，以便查询订单。'),[clarify,setClarify]=useState('请说明您要咨询售后资料还是查询订单。');
 const [ack,setAck]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState(''),[preview,setPreview]=useState<{text:string;note:string;stamp:string;warnings:string[]}|null>(null);
 const stamp=JSON.stringify([taskId,revision,appType,text,hasExisting,blocked,dependencies,dependency,records,noHit,missing,clarify]),current=useRef(stamp),epoch=useRef(0),controller=useRef<AbortController|null>(null);current.current=stamp;
 useEffect(()=>{epoch.current++;controller.current?.abort();setAck(false);setWorking(false);setError('');setPreview(null);return()=>{epoch.current++;controller.current?.abort()}},[stamp]);
 const occupied=hasExisting||!!text.trim(),ready=!blocked&&!occupied&&!working&&ack&&dependencies.includes(dependency)&&!!records.trim()&&[noHit,missing,clarify].every(s=>!!s.trim());
 async function prepare(){
  if(!ready)return;
  const ticket=++epoch.current,nonce=crypto.randomUUID(),abort=new AbortController();controller.current=abort;setWorking(true);setError('');setPreview(null);
  const timer=setTimeout(()=>abort.abort(),20000);
  try{
   const inputs={clarify_reply:clarify,dependency,missing_order_reply:missing,no_hit_reply:noHit,records_text:records,source_text:text};
   const inputHash=await digest(JSON.stringify(inputs));if(ticket!==epoch.current||current.current!==stamp)return;
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/after-sales-plan-preview`,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,request_nonce:nonce,...inputs,acknowledge_scope:ack})});
   if(ticket!==epoch.current||current.current!==stamp)return;const v=await r.json();
   if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:'无法准备完整售后草稿，原内容保持。');
   if(v.task_id!==taskId||v.revision!==revision||v.app_type!=='advanced-chat'||v.request_nonce!==nonce||v.input_sha256!==inputHash||v.verification!=='local_after_sales_template_preview'||v.node_count!==17||typeof v.note!=='string'||!v.note||!Array.isArray(v.warnings)||v.warnings.some((s:unknown)=>typeof s!=='string')||['task_changed','model_called','network_requested','code_executed','platform_checked','business_verified'].some(k=>v[k]!==false)||typeof v.plan_text!=='string'||new TextEncoder().encode(v.plan_text).length>2_000_000||await digest(v.plan_text)!==v.plan_sha256)throw Error('售后草稿响应与当前任务或输入不匹配，未采用。');
   const plan=JSON.parse(v.plan_text);if(plan?.schema_version!==1||!Array.isArray(plan.nodes)||plan.nodes.length!==17||!Array.isArray(plan.edges)||plan.edges.length!==16||new Set(plan.nodes.map((n:{id:string})=>n.id)).size!==17)throw Error('售后完整图结构无效，未采用。');
   if(ticket===epoch.current&&current.current===stamp)setPreview({text:v.plan_text,note:v.note,warnings:v.warnings,stamp});
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'售后草稿准备失败，未保存或重试。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 if(appType!=='advanced-chat')return null;
 const value=preview?.stamp===stamp?preview:null;
 return <details className="after-sales-starter configuration-proposal"><summary><b>售后问答与模拟订单分支草稿（Chatflow）</b></summary>
 <p className="hint">从空白准备17节点：诉求分类→资料检索/无命中回复，或订单号提取→成功保护→合成查询，提取失败追问；不明确诉求先澄清。复用已保存模型、知识库和检索参数。只是固定范围模板，不推断覆盖其它需求，也不验证模型效果或真实订单。</p>
 {occupied&&<p className="callout amber">已有编辑、流程或来源成果，草稿不会覆盖它们。</p>}
 {!dependencies.length&&<p className="hint">请先在配置页声明并保存订单模拟依赖，模型与知识库也须先明确保存。</p>}
 <fieldset disabled={blocked||occupied||working}>
 <label className="field"><span>已声明订单模拟依赖</span><select aria-label="售后草稿模拟依赖" value={dependency} onChange={e=>setDependency(e.target.value)}><option value="">请明确选择</option>{dependencies.map((s,i)=><option key={i} value={s}>{s}</option>)}</select></label>
 <label className="field"><span>合成订单表JSON</span><textarea aria-label="售后草稿合成订单表" rows={4} maxLength={20000} spellCheck={false} value={records} placeholder={'例如：{"DEMO-001":"合成样例：已发货。"}'} onChange={e=>setRecords(e.target.value)}/></label>
 <p className="hint">仅1—10个合成订单号及固定说明，不填客户资料或凭据。查询结果带“模拟订单查询，非真实订单”标记；真实订单接口仍待接入。</p>
 <label className="field"><span>资料无命中或依据不足的固定回复</span><textarea aria-label="售后草稿无命中回复" maxLength={500} value={noHit} onChange={e=>setNoHit(e.target.value)}/></label>
 <label className="field"><span>订单号提取失败的固定追问</span><textarea aria-label="售后草稿订单号追问" maxLength={500} value={missing} onChange={e=>setMissing(e.target.value)}/></label>
 <label className="field"><span>诉求不明确的固定澄清</span><textarea aria-label="售后草稿澄清回复" maxLength={500} value={clarify} onChange={e=>setClarify(e.target.value)}/></label>
 <label><input type="checkbox" aria-label="接受售后草稿范围" checked={ack} onChange={e=>setAck(e.target.checked)}/>我明确选择以上固定回复和合成订单范围，之后仍核对完整图及其未覆盖需求；不把本机草稿当真实运行批准。</label>
 </fieldset><button className="secondary" disabled={!ready} onClick={()=>void prepare()}>准备售后分支草稿（不调用模型）</button>
 {working&&<p role="status">正在本机核对完整草稿，尚未保存…</p>}{error&&<p role="alert">{error}</p>}
 {value&&<><p className="callout amber" style={{display:'block'}}>{value.note}</p><details><summary>查看售后完整节点与连接</summary><pre>{value.text}</pre></details><details><summary>静态检查提示（不证明业务通过）</summary>{value.warnings.map((s,i)=><p className="hint" key={i}>{s}</p>)}</details>
 <button className="secondary" disabled={!ack||blocked||occupied||working} onClick={()=>{if(!ack||blocked||occupied||current.current!==stamp)return;if(onAdopt({taskId,revision,sourceText:text,text:value.text})){setPreview(null);setAck(false)}else setError('任务或原稿已变化，未采用；请保留当前编辑。')}}>将售后分支放入未保存编辑器</button><p className="hint">仅填草稿；须后台校验保存、重新确认配置再构建。未来分类/提取/回答会用所选模型并可能收费，技术失败仍可终止；真实导入发布运行按原门禁。</p></>}
 </details>;
}
