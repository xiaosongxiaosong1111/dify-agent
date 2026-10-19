import {useEffect,useState} from 'react';
import {modelNumber} from './ModelParameterValues';
type Key='temperature'|'max_tokens';
type Values=Record<Key,number>;
type Task={id:string;revision:number;configuration:Values}|null;
type State={taskId:string;text:Record<Key,string>;edited:Record<Key,boolean>;observed:Values&{revision:number}};
const fields:Key[]=['temperature','max_tokens'];
function initial(task:Task,values?:Values,edited=false):State{const cfg=values||task?.configuration;return {taskId:task?.id||'',text:{temperature:cfg?String(cfg.temperature):'',max_tokens:cfg?String(cfg.max_tokens):''},edited:{temperature:edited,max_tokens:edited},observed:{temperature:cfg?.temperature??NaN,max_tokens:cfg?.max_tokens??NaN,revision:task?.revision||0}}}
function parse(field:Key,raw:string):number{const label=field==='temperature'?'Temperature':'Max tokens',value=modelNumber(raw,label);if(field==='temperature'&&(value<0||value>2))throw Error('Temperature 须为 0—2 的数字；目标型号实际范围仍需另行核对。');if(field==='max_tokens'&&(!Number.isInteger(value)||value<1||value>1000000))throw Error('Max tokens 须为 1—1000000 的整数；实际型号上限仍需另行核对。');return value}
export function useManualModelNumbers(task:Task,onChange:(taskId:string,revision:number,patch:Partial<Values>)=>void){
 const [saved,setSaved]=useState<State>(()=>initial(task));
 const current=saved.taskId===(task?.id||'')?saved:initial(task);
 useEffect(()=>{setSaved(previous=>{if(previous.taskId!==(task?.id||''))return initial(task);if(!task)return previous;const next={...previous,text:{...previous.text},edited:{...previous.edited},observed:{temperature:task.configuration.temperature,max_tokens:task.configuration.max_tokens,revision:task.revision}};let changed=previous.observed.revision!==task.revision;
 for(const field of fields){const value=task.configuration[field];if(!Object.is(previous.observed[field],value)){changed=true;if(!previous.edited[field])next.text[field]=String(value)}if(previous.observed.revision!==task.revision){try{if(parse(field,next.text[field])===value)next.edited[field]=false}catch{/* Retain unfinished user input across a server revision. */}}}return changed?next:previous})},[task?.id,task?.revision,task?.configuration.temperature,task?.configuration.max_tokens]);
 const errors:Partial<Record<Key,string>>={},parsed:Partial<Values>={};if(task)for(const field of fields){try{parsed[field]=parse(field,current.text[field])}catch(e){errors[field]=e instanceof Error?e.message:'数值无法完整核对。'}}
 const invalid=!!task&&Object.keys(errors).length>0,conflict=!!task&&fields.some(field=>!errors[field]&&parsed[field]!==task.configuration[field]),pending=invalid||conflict;
 const change=(field:Key,raw:string)=>{if(!task)return;setSaved(previous=>{const base=previous.taskId===task.id?previous:initial(task);return {...base,text:{...base.text,[field]:raw},edited:{...base.edited,[field]:true}}});try{const value=parse(field,raw);onChange(task.id,task.revision,{[field]:value})}catch{/* No partial value or default is applied. */}};
 const acknowledge=(accepted:Exclude<Task,null>)=>setSaved(previous=>{if(previous.taskId!==accepted.id)return previous;const next={...previous,edited:{...previous.edited},observed:{temperature:accepted.configuration.temperature,max_tokens:accepted.configuration.max_tokens,revision:accepted.revision}};for(const field of fields){try{if(parse(field,previous.text[field])===accepted.configuration[field])next.edited[field]=false}catch{/* Invalid input is never discarded by a save acknowledgement. */}}return next});
 const adopt=(values:Values)=>setSaved(initial(task,values,true));
 const restoreText=(temperature:string,maxTokens:string)=>setSaved({...initial(task),text:{temperature,max_tokens:maxTokens},edited:{temperature:true,max_tokens:true}});
 const exitTo=(values:Values)=>{setSaved(initial(task,values,false));if(task)onChange(task.id,task.revision,values)};
 const reset=()=>setSaved(initial(task));
 const apply=()=>{if(!task||invalid)return;const values=parsed as Values;adopt(values);onChange(task.id,task.revision,values)};
 return {text:current.text,errors,invalid,conflict,pending,change,reset,apply,adopt,acknowledge,restoreText,exitTo};
}

export default function ManualModelNumberFields({draft,disabled}:{draft:ReturnType<typeof useManualModelNumbers>;disabled:boolean}){
 return <div className="manual-model-numbers"><div className="field-grid"><label className="field"><span>Temperature</span><input aria-label="手动 Temperature" inputMode="decimal" disabled={disabled} value={draft.text.temperature} onChange={e=>draft.change('temperature',e.target.value)}/></label><label className="field"><span>Max tokens</span><input aria-label="手动 Max tokens" inputMode="numeric" disabled={disabled} value={draft.text.max_tokens} onChange={e=>draft.change('max_tokens',e.target.value)}/></label></div>
 {Object.entries(draft.errors).map(([field,error])=><p className="alert error" role="alert" key={field}>{error}</p>)}{draft.conflict&&<p className="callout amber">当前数字输入与配置不同，可能已收到后台更新。原输入保留；请核对后明确采用，或回到当前配置中的数值。</p>}
 {draft.pending&&<><p className="hint">数字输入尚待处理，不能保存、确认或切换任务；跨页继续保留，刷新可能丢失。没有自动舍入或使用默认值。</p><div className="actions">{draft.conflict&&!draft.invalid&&<button className="secondary" disabled={disabled} onClick={draft.apply}>明确采用当前有效数字到配置草稿</button>}<button className="secondary" disabled={disabled} onClick={draft.reset}>回到当前配置中的数值</button></div></>}
 </div>;
}
