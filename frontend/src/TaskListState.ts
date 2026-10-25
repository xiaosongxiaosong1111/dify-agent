import {useCallback,useState,type SetStateAction} from 'react';
export type TaskSummary={id:string;name:string;app_type:string;revision:number;status:string;updated_at?:string|null};
export function taskSummary(value:TaskSummary):TaskSummary{
 return {id:value.id,name:value.name,app_type:value.app_type,revision:value.revision,status:value.status,updated_at:typeof value.updated_at==='string'?value.updated_at:null};
}
export function useTaskRows(){
 const [rows,setRows]=useState<TaskSummary[]>([]);
 const update=useCallback((next:SetStateAction<TaskSummary[]>)=>setRows(current=>(typeof next==='function'?next(current):next).map(taskSummary)),[]);
 return [rows,update] as const;
}
export async function loadTaskSummaries(){
 const response=await fetch('/api/task-summaries',{cache:'no-store'});
 if(!response.ok)throw Error(`任务摘要读取失败（HTTP ${response.status}），未回退读取所有任务正文，请核对运行版本。`);
 const value=await response.json();const allowed=['id','name','app_type','revision','status','updated_at'];
 if(!value||value.schema_version!==1||value.view!=='summary'||!Array.isArray(value.items)||!value.items.every((row:TaskSummary)=>row&&Object.keys(row).every(key=>allowed.includes(key))&&typeof row.id==='string'&&!!row.id&&typeof row.name==='string'&&typeof row.status==='string'&&['workflow','advanced-chat','agent'].includes(row.app_type)&&Number.isSafeInteger(row.revision)&&row.revision>0&&(row.updated_at===null||typeof row.updated_at==='string'))||new Set(value.items.map((row:TaskSummary)=>row.id)).size!==value.items.length)throw Error('任务摘要格式或标识无法核对，未当作完整任务使用。');
 return value.items.map(taskSummary) as TaskSummary[];
}
