type Audit={schema_version:1;state:'observed_succeeded'|'observed_failed'|'insufficient';plan_id:string|null;plan_revision:number|null;guard_node_id:string|null;observed_status:string|null;guard_status_observed:boolean;execution_graph_matches_original:boolean;business_verified:false;run_state_changed:false;plan_changed:false;verification:string;message:string;note:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function valid(v:unknown):v is Audit{
 if(!object(v)||v.schema_version!==1||!['observed_succeeded','observed_failed','insufficient'].includes(String(v.state))||v.verification!=='observed_file_guard_node_status_only'||v.business_verified!==false||v.run_state_changed!==false||v.plan_changed!==false||typeof v.guard_status_observed!=='boolean'||typeof v.execution_graph_matches_original!=='boolean'||typeof v.message!=='string'||v.message.length>4000||typeof v.note!=='string'||v.note.length>4000||v.plan_id!==null&&(typeof v.plan_id!=='string'||!/^[a-f0-9-]{36}$/.test(v.plan_id))||v.plan_revision!==null&&(!Number.isSafeInteger(v.plan_revision)||Number(v.plan_revision)<1)||v.guard_node_id!==null&&(typeof v.guard_node_id!=='string'||!/^[A-Za-z0-9_-]{1,200}$/.test(v.guard_node_id)))return false;
 if(v.state==='insufficient')return v.guard_status_observed===false&&v.observed_status===null;
 return v.guard_status_observed===true&&v.execution_graph_matches_original===true&&v.plan_id!==null&&v.plan_revision!==null&&v.guard_node_id!==null&&(v.state==='observed_succeeded'?v.observed_status==='succeeded':['failed','exception'].includes(String(v.observed_status)));
}
export default function FileGuardAuditCard({value}:{value:unknown}){
 if(!valid(value))return <div className="file-guard-audit callout amber">文件Schema检查轨迹摘要不完整或版本未适配，未推定节点状态或业务通过。</div>;
 const labels={observed_succeeded:'轨迹记录节点成功',observed_failed:'轨迹记录节点失败',insufficient:'证据不足'};
 return <div className="file-guard-audit callout" style={{display:'block'}}><b>原文件Schema检查 · {labels[value.state]}</b><p>{value.message}</p>{value.plan_id&&<p>原方案：{value.plan_id} · v{value.plan_revision}</p>}{value.guard_node_id&&<p>检查节点：{value.guard_node_id}</p>}<p className="hint">原执行图：{value.execution_graph_matches_original?'与原批准完整图匹配':'尚未可靠匹配'}。{value.observed_status?`原节点状态：${value.observed_status}。`:'尚无可靠校验节点状态。'}</p><p className="hint">{value.note}</p></div>;
}
