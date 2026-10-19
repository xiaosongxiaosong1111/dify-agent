import {unsafePlanNumbers} from './PlanText';
type Scope={object:boolean;expectKey:boolean;keys:Set<string>};
function decimalMeaning(text:string):string|null{
 const match=/^(-?)([0-9]+)(?:\.([0-9]+))?(?:[eE]([+-]?[0-9]+))?$/.exec(text);if(!match)return null;
 const fraction=match[3]||'',significant=(match[2]+fraction).replace(/^0+/,'');if(!significant)return '0';
 const digits=significant.replace(/0+$/,''),scale=Number(match[4]||0)-fraction.length+significant.length-digits.length;
 return Number.isSafeInteger(scale)?match[1]+digits+'e'+scale:null;
}
/** JSON.parse checks syntax; this scan detects keys before any parsed value is used. */
export function parseRunInputText(text:string):Record<string,unknown>{
 if(typeof text!=='string'||text.length>2000000)throw Error('自由输入超过本机200万字符检查范围，原文保持；请缩小输入或明确文件方案，未派发。');
 let parsed:unknown;try{parsed=JSON.parse(text)}catch{throw Error('输入必须是有效 JSON；原文保持，未派发。')}
 if(!parsed||Array.isArray(parsed)||typeof parsed!=='object')throw Error('输入必须是 JSON 对象；原文保持，未派发。');
 const scopes:Scope[]=[],number=/-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/y;let totalKeys=0;
 for(let i=0;i<text.length;){const c=text[i];
  if(c==='"'){
   const start=i;i++;
   while(i<text.length){if(text[i]==='\\'){i+=2;continue}if(text[i++]==='"')break}
   const scope=scopes[scopes.length-1];
   if(scope?.object&&scope.expectKey){const key=JSON.parse(text.slice(start,i)) as string;if(scope.keys.has(key))throw Error('输入JSON包含重复字段（包括转义后相同的名称），不会自动选择最后一个值；请在完整原文中明确保留哪一项，未派发。');scope.keys.add(key);scope.expectKey=false;if(++totalKeys>100000)throw Error('输入字段数量超过本机检查范围，原文保持，未派发。')}
   continue;
  }
  if(c==='-'||c>='0'&&c<='9'){
   number.lastIndex=i;const match=number.exec(text);if(!match)throw Error('输入数字无法完整核对，原文保持，未派发。');
   const value=Number(match[0]);if(!Number.isFinite(value)||Number.isInteger(value)&&!Number.isSafeInteger(value))throw Error('自由输入包含浏览器不能安全传递的数值或超过结构检查范围；原文保持，未派发。请明确修正，不能自动舍入或改成null。');
   if(decimalMeaning(match[0])!==decimalMeaning(JSON.stringify(value)))throw Error('输入数字在浏览器解析或发送时会改变数值（例如小数舍入或非零数变0），未采用或派发；请在原文中明确数值表示，不自动转成字符串。');
   i=number.lastIndex;continue;
  }
  if(c==='{'||c==='['){scopes.push({object:c==='{',expectKey:c==='{',keys:new Set()});if(scopes.length>100)throw Error('输入嵌套超过本机100层检查范围，原文保持，未派发。')}
  else if(c==='}'||c===']')scopes.pop();
  else if(c===','){const scope=scopes[scopes.length-1];if(scope?.object)scope.expectKey=true}
  i++;
 }
 if(unsafePlanNumbers(parsed))throw Error('自由输入包含浏览器不能安全传递的数值或超过结构检查范围；原文保持，未派发。请明确修正，不能自动舍入或改成null。');
 return parsed as Record<string,unknown>;
}
