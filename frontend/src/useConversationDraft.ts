import {useCallback,useState,type SetStateAction} from 'react';
export type ConversationMode='review'|'discussion';
type Draft={text:string;mode:ConversationMode};
const empty:Draft={text:'',mode:'review'};
/** Page-memory drafts only: no network, browser storage or automatic sending. */
export default function useConversationDraft(taskId:string|null){
 const [drafts,setDrafts]=useState<Map<string,Draft>>(()=>new Map());
 const current=taskId?drafts.get(taskId)||empty:empty;
 const setText=useCallback((value:SetStateAction<string>)=>{
  if(!taskId)return;
  setDrafts(previous=>{const old=previous.get(taskId)||empty,text=typeof value==='function'?value(old.text):value;if(text===old.text)return previous;const next=new Map(previous);if(!text&&old.mode==='review')next.delete(taskId);else next.set(taskId,{...old,text});return next});
 },[taskId]);
 const setMode=useCallback((mode:ConversationMode)=>{
  if(!taskId||!['review','discussion'].includes(mode))return;
  setDrafts(previous=>{const old=previous.get(taskId)||empty;if(mode===old.mode)return previous;const next=new Map(previous);if(!old.text&&mode==='review')next.delete(taskId);else next.set(taskId,{...old,mode});return next});
 },[taskId]);
 const hasDraft=useCallback((id:string)=>!!drafts.get(id)?.text.trim(),[drafts]);
 const clearSent=useCallback((content:string,mode:ConversationMode,originalText?:string)=>{
  if(!taskId)return;
  setDrafts(previous=>{const old=previous.get(taskId);if(!old||old.mode!==mode||old.text.trim()!==content.trim()||originalText!==undefined&&old.text!==originalText)return previous;const next=new Map(previous);if(mode==='review')next.delete(taskId);else next.set(taskId,{...old,text:''});return next});
 },[taskId]);
 return {text:current.text,mode:current.mode,setText,setMode,hasDraft,clearSent,hasAnyDraft:[...drafts.values()].some(draft=>!!draft.text.trim())};
}
