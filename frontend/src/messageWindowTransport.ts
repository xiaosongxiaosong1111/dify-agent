export type MessageWindow={schema_version:1;task_id:string;revision:number;state_sequence:number;start:number;end:number;anchor_count:number;total_messages:number;source_token:string;page_limit:50;verification:string;task_modified:false;model_called:false;external_network_requested:false;note:string};
const object=(value:unknown):value is Record<string,unknown>=>!!value&&typeof value==='object'&&!Array.isArray(value);
const count=(value:unknown)=>Number.isSafeInteger(value)&&Number(value)>=0;
export function validWindow(value:unknown,taskId:string,revision:number,messages:unknown):value is MessageWindow{
 if(!object(value)||!Array.isArray(messages)||value.schema_version!==1||value.task_id!==taskId||value.revision!==revision||!['state_sequence','start','end','anchor_count','total_messages'].every(k=>count(value[k]))||value.page_limit!==50||value.verification!=='current_saved_message_window_only'||value.task_modified!==false||value.model_called!==false||value.external_network_requested!==false||typeof value.source_token!=='string'||!/^[a-f0-9]{64}$/.test(value.source_token)||typeof value.note!=='string')return false;
 const n=Number(value.total_messages),anchor=Number(value.anchor_count),start=Number(value.start),end=Number(value.end);
 return start<=end&&end<=anchor&&anchor<=n&&end-start===messages.length&&messages.length<=50&&(anchor===0?start===0&&end===0:start<end);
}
export function validateTaskWindow(value:unknown){
 if(!object(value)||typeof value.id!=='string'||!Number.isSafeInteger(value.revision)||!validWindow(value.message_window,value.id,Number(value.revision),value.messages)||value.message_count!==value.message_window.total_messages||value.message_window.anchor_count!==value.message_count||value.message_window.end!==value.message_count||value.message_window.start!==Math.max(0,Number(value.message_count)-50)||value.message_window.state_sequence!==(value.state_sequence??0))throw Error('任务消息窗口、计数或来源无法核对；请核对运行版本，未把完整历史当作窗口。');
}
export const windowCursor=(value:MessageWindow)=>({start:value.start,end:value.end,anchor_count:value.anchor_count,source_token:value.source_token});
export const taskMessageCount=(task:{message_count?:number;messages:unknown[]})=>task.message_count??task.messages.length;
