import {useCallback,useEffect,useRef,useState} from 'react';

type ReadState={status:'loading'|'ready'|'error';message:string};
export function useWorkspaceRead(read:(signal:AbortSignal)=>Promise<string>){
 const latest=useRef(read);latest.current=read;
 const active=useRef<AbortController|null>(null),ticket=useRef(0);
 const [state,setState]=useState<ReadState>({status:'loading',message:''});
 const reload=useCallback(async()=>{
  if(active.current)return;
  const controller=new AbortController(),current=++ticket.current;active.current=controller;setState({status:'loading',message:''});
  let timer:ReturnType<typeof setTimeout>|undefined;
  try{
   const timeout=new Promise<never>((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(Error('读取超过15秒，请检查本机后台后明确重读。'))},15000)});
   const message=await Promise.race([latest.current(controller.signal),timeout]);
   if(current===ticket.current&&!controller.signal.aborted)setState({status:'ready',message});
  }catch(error){
   if(current===ticket.current)setState({status:'error',message:controller.signal.aborted?'读取中断或超过15秒，请检查本机后台后明确重读。':error instanceof Error?error.message:'本机工作区读取失败，请检查后台后明确重读。'});
  }finally{clearTimeout(timer);controller.abort();if(current===ticket.current)active.current=null}
 },[]);
 useEffect(()=>{void reload();return()=>{ticket.current++;active.current?.abort();active.current=null}},[reload]);
 return {...state,reload};
}
export default function WorkspaceRecovery({state,blocked}:{state:ReturnType<typeof useWorkspaceRead>;blocked:boolean}){
 return <section className="workspace-recovery" aria-label="本机工作区读取" style={{fontSize:12,padding:'8px 4px'}}>
  <button className="secondary full" aria-label="重新读取工作区" disabled={state.status==='loading'||blocked} onClick={()=>void state.reload()}>{state.status==='loading'?'正在读取工作区…':'重新读取工作区'}</button>
  {state.status==='error'?<p role="alert">读取本机工作区失败：{state.message}</p>:state.status==='ready'?<p role="status">{state.message}</p>:<p role="status">正在读取已保存的本机状态。</p>}
  <small>仅重读本机信息，不重发对话、模型或Dify操作；未保存编辑和新选择保留。</small>
 </section>;
}
