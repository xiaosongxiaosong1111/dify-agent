import {useEffect} from 'react';

/** Native navigation warning only; never saves, sends, or stores draft contents. */
export default function useUnsavedExit(pending:boolean){
 useEffect(()=>{
  if(!pending)return;
  const warn=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=''};
  window.addEventListener('beforeunload',warn);
  return()=>window.removeEventListener('beforeunload',warn);
 },[pending]);
}
