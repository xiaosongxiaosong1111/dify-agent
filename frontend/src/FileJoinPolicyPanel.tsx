import {useEffect,useRef,useState} from 'react';
import JoinPolicyFields,{validJoinPolicy,type JoinPolicy} from './JoinPolicyFields';
type Plan={nodes:{id:string;type:string;title?:string;config?:Record<string,unknown>}[];edges:unknown[]};
type Scope={task_id:string;revision:number;node_id:string;request_nonce:string;source_plan_sha256:string;policy:JoinPolicy;file_variable:string};
type Proposal=Scope&{previous_policy:JoinPolicy;candidate_plan_sha256:string;updated_nodes:number;plan:Plan};
const hash=(s:unknown):s is string=>typeof s==='string'&&/^[a-f0-9]{64}$/.test(s);
const same=(a:JoinPolicy,b:JoinPolicy)=>Object.keys(a).every(k=>a[k as keyof JoinPolicy]===b[k as keyof JoinPolicy]);
export default function FileJoinPolicyPanel({taskId,revision,plan,appType,disabled,onChange}:{taskId:string;revision:number;plan:Plan|null;appType:string;disabled:boolean;onChange:(p:Plan)=>void}){
 const [chosen,setChosen]=useState(''),[baseline,setBaseline]=useState<Scope|null>(null),[selected,setSelected]=useState<JoinPolicy|null>(null),[proposal,setProposal]=useState<Proposal|null>(null),[working,setWorking]=useState(false),[error,setError]=useState('');
 const stamp=JSON.stringify(plan),epoch=useRef(0),policyStamp=JSON.stringify(selected),latest=useRef('');
 const context=JSON.stringify([taskId,revision,stamp,chosen,disabled,policyStamp]);latest.current=context;
 useEffect(()=>{epoch.current++;setBaseline(null);setSelected(null);setProposal(null);setWorking(false);setError('');return()=>{epoch.current++}},[taskId,revision,stamp,chosen,disabled]);
 useEffect(()=>{setProposal(null)},[policyStamp]);
 const rows=plan?.nodes.filter(n=>n.type==='code'&&typeof n.config?.code==='string'&&n.config.code.startsWith('# Sierra TXT join guard v1\n'))??[];
 if(appType!=='workflow'||!plan||!rows.length)return null;
 const validScope=(v:Scope,nonce:string)=>v&&v.task_id===taskId&&v.revision===revision&&v.node_id===chosen&&v.request_nonce===nonce&&hash(v.source_plan_sha256)&&validJoinPolicy(v.policy)&&typeof v.file_variable==='string';
 const request=async(kind:'inspect'|'preview')=>{
  if(disabled||working||!rows.some(n=>n.id===chosen)||kind==='preview'&&(!baseline||!selected||same(baseline.policy,selected)))return;
  const ticket=++epoch.current,nonce=crypto.randomUUID(),snapshot=context;setWorking(true);setProposal(null);setError('');
  try{
   const response=await fetch(`/api/tasks/${taskId}/file-join-policy/${kind}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,plan,node_id:chosen,request_nonce:nonce,...(kind==='preview'?{policy:selected}:{})})}),value=await response.json();
   if(ticket!==epoch.current||latest.current!==snapshot)return;
   if(!response.ok)throw Error(typeof value?.detail==='string'?value.detail:`拼接政策处理失败（HTTP ${response.status}）`);
   if(!validScope(value,nonce)||value.verification!=='local_policy_static_only'||value.task_changed!==false||value.network_requested!==false||value.model_called!==false)throw Error('拼接政策回执与当前任务／节点不符，未采用。');
   if(kind==='inspect'){setBaseline(value);setSelected(value.policy)}
   else{
    if(!baseline||!selected||value.source_plan_sha256!==baseline.source_plan_sha256||!validJoinPolicy(value.previous_policy)||!same(value.previous_policy,baseline.policy)||!same(value.policy,selected)||!hash(value.candidate_plan_sha256)||value.changed_edges!==0||value.added_nodes!==0||value.updated_nodes!==1+Number(baseline.policy.max_files!==selected.max_files)||!value.plan||!Array.isArray(value.plan.nodes)||!Array.isArray(value.plan.edges))throw Error('政策变更内容或原草稿不符，未采用。');
    // The server owns recipe validation; the browser also refuses unrelated edits.
    const expected=structuredClone(plan),original=expected.nodes.find(n=>n.id===chosen),replacement=value.plan.nodes.find((n:{id:string})=>n.id===chosen);
    if(!original?.config||typeof replacement?.config?.code!=='string'||!replacement.config.code.startsWith('# Sierra TXT join guard v1\n'))throw Error('拼接代码目标不完整，未采用。');
    original.config.code=replacement.config.code;
    const bindings=original.config.variables as {value_selector:string[]}[],extract=expected.nodes.find(n=>n.id===bindings[0].value_selector[0]),selector=extract?.config?.variable_selector as string[],start=expected.nodes.find(n=>n.id===selector?.[0]);
    const variables=start?.config?.variables as {variable:string;max_length?:number}[],field=variables?.find(v=>v.variable===baseline.file_variable);
    if(!field)throw Error('开始文件变量无法核对，未采用。');field.max_length=selected.max_files;
    if(JSON.stringify(expected)!==JSON.stringify(value.plan))throw Error('候选还改变了政策之外的字段，未采用。');
    setProposal(value);
   }
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'政策处理未完成，原内容保持。')}
  finally{if(ticket===epoch.current)setWorking(false)}
 };
 return <section className="configuration-proposal file-join-policy-panel"><div className="listhead"><b>调整已有文字拼接政策</b><small>本机核对 → 预览 → 采纳未保存草稿</small></div><p className="hint">只更新完整原样的规范模板。手改代码、输入绑定或前置路径不覆盖；不执行代码、模型或Dify。读取不更改任何内容。</p><label className="field"><span>明确选择拼接节点</span><select aria-label="拼接政策目标节点" disabled={disabled||working} value={chosen} onChange={e=>setChosen(e.target.value)}><option value="">请选择</option>{rows.map(n=><option key={n.id} value={n.id}>{n.title||n.id} · {n.id}</option>)}</select></label><button className="secondary" disabled={disabled||working||!chosen} onClick={()=>void request('inspect')}>读取当前规范拼接政策</button>{baseline&&<><p className="hint">当前绑定文件变量：{baseline.file_variable}。下方从已核对的原政策开始编辑；尚未修改草稿。</p><details><summary>当前原政策完整值</summary><pre>{JSON.stringify(baseline.policy,null,2)}</pre></details><JoinPolicyFields key={baseline.source_plan_sha256+chosen} initial={baseline.policy} disabled={disabled||working} onChange={setSelected}/><button className="secondary" disabled={disabled||working||!selected||same(baseline.policy,selected)} onClick={()=>void request('preview')}>预览拼接政策变更</button></>}{working&&<p role="status">正在本机核对政策，原草稿保持。</p>}{error&&<p className="error" role="alert">{error}</p>}{proposal&&<div className="file-join-policy-proposal"><b>政策变更预览 · 尚未采纳</b><p>将更新拼接节点代码{proposal.updated_nodes===2?`，同时将开始变量 ${proposal.file_variable} 的最大文件数由 ${proposal.previous_policy.max_files} 改为 ${proposal.policy.max_files}`:'；开始变量文件数保持'}。节点ID、标题、提示词、模型、连接及其他字段保留。</p><pre>{JSON.stringify({原政策:proposal.previous_policy,新政策:proposal.policy},null,2)}</pre><details><summary>查看完整候选流程与规范代码</summary><pre>{JSON.stringify(proposal.plan,null,2)}</pre></details><p className="hint">采纳只填未保存草稿。须再保存、确认配置、生成新DSL，原成果／上传／运行方案不自动刷新，旧运行批准不能继续沿用。静态核对不是平台或业务验收。</p><button className="secondary" disabled={disabled||working} onClick={()=>{if(proposal.task_id===taskId&&proposal.revision===revision&&selected&&same(proposal.policy,selected)){const value=proposal.plan;epoch.current++;setProposal(null);onChange(value)}}}>采纳拼接政策到未保存草稿</button></div>}</section>
}
