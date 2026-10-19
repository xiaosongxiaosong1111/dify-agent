import type {StructuredFileOutput} from './FileStructuredOutput';
export type StrictFileGuard={node_id:string;source_node_id:string;input_variable:string;output_variable:string;end_selector:string[];recipe:string;schema_sha256:string;schema_text_sha256:string;code_sha256:string;code_text:string;failure_behavior:string;verification:string;platform_checked:false;business_verified:false};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const fields=['node_id','source_node_id','input_variable','output_variable','end_selector','recipe','schema_sha256','schema_text_sha256','code_sha256','code_text','failure_behavior','verification','platform_checked','business_verified'];
export function validStrictFileGuard(v:unknown,output:unknown):v is StrictFileGuard{
 if(!object(v)||!object(output)||Object.keys(v).length!==fields.length||Object.keys(v).some(k=>!fields.includes(k))||typeof v.node_id!=='string'||!v.node_id||v.node_id===output.node_id||v.source_node_id!==output.node_id||v.input_variable!=='data'||v.output_variable!=='result'||v.recipe!=='sierra_strict_schema_guard_v1'||v.failure_behavior!=='fail_workflow_no_defaults_no_retry'||v.verification!=='canonical_code_and_binding_static_only'||v.platform_checked!==false||v.business_verified!==false||typeof v.code_text!=='string'||!v.code_text.startsWith('# Sierra strict schema guard v1\n')||new TextEncoder().encode(v.code_text).length>256000||!['schema_sha256','schema_text_sha256','code_sha256'].every(k=>typeof v[k]==='string'&&/^[a-f0-9]{64}$/.test(v[k] as string)))return false;
 return JSON.stringify(v.end_selector)===JSON.stringify([output.node_id,'structured_output'])||JSON.stringify(v.end_selector)===JSON.stringify([v.node_id,'result']);
}
async function sha(text:string){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))].map(n=>n.toString(16).padStart(2,'0')).join('')}
export async function verifyStrictFileGuard(flow:{strict_guard?:StrictFileGuard;structured_output?:StructuredFileOutput}){
 if(!flow.strict_guard)return;
 if(!validStrictFileGuard(flow.strict_guard,flow.structured_output)||!flow.structured_output||await sha(flow.strict_guard.code_text)!==flow.strict_guard.code_sha256||await sha(flow.structured_output.schema_text)!==flow.strict_guard.schema_text_sha256)throw Error('文件Schema检查代码或完整规则与冻结哈希不一致，未提供运行按钮。');
}
export default function FileSchemaGuard({value}:{value:StrictFileGuard}){
 return <div className="file-schema-guard callout" style={{display:'block'}}><b>工作流内严格Schema校验</b><p>{value.source_node_id}.structured_output → {value.node_id}.data<br/>实际结束来源：{value.end_selector.join('.')}</p><p>按所列Schema检查原对象；不合规由代码节点抛出错误，使整次Workflow失败。不转换值、不补默认、不删字段、不自动重试；仍可能已经产生模型费用。</p><details><summary>查看冻结的完整检查代码</summary><pre>{value.code_text}</pre></details><p className="hint">代码SHA256：{value.code_sha256}<br/>Schema SHA256：{value.schema_sha256}</p><p className="hint">本机核对的是Sierra v1生成代码、对象绑定和完整发布图。尚无本次节点轨迹证明远端沙箱实际执行，平台成功及Schema合规也不证明字段真实；返回后还会按本机大小、整数及完整Schema边界核对。不执行自定义或修改过的代码。</p></div>;
}
