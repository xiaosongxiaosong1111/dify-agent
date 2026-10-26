import {useState} from 'react';
import {parseRunInputText} from './RunInputText';
export default function NumericRunInput({name,value,disabled,onCommit,onPending}:{name:string;value:unknown;disabled:boolean;onCommit:(value:number)=>void;onPending:(pending:boolean)=>void}){
 const original=typeof value==='string'?value:JSON.stringify(value)??'', [draft,setDraft]=useState(original);
 const pending=draft!==original;let number:number|undefined,error='';
 if(pending){try{if(!/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$/.test(draft.trim()))throw Error('请填写一个完整JSON数字；空白、未完成或其他JSON类型保持原稿。');const parsed=parseRunInputText('{"value":'+draft+'}');if(typeof parsed.value!=='number')throw Error('请填写JSON数字，不把字符串、布尔或null转换成数字。');number=parsed.value}catch(e){error=e instanceof Error?e.message:'数字原文无法核对，未填入完整输入。'}}
 return <div className="numeric-run-input"><input aria-label={`试跑输入 ${name} 实际值`} value={draft} disabled={disabled} onChange={e=>{setDraft(e.target.value);onPending(e.target.value!==original)}}/><p className="hint">数字在此独立编辑，明确填入后才改变上方完整JSON；空白、未完成或无法安全传递的数字保持原文，不自动舍入、变0/null或转文字。</p>{pending&&<p role="status">数字草稿尚未填入；请明确填入或撤销后再检查或自由试跑。</p>}{pending&&error&&<p role="alert" className="callout amber">{error}</p>}<button className="secondary" disabled={disabled||!pending||!!error||number===undefined} onClick={()=>{if(number!==undefined&&!error){onPending(false);onCommit(number)}}}>将 {name} 数字填入本次输入</button><button className="secondary" disabled={disabled||!pending} onClick={()=>{setDraft(original);onPending(false)}}>撤销 {name} 数字草稿</button></div>;
}
