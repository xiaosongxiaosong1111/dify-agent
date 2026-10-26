import {parseRunInputText} from './RunInputText';
import type {TestCase} from './AcceptancePanel';
export const CASE_SET_LIMIT=512000;
export const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
export const hash=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export const fail=()=>Error('样例定义包、来源或读取范围无法完整核对，未追加或下载。');
function keys(value:Record<string,unknown>,required:string[],optional:string[]=[]){return required.every(k=>Object.hasOwn(value,k))&&Object.keys(value).every(k=>[...required,...optional].includes(k))}
export function sameJson(left:unknown,right:unknown):boolean{
 if(left===right)return true;if(Array.isArray(left)||Array.isArray(right))return Array.isArray(left)&&Array.isArray(right)&&left.length===right.length&&left.every((item,i)=>sameJson(item,right[i]));
 if(object(left)&&object(right)){const a=Object.keys(left).sort(),b=Object.keys(right).sort();return a.length===b.length&&a.every((key,i)=>key===b[i]&&sameJson(left[key],right[key]))}return false;
}
function turn(value:unknown){
 if(!object(value)||!object(value.input)||!object(value.expectation))throw fail();const expected=value.expectation;
 if(typeof expected.mode!=='string'||!['equals','contains','json_keys','json_schema','manual'].includes(expected.mode))throw fail();
 if(expected.mode==='manual'){if(!keys(expected,['mode','description'])||typeof expected.description!=='string'||!expected.description.trim())throw fail()}
 else{
  if(!keys(expected,['mode','target','expected'])||typeof expected.target!=='string'||!expected.target.trim())throw fail();
  if(['contains','json_keys'].includes(expected.mode)&&(!Array.isArray(expected.expected)||!expected.expected.length||expected.expected.some(x=>typeof x!=='string'||!x)))throw fail();
  if(expected.mode==='json_schema'&&typeof expected.expected!=='string')throw fail();
 }
}
export function casePackage(bytes:ArrayBuffer,appType:string){
 if(bytes.byteLength<1||bytes.byteLength>CASE_SET_LIMIT)throw fail();let value:Record<string,unknown>;
 try{value=parseRunInputText(new TextDecoder('utf-8',{fatal:true}).decode(bytes))}catch{throw fail()}
 if(!keys(value,['schema_version','app_type','cases'])||value.schema_version!==1||value.app_type!==appType||!Array.isArray(value.cases)||value.cases.length<1||value.cases.length>20)throw fail();
 for(const row of value.cases){
  if(!object(row)||!keys(row,['name','input','expectation','required'],['followups'])||typeof row.name!=='string'||!row.name.trim()||typeof row.required!=='boolean')throw fail();turn(row);
  if(Object.hasOwn(row,'followups')){
   if(!['advanced-chat','agent'].includes(appType)||!Array.isArray(row.followups)||row.followups.length<1||row.followups.length>9)throw fail();
   for(const follow of row.followups){if(!object(follow)||!keys(follow,['input','expectation']))throw fail();turn(follow)}
  }
 }
 return value as unknown as {schema_version:1;app_type:string;cases:Omit<TestCase,'id'>[]};
}
export async function sha256(bytes:ArrayBuffer){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(n=>n.toString(16).padStart(2,'0')).join('')}
