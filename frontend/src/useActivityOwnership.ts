import {useCallback,useMemo,useRef,useState,type SetStateAction} from 'react';

type Activity=string|boolean|null;
type Reporter=(value:Activity,owner?:object)=>void;
type Entry={allowed:()=>boolean;trueLabel:string;owners:WeakMap<object,number>;fallback:object;report:Reporter};

/** Gives a mounted panel its own identity, including after a revision change. */
export function useOwnedActivity<T>(report:((value:T,owner?:object)=>void)|undefined,scope:unknown){
 return useMemo(()=>{const owner={};return (value:T)=>report?.(value,owner)},[report,scope]);
}

/** Main actions and panel actions share the same visible-state ownership. */
export default function useActivityOwnership(){
 const [label,publish]=useState('');
 const state=useRef({value:'',serial:0,scope:'',entries:new Map<string,Entry>()});
 const set=useCallback((update:SetStateAction<string>)=>{const current=state.current;current.value=typeof update==='function'?update(current.value):update;const ticket=++current.serial;publish(current.value);return ticket},[]);
 const owns=useCallback((ticket:number)=>state.current.serial===ticket,[]);
 const scoped=useCallback((scope:string,name:string,allowed:()=>boolean,trueLabel='处理当前任务'):Reporter=>{
  const current=state.current;
  if(scope!=='global'&&scope!==current.scope){current.scope=scope;for(const key of current.entries.keys())if(!key.startsWith('global:'))current.entries.delete(key)}
  const key=scope+':'+name;let entry=current.entries.get(key);
  if(!entry){
   const created:Entry={allowed,trueLabel,owners:new WeakMap(),fallback:{},report:()=>{}};
   created.report=(value,owner=created.fallback)=>{
    if(!created.allowed())return;
    const next=typeof value==='boolean'?value?created.trueLabel:'':value||'';
    if(next)created.owners.set(owner,set(next));
    else{const ticket=created.owners.get(owner);created.owners.delete(owner);if(ticket!==undefined&&owns(ticket))set('')}
   };
   current.entries.set(key,created);entry=created;
  }
  entry.allowed=allowed;entry.trueLabel=trueLabel;return entry.report;
 },[set,owns]);
 return {label,set,owns,scoped};
}
