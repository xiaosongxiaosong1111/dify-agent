import {useCallback,useState,type SetStateAction} from 'react';
export const DEFAULT_RUN_INPUT='{\n  "query": ""\n}';
/** Independent unsent free-run inputs in page memory; never persists or dispatches. */
export default function useTaskRunDraft(taskId:string|null){
 const [drafts,setDrafts]=useState<Map<string,string>>(()=>new Map());
 const input=taskId?drafts.get(taskId)??DEFAULT_RUN_INPUT:DEFAULT_RUN_INPUT;
 const setInput=useCallback((value:SetStateAction<string>)=>{
  if(!taskId)return;
  setDrafts(previous=>{const old=previous.get(taskId)??DEFAULT_RUN_INPUT,nextValue=typeof value==='function'?value(old):value;if(nextValue===old)return previous;const next=new Map(previous);if(nextValue===DEFAULT_RUN_INPUT)next.delete(taskId);else next.set(taskId,nextValue);return next});
 },[taskId]);
 const hasDraft=useCallback((id:string)=>drafts.has(id),[drafts]);
 return [input,setInput,hasDraft,drafts.size>0] as const;
}
