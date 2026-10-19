import {useEffect,useRef,useState} from 'react';
type Draft={taskId:string;revision:number;sourceText:string;text:string};
type Preview={text:string;note:string;stamp:string;token:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
export function validLinearPlanText(text:unknown,appType:string):text is string{
 if(typeof text!=='string'||text.length>2_000_000)return false;
 try{const p=JSON.parse(text);if(!object(p)||p.schema_version!==1||Object.keys(p).sort().join('|')!=='edges|nodes|schema_version'||!Array.isArray(p.nodes)||!Array.isArray(p.edges))return false;
  const end=appType==='workflow'?'end':appType==='advanced-chat'?'answer':null;if(!end)return false;
  const nodes=p.nodes,edges=p.edges,kinds=nodes.map(n=>object(n)?n.type:null),expected=nodes.length===4?['start','knowledge-retrieval','llm',end]:['start','llm',end];
  if(JSON.stringify(kinds)!==JSON.stringify(expected)||edges.length!==nodes.length-1)return false;
  const ids=new Set();for(const n of nodes){if(!object(n)||typeof n.id!=='string'||!n.id||ids.has(n.id)||!object(n.config))return false;ids.add(n.id)}
  return edges.every((e,i)=>object(e)&&Object.keys(e).sort().join('|')==='source|target'&&e.source===nodes[i].id&&e.target===nodes[i+1].id);
 }catch{return false}
}
export default function LinearPlanStarter({taskId,revision,appType,text,hasExisting,blocked,onAdopt}:{taskId:string;revision:number;appType:string;text:string;hasExisting:boolean;blocked:boolean;onAdopt:(draft:Draft)=>boolean}){
 const stamp=JSON.stringify([taskId,revision,appType,text,hasExisting,blocked]),current=useRef(stamp),epoch=useRef(0),controller=useRef<AbortController|null>(null);current.current=stamp;
 const [preview,setPreview]=useState<Preview|null>(null),[ack,setAck]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState('');
 useEffect(()=>{epoch.current++;controller.current?.abort();setPreview(null);setAck(false);setWorking(false);setError('');return()=>{epoch.current++;controller.current?.abort()}},[stamp]);
 if(!['workflow','advanced-chat'].includes(appType))return null;
 const occupied=hasExisting||!!text.trim(),value=preview?.stamp===stamp?preview:null;
 const prepare=async()=>{
  if(blocked||occupied||working)return;const ticket=++epoch.current,nonce=crypto.randomUUID(),abort=new AbortController();controller.current=abort;setWorking(true);setError('');setPreview(null);setAck(false);const timer=setTimeout(()=>abort.abort(),15000);
  try{const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/linear-plan-preview`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,request_nonce:nonce}),signal:abort.signal});if(ticket!==epoch.current||current.current!==stamp)return;if(!r.ok)throw Error();const v:unknown=await r.json();if(ticket!==epoch.current||current.current!==stamp)return;
   if(!object(v)||v.task_id!==taskId||v.revision!==revision||v.app_type!==appType||v.request_nonce!==nonce||v.verification!=='local_linear_template_preview'||['task_changed','model_called','network_requested','business_verified'].some(k=>v[k]!==false)||typeof v.preview_token!=='string'||!/^[a-f0-9]{64}$/.test(v.preview_token)||typeof v.note!=='string'||!v.note||v.note.length>1200||!validLinearPlanText(v.plan_text,appType))throw Error();
   setPreview({text:v.plan_text,note:v.note,stamp,token:v.preview_token});
  }catch{if(ticket===epoch.current)setError('无法准备可信的基础草稿；请核对当前配置与任务后主动重试，未覆盖或保存内容。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 };
 return <details className="configuration-proposal linear-plan-starter"><summary><b>仅需简单线性流程时：明确准备基础草稿</b></summary><p className="hint">有业务分支、无命中转人工、循环或接口要求时，请先使用本页“请求模型生成流程建议”并复核完整图。基础模板只把需求写入提示词，不能代替这些节点。</p>{occupied&&<p className="hint">当前已有流程、编辑内容或来源成果，基础草稿不会覆盖它们。</p>}<button className="secondary" disabled={blocked||occupied||working} onClick={()=>void prepare()}>查看基础线性草稿（不调用模型）</button>{working&&<p role="status">正在本机准备完整草稿，尚未保存…</p>}{error&&<p role="alert">{error}</p>}{value&&<><p className="callout amber" style={{display:'block'}}>{value.note}</p><details><summary>查看完整节点与连接</summary><pre>{value.text}</pre></details><label className="repair-ack"><input type="checkbox" aria-label="确认基础线性草稿范围" checked={ack} disabled={blocked||working||occupied} onChange={e=>setAck(e.target.checked)}/><span>我已查看节点与连接，确认本次只需这些线性步骤；需求文字不代表分支、失败处理或业务覆盖已实现。</span></label><button className="secondary" disabled={!ack||blocked||occupied||working} onClick={()=>{if(!ack||!value||current.current!==stamp||occupied||blocked)return;if(onAdopt({taskId,revision,sourceText:text,text:value.text})){setPreview(null);setAck(false)}else setError('当前任务或编辑已变化，未放入基础草稿。')}}>将已核对的基础流程放入未保存编辑器</button><p className="hint">只填编辑器；仍须后台校验保存、确认配置，再生成DSL。未创建Dify资源或调用模型，未证明业务通过。</p></>}</details>;
}
