import {useOwnedActivity} from './useActivityOwnership';
import {useEffect, useState} from 'react';
import type {TestCase} from './AcceptancePanel';

type Item={id:string;category:string;purpose:string;source:{field:string;quote:string};node_ids:string[];case:Omit<TestCase,'id'>};
type State={contract?:{source?:{kind:string;semantics?:unknown}}|null;generation_route?:{role:string;provider:{name:string;model:string}|null;blocker:string|null;upgrade?:{enabled:boolean;main_provider:{name:string;model:string}|null;max_model_http_requests:number}};record:{id:string;status:string;proposal_token:string;generation_origin?:{provider_id:string;model:string;routing?:{selected_role:string;policy_revision:number;final_role?:string}}|null;candidate:{items:Item[];open_issues:{question:string;recommendation:string}[];notes:string}}|null;can_adopt:boolean;stale:boolean;blocker:string|null;scope_note:string;history:unknown[]};
const category:Record<string,string>={normal:'正常场景',branch:'关键分支',exception:'异常场景',conversation:'多轮对话'};
const fields:Record<string,string>={goal:'业务目标',audience:'目标用户',input:'输入内容',output:'期望输出',rules:'业务规则',knowledge:'资料与依赖',exceptions:'异常处理',tests:'验收场景'};
async function request<T>(path:string,body?:unknown):Promise<T>{
 const r=await fetch(`/api${path}`,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:undefined);
 let v;try{v=await r.json()}catch{throw Error(`接口未返回可读取结果（HTTP ${r.status}），请检查服务状态。`)}
 if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:`请求失败（HTTP ${r.status}）`);return v;
}
export default function CaseProposalPanel({task,routingRefresh,blocked,onDirty,onActivity:reportActivity,onUpdated,onDiscuss}:{task:{id:string;revision:number;requirements_confirmed:boolean;status:string;plan_stale?:boolean};routingRefresh:string;blocked:boolean;onDirty:(v:boolean)=>void;onActivity:(v:string)=>void;onUpdated:(v:unknown)=>void;onDiscuss:(v:string)=>void}){
 const onActivity=useOwnedActivity(reportActivity,`${task.id}:${task.revision}`);
 const [state,setState]=useState<State|null>(null),[selected,setSelected]=useState<string[]>([]),[ack,setAck]=useState(false),[working,setWorking]=useState(''),[error,setError]=useState('');
 const reset=()=>{setSelected([]);setAck(false);onDirty(false)};
 const load=async()=>{const v=await request<State>(`/tasks/${task.id}/case-proposal`);setState(v);return v};
 useEffect(()=>{let live=true;reset();request<State>(`/tasks/${task.id}/case-proposal`).then(v=>{if(live){setState(v);setError('')}}).catch(e=>live&&setError(e.message));return()=>{live=false}},[task.id,task.revision,routingRefresh,onDirty]);
 useEffect(()=>{if(!working&&task.status!=='planning')return;let live=true;const timer=setInterval(()=>void request<State>(`/tasks/${task.id}/case-proposal`).then(v=>live&&setState(v)).catch(e=>live&&setError(e.message)),1500);return()=>{live=false;clearInterval(timer)}},[task.id,task.status,working]);
 const action=async(kind:'generate'|'adopt')=>{
  setWorking(kind);onActivity(kind==='generate'?'请求模型生成验收样例建议':'采纳验收样例建议');setError('');
  try{
   const body=kind==='generate'?{revision:task.revision}:{revision:task.revision,proposal_id:state?.record?.id,proposal_token:state?.record?.proposal_token,item_ids:selected,acknowledge_review:ack};
   const t=await request(`/tasks/${task.id}/case-proposal/${kind}`,body);reset();await load();onUpdated(t);
  }catch(e){setError(e instanceof Error?e.message:'请求失败');try{await load();if(kind==='generate')onUpdated(await request(`/tasks/${task.id}`))}catch{}}
  finally{setWorking('');onActivity('')}
 };
 const disabled=blocked||!!working,editing=!!selected.length||ack,record=state?.record;
 return <section className="configuration-proposal case-proposal">
  <div className="paneltitle"><span><b>验收样例建议</b><small>按需求与流程建议 · 逐项选择 · 保留已有样例</small></span></div>
  {error&&<div className="alert error" role="alert">{error}</div>}
  {state&&<>
   <p className="hint">{state.scope_note}</p>{state.generation_route&&<div className="callout">本次建议模型：{state.generation_route.role==='light'?'已确认轻量服务':'默认任务主模型'} · {state.generation_route.provider?`${state.generation_route.provider.name} / ${state.generation_route.provider.model}`:'未能确定'}。{state.generation_route.blocker||(state.generation_route.upgrade?.enabled?`已独立启用限定JSON格式失败升级：固定主模型 ${state.generation_route.upgrade.main_provider?.name||'未固定'} / ${state.generation_route.upgrade.main_provider?.model||'未知'}，本次共最多2次调用，共用轮次/累计费用与时间，未知或业务问题不升级。`:'可在任务上方“验收建议模型路由”核对，默认失败不会自动换模型。')}</div>}<p className="hint">请求建议会将已确认需求、当前配置／流程、最终保留 DSL 的实际条件／代码／提示词／循环状态声明及初始值／赋值绑定、模型／选库／连接摘要、已有样例及覆盖清单发送给已配置的搭建助手模型，并计入任务预算。不会读取凭据存储中的 Key 或密码加入提示词。不要在需求或样例里填写密钥。</p>
   <button className="primary" disabled={disabled||editing||!task.requirements_confirmed||task.plan_stale||!!state.blocker||!!state.generation_route?.blocker} onClick={()=>void action('generate')}>请求 Sierra 建议验收样例</button>
   {(!task.requirements_confirmed||task.plan_stale)&&<p className="hint">请先确认需求并复核保存流程，再生成样例建议。</p>}{state.blocker&&<p className="callout amber">{state.blocker}</p>}
   {state.contract?.source?.kind==='preserved_dsl'&&<details className="case-semantic-preview"><summary>本次最终保留 DSL 的验收字段摘要（请求建议时发送）</summary><p className="hint">包含当前条件、代码、提示词及模型／选库标识和连接、循环状态声明／初始值及赋值绑定；未知字段只列名称，不发送其值。摘要不能代替真实运行或全面业务理解；过大或未适配时不截断后继续。</p><pre>{JSON.stringify(state.contract.source.semantics,null,2)}</pre></details>}
   {record&&<>
    <p className="hint">本候选生成来源：{record.generation_origin?`${record.generation_origin.model} · ${record.generation_origin.routing?.final_role==='main_upgrade'?'单次升级主模型':record.generation_origin.routing?.selected_role==='light'?'轻量服务':'任务主模型'} · 策略版本 ${record.generation_origin.routing?.policy_revision??'未记录'}`:'历史来源未记录，不猜测模型'}。更改当前路由不会改写已有候选的来源。</p>
    <div className={`callout ${state.stale||record.candidate.open_issues.length?'amber':''}`}>{record.status==='adopted'?'所选样例已追加保存；请在样例编辑器复核，并重新确认需求、流程和配置。':state.stale?'建议已过期，请按当前需求和流程重新生成。':record.candidate.open_issues.length?'仍有待决定的检查规则，暂不能采纳。':'样例建议已生成，现有样例尚未改变。'}<p>{record.candidate.notes}</p></div>
    <fieldset disabled={disabled||state.stale||record.status!=='proposed'}>
     {record.candidate.items.map(item=><article className="configuration-diff" key={item.id}>
      <label className="configuration-ack"><input type="checkbox" aria-label={`选择样例：${item.case.name}`} checked={selected.includes(item.id)} onChange={e=>{const next=e.target.checked?[...selected,item.id]:selected.filter(id=>id!==item.id);setSelected(next);setAck(false);onDirty(next.length>0)}}/><b>{item.case.name} · {category[item.category]}</b></label>
      <p>检查目的：{item.purpose}</p><p>来源：{fields[item.source.field]||item.source.field} · “{item.source.quote}”</p>{!!item.node_ids.length&&<p>关联节点：{item.node_ids.join('、')}（仅为建议关联，尚未证明触发）</p>}
      <div className="configuration-values"><div><small>首轮输入</small><pre>{JSON.stringify(item.case.input,null,2)}</pre></div><div><small>检查规则 · {item.case.expectation.mode==='manual'?'需要人工复核':'只检查所声明规则'}</small><pre>{JSON.stringify(item.case.expectation,null,2)}</pre></div></div>
      {!!item.case.followups?.length&&<details><summary>后续 {item.case.followups.length} 轮的输入与逐轮预期</summary><pre>{JSON.stringify(item.case.followups,null,2)}</pre></details>}
      <button className="secondary" disabled={editing} onClick={()=>onDiscuss(`请讨论验收样例“${item.case.name}”的输入与检查标准，说明正常、异常或多轮情况下怎样判断。我尚未采纳，不要把建议算作试跑通过。`)}>讨论检查标准</button>
     </article>)}
    </fieldset>
    {record.candidate.open_issues.map((issue,i)=><div className="configuration-issue" key={i}><b>{issue.question}</b><p>{issue.recommendation}</p><button className="secondary" disabled={disabled||editing} onClick={()=>onDiscuss(`请讨论验收缺口“${issue.question}”，推荐方案为“${issue.recommendation}”。明确可判断的预期与限制，未确认前不要省略需求。`)}>讨论验收缺口</button></div>)}
    {record.status==='proposed'&&<fieldset disabled={disabled}>
     <p className="hint">已选择 {selected.length} / {record.candidate.items.length} 个候选。仅追加所选样例；未选择候选不代表取消对应业务需求。采纳后可在样例编辑器修改输入与预期。</p>
     <label className="configuration-ack"><input type="checkbox" checked={ack} onChange={e=>{setAck(e.target.checked);onDirty(e.target.checked||selected.length>0)}}/>我已核对所选输入与检查标准；建议和节点关联不代表试跑通过或完整业务覆盖。</label>
     <div className="actions"><button className="primary" disabled={!state.can_adopt||!selected.length||!ack} onClick={()=>void action('adopt')}>追加所选验收样例</button><button className="secondary" disabled={!editing} onClick={reset}>撤销样例选择</button></div>
    </fieldset>}
   </>}
   {!!state.history.length&&<details><summary>样例建议历史 · {state.history.length} 条</summary><pre>{JSON.stringify(state.history,null,2)}</pre></details>}
  </>}
 </section>;
}
