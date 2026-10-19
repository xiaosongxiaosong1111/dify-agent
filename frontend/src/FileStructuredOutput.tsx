export type StructuredFileOutput={node_id:string;output_variable:string;schema:Record<string,unknown>;schema_text:string;verification:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
export function validStructuredFileOutput(v:unknown):v is StructuredFileOutput{
 if(!object(v)||typeof v.node_id!=='string'||!v.node_id||typeof v.output_variable!=='string'||!/^[A-Za-z_][A-Za-z0-9_]{0,63}$/.test(v.output_variable)||!object(v.schema)||v.schema.type!=='object'||typeof v.schema_text!=='string'||new TextEncoder().encode(v.schema_text).length>128000||v.verification!=='declared_schema_and_local_instance_check_only')return false;
 try{return JSON.stringify(JSON.parse(v.schema_text))===JSON.stringify(v.schema)}catch{return false}
}
export default function FileStructuredOutput({value}:{value:StructuredFileOutput}){
 return <div className="file-structured-output"><b>本次返回JSON对象并按完整Schema本机核对</b><p>来源：{value.node_id}.structured_output<br/>结束输出：{value.output_variable}</p><details open><summary>冻结的完整输出Schema（保留数字原文）</summary><pre>{value.schema_text}</pre></details><p className="hint">必须返回真正JSON对象，按所列字段、类型、必填及额外字段规则核对，不解析JSON文字、不补默认、不删字段或自动修复。最多64000字节，整数限±9007199254740991；小数不承诺金额精度。对象或规则不符时记结果未知，不自动重跑。</p><p className="hint">声明和本机核对不证明Dify／供应商原生严格支持；平台可能修复JSON或改写Schema。字段形式正确也不证明提取文字完整或业务值真实，仍需固定业务样例和人工复核。</p></div>;
}
