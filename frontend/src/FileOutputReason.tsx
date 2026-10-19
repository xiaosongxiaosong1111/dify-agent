export type FileOutputReasonValue={schema_version:1;category:string;schema_pointer:string|null;message:string;schema_text_sha256:string;output_retained:false;automatic_retry:false;business_verified:false;verification:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const categories=['output_fields','object_required','json_value_invalid','size_limit','structure_limit','integer_range','schema_rule','unknown'];
const messages:Record<string,string>={"output_fields": "平台成功回执的输出字段不符合结束声明；不展示未知字段名或值。", "object_required": "结束输出须为真正JSON对象；不将JSON文字、数组、null或布尔转换为对象。", "json_value_invalid": "输出不是可完整编码的有限JSON值；未展示原值或异常正文。", "size_limit": "输出对象超过64000字节；未截断、拆字段或保留原值。", "structure_limit": "输出对象超过20000实例值的结构检查上限；不把部分结果算作通过。", "integer_range": "输出整数超出本批无损编辑范围±9007199254740991；未舍入或改成其他类型。", "schema_rule": "输出对象未通过已确认Schema规则；不补默认、删除字段或重跑。", "unknown": "本机未能安全细分此次对象拒绝原因；不展示原值或异常正文。"};
const fields=['schema_version','category','schema_pointer','message','schema_text_sha256','output_retained','automatic_retry','business_verified','verification'];
const keywords=['type','required','additionalProperties','enum','minimum','maximum','minItems','maxItems','minLength','maxLength'];
export function validFileOutputReason(v:unknown):v is FileOutputReasonValue{
 return object(v)&&Object.keys(v).length===fields.length&&Object.keys(v).every(k=>fields.includes(k))&&v.schema_version===1&&typeof v.category==='string'&&categories.includes(v.category)&&typeof v.message==='string'&&v.message.length<=2000&&typeof v.schema_text_sha256==='string'&&/^[a-f0-9]{64}$/.test(v.schema_text_sha256)&&v.output_retained===false&&v.automatic_retry===false&&v.business_verified===false&&v.verification==='local_file_output_contract_rejection_only'&&(v.schema_pointer===null||v.category==='schema_rule'&&typeof v.schema_pointer==='string'&&new TextEncoder().encode(v.schema_pointer).length<=1000&&!/[\u0000-\u001f\u007f]/.test(v.schema_pointer))&&v.message===messages[v.category]+(v.schema_pointer!==null?' 规则路径：'+v.schema_pointer:'');
}
function rulePaths(schema:unknown){
 const result=new Set<string>(),stack:{row:unknown;path:string;depth:number}[]=[{row:schema,path:'',depth:0}];let count=0;
 while(stack.length){const {row,path,depth}=stack.pop()!;if(++count>200||depth>8||!object(row))throw Error('拒绝原因的原Schema不能完整核对。');for(const k of keywords)if(Object.hasOwn(row,k))result.add(path+'/'+k);if(row.type==='object'&&object(row.properties))for(const [k,v] of Object.entries(row.properties))stack.push({row:v,path:path+'/properties/'+k.replace(/~/g,'~0').replace(/\//g,'~1'),depth:depth+1});else if(row.type==='array')stack.push({row:row.items,path:path+'/items',depth:depth+1})}
 return result;
}
export async function verifyFileOutputReason(value:unknown,schemaText?:string){
 if(value===undefined)return;
 if(!validFileOutputReason(value)||typeof schemaText!=='string')throw Error('文件对象拒绝原因缺少完整版本或原Schema来源，未采用。');
 const actual=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(schemaText)))].map(n=>n.toString(16).padStart(2,'0')).join('');
 if(actual!==value.schema_text_sha256||value.schema_pointer!==null&&!rulePaths(JSON.parse(schemaText)).has(value.schema_pointer))throw Error('拒绝原因与原Schema哈希或规则路径不一致，未使用当前规则代替。');
}
export default function FileOutputReason({value}:{value:unknown}){
 if(!validFileOutputReason(value))return <p className="error">对象拒绝原因不完整或版本未适配，没有推定具体字段问题。</p>;
 return <div className="file-output-contract-reason callout amber" style={{display:'block',overflowWrap:'anywhere'}}><b>原对象输出的本机拒绝原因</b><p>{value.message}</p>{value.schema_pointer&&<p>已确认Schema规则：<code>{value.schema_pointer}</code></p>}<p className="hint">来源：原方案的完整Schema及当时本机检查，不是Dify节点失败原因；未保存原输出值、修改规则或重跑。请核对输入、模型支持及已确认字段，再决定修改；这不授权放宽业务要求。</p></div>;
}
