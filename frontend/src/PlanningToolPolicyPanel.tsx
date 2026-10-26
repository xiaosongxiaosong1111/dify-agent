import {useEffect,useRef,useState} from 'react';
import {useOwnedActivity} from './useActivityOwnership';

type State={enabled:boolean;policy_revision:number;required_scope_version:number;current_source_token:string;ready:boolean;blocker:string|null;scope_note:string;history:unknown[];catalogue_token:string;catalogue:{[key:string]:unknown};provider:{name:string;model:string;base_url:string;protocol:string;configuration_revision?:number;pricing?:{input_per_million_usd:number;output_per_million_usd:number}}|null;round_limits:{max_cost_usd:number;max_minutes:number}};
async function request(path:string,body?:unknown):Promise<State>{const r=await fetch(`/api${path}`,body?{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);const v=await r.json();if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:`读取失败（HTTP ${r.status}）`);return v;}

export default function PlanningToolPolicyPanel({taskId,revision,providerRefreshKey,blocked,onDirty,onActivity:reportActivity,onSaved}:{taskId:string;revision:number;providerRefreshKey:string;blocked:boolean;onDirty:(v:boolean)=>void;onActivity:(v:string)=>void;onSaved:()=>void}){
 const [state,setState]=useState<State|null>(null),[enabled,setEnabled]=useState(false),[note,setNote]=useState(''),[ack,setAck]=useState(false),[dirty,setDirty]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState(''),[refresh,setRefresh]=useState(0);
 const source=JSON.stringify([taskId,revision,providerRefreshKey]),binding=useRef(source),mounted=useRef(true),serial=useRef(0),dirtyRef=useRef(false);binding.current=source;
 const onActivity=useOwnedActivity(reportActivity,source);
 const reset=(s:State)=>{setState(s);setEnabled(s.enabled);setNote('');setAck(false);setDirty(false);dirtyRef.current=false;onDirty(false)};
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false}},[]);
 useEffect(()=>{let live=true;const token=++serial.current;setState(null);setWorking(false);request(`/tasks/${taskId}/planning-tool-policy`).then(s=>{if(!live||token!==serial.current)return;if(dirtyRef.current){setState(s);setAck(false);setError('来源已刷新，草稿保留；请重新核对主模型、版本和规则范围。')}else{reset(s);setError('')}}).catch(e=>{if(live&&token===serial.current)setError(e.message)});return()=>{live=false}},[source,refresh,onDirty]);
 const edit=()=>{dirtyRef.current=true;setDirty(true);setAck(false);onDirty(true)};
 const save=async()=>{if(!state||working||blocked)return;const origin=source,token=++serial.current;const current=()=>mounted.current&&binding.current===origin&&serial.current===token;setWorking(true);setError('');onActivity('保存只读规则工具策略');try{const s=await request(`/tasks/${taskId}/planning-tool-policy`,{revision,policy_revision:state.policy_revision,scope_version:state.required_scope_version,enabled,source_token:enabled?state.current_source_token:null,acknowledge_scope:ack,note});if(current()){reset(s);onSaved()}}catch(e){if(current())setError(e instanceof Error?e.message:'保存失败')}finally{if(current())setWorking(false);onActivity('')}};
 return <details className="task-budget planning-tool-policy"><summary>规划只读规则工具 · {state?.enabled?'已明确启用':'默认关闭'}</summary>
  {error&&<div className="alert error" role="alert">{error}</div>}{!state&&<p className="hint">正在读取当前工具范围；不会调用模型。</p>}
  {state&&<><p className="hint">{state.scope_note}</p><p>固定主模型：{state.provider?`${state.provider.name} / ${state.provider.model}`:'未配置'} · {state.provider?.base_url||'地址未记录'} · {state.provider?.protocol||'协议未记录'} · 配置 v{state.provider?.configuration_revision??'未记录'}。</p>
   {state.provider?.pricing&&<p className="hint">参考单价：输入${state.provider.pricing.input_per_million_usd}／输出${state.provider.pricing.output_per_million_usd} 每百万tokens；非账单硬限。</p>}
   <p>只查询 Dify 1.17.1 的检索、条件、Python、文字LLM规则。最多2次模型HTTP、1次模型触发的注册查询；共用本轮 {state.round_limits.max_cost_usd} USD／{state.round_limits.max_minutes}分钟及任务累计账本。</p><p className="hint">先收到真实工具请求才查询。示例是合成资料，不能当作当前资源、人工批准或真实运行结果；这里只适配固定工具，不是任意工具执行器或原生Agent工具。</p>
   {state.blocker&&<div className="callout amber">{state.blocker}</div>}
   <fieldset disabled={blocked||working}><label className="budget-check"><input aria-label="启用规划只读规则工具" type="checkbox" checked={enabled} onChange={e=>{setEnabled(e.target.checked);edit()}}/>明确允许主规划模型按需查询一次节点规则</label>
    <label className="field"><span>工具策略变更原因</span><input aria-label="工具策略变更原因" maxLength={2000} value={note} onChange={e=>{setNote(e.target.value);edit()}}/></label>
    <label className="budget-check"><input aria-label="确认只读工具范围及共享费用" type="checkbox" checked={ack} onChange={e=>{setAck(e.target.checked);dirtyRef.current=true;setDirty(true);onDirty(true)}}/>我接受上述数据范围、最多两次模型请求及共享费用／时间；保存策略不会请求模型或执行资源</label>
    <div className="actions"><button className="primary" disabled={!dirty||!ack||!note.trim()||enabled&&!state.ready} onClick={()=>void save()}>保存只读工具策略</button><button className="secondary" disabled={!dirty} onClick={()=>{reset(state);setError('')}}>撤销工具策略草稿</button><button className="secondary" disabled={dirty} onClick={()=>setRefresh(v=>v+1)}>刷新只读工具状态</button></div>
   </fieldset><details><summary>工具范围确认历史 · {state.history.length} 条</summary><pre>{JSON.stringify(state.history,null,2)}</pre></details>
  </>}
 </details>;
}
