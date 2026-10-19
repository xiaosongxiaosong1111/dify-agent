export function unsafePlanNumbers(value:unknown):boolean{
 const stack=[value];let count=0;while(stack.length){if(++count>100000)return true;const v=stack.pop();if(typeof v==='number'&&(!Number.isFinite(v)||Number.isInteger(v)&&!Number.isSafeInteger(v)))return true;if(v&&typeof v==='object'){const values=Object.values(v);if(values.length>100000-count-stack.length)return true;for(const item of values)stack.push(item)}}return false;
}
export function exactPlanText(plan:unknown,text:unknown):string|null{
 if(typeof text!=='string')return null;
 try{if(JSON.stringify(JSON.parse(text))===JSON.stringify(plan))return text}catch{}
 throw Error('计划原文与返回结构不一致，未使用可能舍入的对象替代。');
}
