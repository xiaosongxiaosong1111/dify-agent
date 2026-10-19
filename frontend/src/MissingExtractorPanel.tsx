import {useEffect,useMemo,useRef,useState} from 'react';
type Slot={start:string;missing:string;variable:string};
export type ExtractorDraft={taskId:string;revision:number;sourceText:string;text:string};
const object=(v:unknown):v is Record<string,any>=>!!v&&typeof v==='object'&&!Array.isArray(v);
export function extractionSlot(text:string,appType:string):Slot|null{
 if(appType!=='workflow'||text.length>2000000)return null;
 try{const p=JSON.parse(text);if(!object(p)||p.schema_version!==1||!Array.isArray(p.nodes)||p.nodes.length!==2||!p.nodes.every(object)||!Array.isArray(p.edges)||p.edges.length!==2||!p.edges.every(object))return null;
  const starts=p.nodes.filter((n:any)=>n.type==='start'),ends=p.nodes.filter((n:any)=>n.type==='end');if(starts.length!==1||ends.length!==1)return null;const start=starts[0],end=ends[0];
  if(typeof start.id!=='string'||!start.id||typeof end.id!=='string'||!end.id||start.id===end.id||!object(start.config)||!object(end.config))return null;
  if(!Array.isArray(end.config.outputs)||end.config.outputs.length!==1||!object(end.config.outputs[0]))return null;const selector=end.config.outputs[0].value_selector;if(!Array.isArray(selector)||selector.length!==2||typeof selector[0]!=='string'||!selector[0]||selector[1]!=='text'||[start.id,end.id].includes(selector[0]))return null;
  const expected=new Set([JSON.stringify([start.id,selector[0]]),JSON.stringify([selector[0],end.id])]);for(const edge of p.edges){if(typeof edge.source!=='string'||typeof edge.target!=='string'||!expected.delete(JSON.stringify([edge.source,edge.target])))return null}if(expected.size)return null;
  if(!Array.isArray(start.config.variables)||!start.config.variables.every(object))return null;const files=start.config.variables.filter((v:any)=>['file','file-list'].includes(v.type));if(files.length!==1||files[0].type!=='file'||files[0].required!==true||typeof files[0].variable!=='string'||!files[0].variable)return null;
  return {start:start.id,missing:selector[0],variable:files[0].variable};
 }catch{return null}
}
type Proposal={task_id:string;revision:number;request_nonce:string;plan_text:string;source_text_sha256:string;proposal_sha256:string;added_node_id:string;file_selector:string[];failure_policy:string;verification:string;original_nodes_preserved:boolean;original_edges_preserved:boolean;task_changed:boolean;network_requested:boolean;code_executed:boolean;platform_checked:boolean;business_verified:boolean};
const keys='added_node_id,business_verified,code_executed,failure_policy,file_selector,network_requested,original_edges_preserved,original_nodes_preserved,plan_text,platform_checked,proposal_sha256,request_nonce,revision,source_text_sha256,task_changed,task_id,verification';
const digest=async(text:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),b=>b.toString(16).padStart(2,'0')).join('');
export default function MissingExtractorPanel({taskId,revision,appType,text,disabled,onAdopt}:{taskId:string;revision:number;appType:string;text:string;disabled:boolean;onAdopt:(draft:ExtractorDraft)=>boolean}){
 const slot=useMemo(()=>extractionSlot(text,appType),[text,appType]);const [ack,setAck]=useState(false),[checking,setChecking]=useState(false),[error,setError]=useState(''),[proposal,setProposal]=useState<(Proposal&{sourceText:string})|null>(null);const epoch=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{epoch.current++;controller.current?.abort();setAck(false);setChecking(false);setError('');setProposal(null);return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,appType,text,disabled]);
 async function prepare(){if(!slot||!ack||disabled||checking)return;const ticket=++epoch.current,nonce=crypto.randomUUID(),abort=new AbortController();controller.current=abort;setChecking(true);setProposal(null);setError('');const timer=setTimeout(()=>abort.abort(),15000);
  try{const hash=await digest(text);if(ticket!==epoch.current)return;
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/missing-document-extractor`,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,plan_text:text,missing_node_id:slot.missing,input_variable:slot.variable,acknowledge_extraction:ack,request_nonce:nonce})});if(ticket!==epoch.current)return;if(!response.ok)throw Error();const v=await response.json() as Proposal;if(ticket!==epoch.current)return;
   if(!object(v)||Object.keys(v).sort().join(',')!==keys||v.task_id!==taskId||v.revision!==revision||v.request_nonce!==nonce||v.source_text_sha256!==hash||v.added_node_id!==slot.missing||JSON.stringify(v.file_selector)!==JSON.stringify([slot.start,slot.variable])||v.failure_policy!=='fail_if_missing'||v.verification!=='local_missing_extractor_proposal_only'||v.original_nodes_preserved!==true||v.original_edges_preserved!==true||['task_changed','network_requested','code_executed','platform_checked','business_verified'].some(k=>v[k as keyof Proposal]!==false)||typeof v.plan_text!=='string'||new TextEncoder().encode(v.plan_text).length>2000000||typeof v.proposal_sha256!=='string'||!/^[a-f0-9]{64}$/.test(v.proposal_sha256))throw Error();
   if(await digest(v.plan_text)!==v.proposal_sha256)throw Error();if(ticket!==epoch.current)return;
   const p=JSON.parse(v.plan_text);if(!object(p)||!Array.isArray(p.nodes)||p.nodes.length!==3)throw Error();const added=p.nodes.filter((n:any)=>object(n)&&n.id===slot.missing);if(added.length!==1||added[0].type!=='document-extractor'||!object(added[0].config)||Object.keys(added[0].config).sort().join(',')!=='empty_policy,input_type,variable_selector'||added[0].config.input_type!=='file'||added[0].config.empty_policy!=='fail_if_missing'||JSON.stringify(added[0].config.variable_selector)!==JSON.stringify(v.file_selector))throw Error();
   setProposal({...v,sourceText:text});
  }catch{if(ticket===epoch.current)setError('无法按这个单节点方案准备建议，或响应不匹配；请先检查原稿及支持范围，没有保存或部分修复。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setChecking(false)}
 }
 const visible=proposal&&proposal.task_id===taskId&&proposal.revision===revision&&proposal.sourceText===text&&ack&&!disabled?proposal:null;
 if(!slot)return null;
 return <section className="missing-extractor-panel configuration-proposal"><div className="listhead"><b>补充缺失的文档提取节点</b><small>本机建议 · 不保存</small></div><p>这份根流程引用了尚不存在的 {slot.missing}。建议补一个文档提取节点，读取开始变量 {slot.start}.{slot.variable}，保持原结束输出和连线。</p><p className="hint">仅适用于两个现有开始／结束节点、一条缺失节点路径和一个必填单文件。其它文字输入保留；不重建整图、不添加OCR或其它业务规则。文件缺失或解析失败终止，提取出的空文字不自动拒绝；实际格式、解析内容、外部服务和费用仍需独立确认。</p>
 <label className="missing-extractor-ack"><input type="checkbox" aria-label="确认补充文档提取节点及缺失失败政策" disabled={disabled} checked={ack} onChange={e=>{epoch.current++;controller.current?.abort();setChecking(false);setProposal(null);setError('');setAck(e.target.checked)}}/>我确认缺少的是文档提取节点，使用上述单文件和失败政策；这不是文件上传或运行批准。</label>
 <button className="secondary" disabled={disabled||checking||!ack} onClick={()=>void prepare()}>准备补充节点建议（不保存）</button>{checking&&<p role="status">正在本机核对补充建议...</p>}{error&&<p role="alert">{error}</p>}
 {visible&&<><p>新增 {visible.added_node_id} · 来源 {visible.file_selector.join('.')} · 缺失文件失败。原开始／结束节点和连线保持，已做计划结构检查，尚未运行。</p><details><summary>查看完整建议原文（未采用）</summary><pre>{visible.plan_text}</pre></details><button className="secondary" onClick={()=>onAdopt({taskId,revision,sourceText:text,text:visible.plan_text})}>将补充建议放入未保存草稿</button><p className="hint">采用仅更新当前草稿；正式保存、配置确认和真实试跑仍需分别完成。本次没有调用模型、上传文件或改变Dify应用。</p></>}
 </section>;
}
