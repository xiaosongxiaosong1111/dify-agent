import {useEffect,useRef,useState} from 'react';
import SchemaCheckNotice from './SchemaCheckNotice';

const labels:Record<string,string>={json:'JSON不完整或格式不正确，请按行列位置核对。',duplicate:'JSON存在重复键，不能选择其中一个值。',finite_json:'JSON须只包含有限数值及可表达的值。',encoding:'文字编码不完整。',size:'Schema最多64000 UTF-8字节，不截断。',root:'根类型须为object，不能用数组、标量或null。',type:'请明确受支持的类型，不猜测或转换。',keywords:'包含未适配的关键字；引用、组合、正则及默认值不能忽略。',enum:'枚举须为1—100个不重复的同类型标量。',complexity:'Schema最多200个类型节点、8层嵌套。',properties:'对象须有最多50个有效命名属性。',closed_object:'每个对象须明确additionalProperties=false。',required:'required须为properties内的唯一字段名列表。',text:'标题或说明须为最多4000字符的文字。',bounds:'范围值须有效且下限不能大于上限，长度／数量须为0—1000000整数。',unsafe_integer:'整数规则须在±9007199254740991内，不舍入。',credentials:'Schema疑似含明文凭据，请移除密钥或密码。',schema:'请核对完整受支持的对象规则，不会简化后采用。',too_many:'规则问题超过20项，请分步修改；未采用部分Schema。'};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const path=/^schema(?:(?:\.properties\[(?:[1-9]|[1-4][0-9]|50)\])|\.items){0,8}(?:\.(?:type|enum|properties|required|additionalProperties|title|description|minLength|maxLength|minItems|maxItems|minimum|maximum))?$/;
function explain(value:unknown):string[]|null{
 if(!Array.isArray(value)||value.length>20)return null;
 const out:string[]=[];
 for(const row of value){
  if(!object(row)||Object.keys(row).sort().join(',')!=='code,column,line,path'||typeof row.code!=='string'||!Object.hasOwn(labels,row.code)||!(row.path===null||typeof row.path==='string'&&row.path.length<=300&&path.test(row.path)))return null;
  if(row.line!==null||row.column!==null){if(row.code!=='json'||![row.line,row.column].every(n=>typeof n==='number'&&Number.isSafeInteger(n)&&n>=1&&n<=64001))return null}
  out.push((row.path?row.path+'：':'')+labels[row.code]+(row.line!==null?` 第${row.line}行，第${row.column}列。`:''));
 }
 return out;
}
export default function ObjectSchemaCheckPanel({taskId,revision,scope,schemaText,disabled}:{taskId:string;revision:number;scope:string;schemaText:string;disabled:boolean}){
 const [status,setStatus]=useState<'idle'|'checking'|'valid'|'invalid'|'error'>('idle'),[issues,setIssues]=useState<string[]>([]),[schemaHash,setSchemaHash]=useState<string|null>(null),epoch=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{epoch.current++;controller.current?.abort();setStatus('idle');setIssues([]);setSchemaHash(null);return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,scope,schemaText]);
 useEffect(()=>{if(disabled){epoch.current++;controller.current?.abort();setStatus('idle');setIssues([]);setSchemaHash(null)}},[disabled]);
 async function check(){
  if(disabled||status==='checking'||!schemaText.trim())return;
  const ticket=++epoch.current,nonce=crypto.randomUUID(),abort=new AbortController();controller.current=abort;setStatus('checking');setIssues([]);setSchemaHash(null);const timer=setTimeout(()=>abort.abort(),15000);
  try{
   const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(schemaText))),b=>b.toString(16).padStart(2,'0')).join('');
   if(ticket!==epoch.current)return;
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/object-schema-check`,{method:'POST',signal:abort.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,schema_text:schemaText,request_nonce:nonce})});
   if(ticket!==epoch.current)return;
   if(!response.ok)throw Error();
   const v:unknown=await response.json();if(ticket!==epoch.current)return;
   if(!object(v)||v.task_id!==taskId||v.revision!==revision||v.request_nonce!==nonce||v.source_text_sha256!==digest||typeof v.valid!=='boolean'||v.verification!=='local_object_schema_rules_only'||['task_changed','network_requested','code_executed','platform_checked','business_verified'].some(k=>v[k]!==false))throw Error();
   const messages=explain(v.diagnostics);if(messages===null||(v.valid?(messages.length!==0||!hash(v.schema_sha256)):(messages.length===0||v.schema_sha256!==null)))throw Error();
   setIssues(messages);setSchemaHash(v.valid?v.schema_sha256 as string:null);setStatus(v.valid?'valid':'invalid');
  }catch{if(ticket===epoch.current)setStatus('error')}
  finally{clearTimeout(timer)}
 }
 return <section className="object-schema-check-panel"><button type="button" className="secondary" disabled={disabled||status==='checking'||!schemaText.trim()} onClick={()=>void check()}>检查对象 Schema（不保存）</button><p className="hint">路径中的properties[1]表示原文的第1个属性规则；只解释支持范围，检查通过不代替结果合同确认。</p><SchemaCheckNotice status={status} issues={issues} schemaHash={schemaHash}/></section>;
}
