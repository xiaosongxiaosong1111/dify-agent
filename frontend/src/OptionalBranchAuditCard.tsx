type Audit={schema_version:1;state:'matched'|'different'|'insufficient';plan_id:string|null;plan_revision:number|null;expected_path:string|null;expected_node_ids:string[];observed_node_ids:string[];missing_node_ids:string[];unexpected_node_ids:string[];node_set_matches:boolean;message:string;note:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const ids=(v:unknown):v is string[]=>Array.isArray(v)&&v.length<=5&&v.every(x=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,200}$/.test(x))&&new Set(v).size===v.length;
const same=(a:string[],b:string[])=>a.length===b.length&&a.every(x=>b.includes(x));
function valid(v:unknown):v is Audit{
 if(!object(v)||v.schema_version!==1||!['matched','different','insufficient'].includes(String(v.state))||!(v.plan_id===null||typeof v.plan_id==='string'&&/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(v.plan_id))||!(v.plan_revision===null||Number.isInteger(v.plan_revision)&&Number(v.plan_revision)>0)||![null,'file_present','file_missing'].includes(v.expected_path as string|null)||!ids(v.expected_node_ids)||!ids(v.observed_node_ids)||!ids(v.missing_node_ids)||!ids(v.unexpected_node_ids)||typeof v.message!=='string'||typeof v.note!=='string'||v.verification!=='observed_optional_node_set_only'||v.execution_order_verified!==false||v.business_verified!==false||v.run_state_changed!==false||v.plan_changed!==false)return false;
 if(v.state==='insufficient')return v.node_set_matches===false;
 if(v.plan_id===null||v.plan_revision===null||v.expected_path===null||v.expected_node_ids.length!==(v.expected_path==='file_present'?4:3))return false;
 const expected=v.expected_node_ids,observed=v.observed_node_ids,missing=expected.filter(x=>!observed.includes(x)),unexpected=observed.filter(x=>!expected.includes(x)),matches=!missing.length&&!unexpected.length;
 return v.node_set_matches===matches&&v.state===(matches?'matched':'different')&&same(v.missing_node_ids,missing)&&same(v.unexpected_node_ids,unexpected);
}
export default function OptionalBranchAuditCard({value}:{value:unknown}){
 if(!valid(value))return <div className="callout amber optional-branch-audit">分支核对摘要不完整或版本未适配，不能据此证明预计选路；可主动重新读取原节点轨迹。</div>;
 return <div className={`callout optional-branch-audit ${value.state==='matched'?'':'amber'}`} style={{display:'block',overflowWrap:'anywhere'}}><b>原可选文件分支核对 · {value.state==='matched'?'采集节点集合一致':value.state==='different'?'采集节点集合有差异':'证据不足'}</b><p>{value.message}</p>{value.plan_id&&<small>原方案：{value.plan_id} · v{value.plan_revision}</small>}{value.expected_path&&<p>原预计分支：{value.expected_path==='file_present'?'有文件，提取后返回':'无文件，返回明确说明'}<br/>原预计节点：{value.expected_node_ids.join(' → ')}<br/>采集节点：{value.observed_node_ids.join('、')||'尚未完整核对'}</p>}{!!value.missing_node_ids.length&&<p>未观察到的预计节点：{value.missing_node_ids.join('、')}</p>}{!!value.unexpected_node_ids.length&&<p>预计分支外的节点：{value.unexpected_node_ids.join('、')}</p>}<p className="hint">{value.note}</p></div>;
}
