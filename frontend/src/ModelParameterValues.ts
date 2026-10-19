import {parseRunInputText} from './RunInputText';
/** Preserve decimal meaning when a form value becomes a JSON number. */
export function modelNumber(raw:string|number|boolean,label:string):number{
 if(typeof raw==='boolean')throw Error(`${label} 须明确填写数值，不能把布尔值转换成数字。`);
 const source=String(raw).trim();if(source.length>2048)throw Error(`${label} 数字过长，原文保持，不截断后采用。`);const match=/^([+-]?)([0-9]*)(?:\.([0-9]*))?(?:[eE]([+-]?[0-9]+))?$/.exec(source);
 if(!match||!(match[2]||match[3]))throw Error(`${label} 须为有效的十进制数字，原文保持。`);
 const integer=(match[2]||'0').replace(/^0+(?=[0-9])/,'');
 const normalized=(match[1]==='-'?'-':'')+integer+(match[3]?'.'+match[3]:'')+(match[4]?'e'+match[4]:'');
 try{const value=parseRunInputText(`{"value":${normalized}}`).value;if(typeof value!=='number')throw Error();return value}
 catch{throw Error(`${label} 无法在浏览器解析及发送时保持数值，原文保持；请明确修正，不自动舍入或改成默认值。`)}
}

export function modelBooleanDefault(value:unknown):boolean|''{return typeof value==='boolean'?value:''}
