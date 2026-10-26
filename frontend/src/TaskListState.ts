import {useCallback,useMemo,useRef,useState,type SetStateAction} from 'react';
export type TaskSummary={id:string;name:string;app_type:string;revision:number;status:string;updated_at?:string|null};
type TaskOrderInput={id:string;revision:number;state_sequence?:number};
type TaskOrder={revision:number;sequence:number};
function orderOf(value:TaskOrderInput):TaskOrder|null{
 const sequence=value.state_sequence===undefined?0:value.state_sequence;
 return Number.isSafeInteger(value.revision)&&value.revision>0&&Number.isSafeInteger(sequence)&&sequence>=0?{revision:value.revision,sequence}:null;
}
function atLeast(incoming:TaskOrder,known:TaskOrder){return incoming.revision>known.revision||incoming.revision===known.revision&&incoming.sequence>=known.sequence}
export function taskSummary(value:TaskSummary):TaskSummary{
 return {id:value.id,name:value.name,app_type:value.app_type,revision:value.revision,status:value.status,updated_at:typeof value.updated_at==='string'?value.updated_at:null};
}
export function useTaskRows(){
 const [rows,setRows]=useState<TaskSummary[]>([]);
 const orders=useRef(new Map<string,TaskOrder>());
 const isCurrent=useCallback((value:TaskOrderInput)=>{const incoming=orderOf(value),known=orders.current.get(value.id);return !!incoming&&(!known||atLeast(incoming,known))},[]);
 const remember=useCallback((value:TaskOrderInput)=>{if(!isCurrent(value))return false;orders.current.set(value.id,orderOf(value)!);return true},[isCurrent]);
 const order=useMemo(()=>({isCurrent,remember}),[isCurrent,remember]);
 const update=useCallback((next:SetStateAction<TaskSummary[]>)=>setRows(current=>{const prior=new Map(current.map(row=>[row.id,row]));return (typeof next==='function'?next(current):next).flatMap(value=>{if(remember(value))return [taskSummary(value)];const known=prior.get(value.id);return known?[known]:[]})}),[remember]);
 return [rows,update,order] as const;
}
export async function loadTaskSummaries(){
 const response=await fetch('/api/task-summaries',{cache:'no-store'});
 if(!response.ok)throw Error(`任务摘要读取失败（HTTP ${response.status}），未回退读取所有任务正文，请核对运行版本。`);
 const value=await response.json();const allowed=['id','name','app_type','revision','status','updated_at'];
 if(!value||value.schema_version!==1||value.view!=='summary'||!Array.isArray(value.items)||!value.items.every((row:TaskSummary)=>row&&Object.keys(row).every(key=>allowed.includes(key))&&typeof row.id==='string'&&!!row.id&&typeof row.name==='string'&&typeof row.status==='string'&&['workflow','advanced-chat','agent'].includes(row.app_type)&&Number.isSafeInteger(row.revision)&&row.revision>0&&(row.updated_at===null||typeof row.updated_at==='string'))||new Set(value.items.map((row:TaskSummary)=>row.id)).size!==value.items.length)throw Error('任务摘要格式或标识无法核对，未当作完整任务使用。');
 return value.items.map(taskSummary) as TaskSummary[];
}
