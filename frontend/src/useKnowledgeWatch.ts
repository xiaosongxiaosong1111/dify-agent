import {useEffect,useRef,useState} from 'react';
type WatchedJob={id:string;task_id:string;task_revision:number;environment_id:string|null;status:string;operations:{status:string}[]};
export default function useKnowledgeWatch<T extends WatchedJob>({taskId,revision,environmentId,job,executing,keep,onError}:{taskId:string;revision:number;environmentId:string|null;job:T|null;executing:boolean;keep:(v:T)=>void;onError:(message:string)=>void}){
 const [watching,setWatching]=useState(false),[rounds,setRounds]=useState(0),[note,setNote]=useState('平台自动跟踪未开启。'),[remoteBusy,setRemoteBusy]=useState(false),[localStopped,setLocalStopped]=useState(false);
 const scope=JSON.stringify([taskId,revision,environmentId,job?.id,job?.task_revision,job?.environment_id]),currentScope=useRef(scope);currentScope.current=scope;
 const callbacks=useRef({keep,onError});callbacks.current={keep,onError};
 const session=useRef({enabled:false,scope:'',started:0,rounds:0}),epoch=useRef(0),controller=useRef<AbortController|null>(null);
 const pending=!!job?.operations.some(o=>o.status==='pending');
 function stop(message='已停止后续平台索引查询；已派发请求可能继续完成。'){
  session.current.enabled=false;epoch.current++;controller.current?.abort();setWatching(false);setRemoteBusy(false);setNote(message);
 }
 function start(){
  if(!job||job.status!=='indexing'||job.task_revision!==revision||job.environment_id!==environmentId||pending||executing)return;
  stop();session.current={enabled:true,scope,started:Date.now(),rounds:0};setRounds(0);setNote('有限平台跟踪进行中。');setLocalStopped(false);setWatching(true);
 }
 useEffect(()=>{session.current.enabled=false;setWatching(false);setRounds(0);setRemoteBusy(false);setLocalStopped(false);setNote('平台自动跟踪未开启。');return()=>{session.current.enabled=false;epoch.current++;controller.current?.abort()}},[scope]);
 useEffect(()=>{
  if(!job||localStopped||!(pending||job.status==='running'||watching&&job.status==='indexing'))return;
  const abort=new AbortController();controller.current=abort;const ticket=++epoch.current;let inflight=false;
  const valid=()=>!abort.signal.aborted&&epoch.current===ticket&&currentScope.current===scope;
  function verify(value:T){if(!value||value.id!==job!.id||value.task_id!==taskId||value.task_revision!==job!.task_revision||value.environment_id!==job!.environment_id||typeof value.status!=='string'||!Array.isArray(value.operations)||value.operations.some(o=>!o||typeof o.status!=='string'))throw Error('知识库回执归属或状态结构不匹配，未继续平台查询。')}
  async function request(remote=false):Promise<T>{const response=await fetch(`${import.meta.env.VITE_API_BASE||'/api'}/knowledge-jobs/${encodeURIComponent(job!.id)}${remote?'/refresh':''}`,{method:remote?'POST':'GET',...(remote?{headers:{'Content-Type':'application/json'},body:'{}'}:{}),cache:'no-store',signal:abort.signal});const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:`状态读取失败（HTTP ${response.status}）`);verify(value);return value}
  function expired(){return Date.now()-session.current.started>=120000||session.current.rounds>=20}
  const poll=async()=>{
   if(inflight||!valid())return;inflight=true;
   try{
    if(session.current.enabled&&expired()){stop('已达到20轮或2分钟边界，停止后续平台查询。');return}
    const value=await request();if(!valid())return;callbacks.current.keep(value);
    if(!session.current.enabled||session.current.scope!==scope)return;
    if(value.status!=='indexing'||value.operations.some(o=>o.status==='pending')||executing||value.task_revision!==revision||value.environment_id!==environmentId){stop('当前状态不再允许平台自动跟踪，已停止后续查询。');return}
    if(expired()){stop('已达到20轮或2分钟边界，停止后续平台查询。');return}
    session.current.rounds++;setRounds(session.current.rounds);setRemoteBusy(true);
    const observed=await request(true);if(!valid())return;callbacks.current.keep(observed);setRemoteBusy(false);
    if(expired()||observed.status!=='indexing')stop(expired()?'已达到20轮或2分钟边界，停止后续平台查询。':'索引状态已变化，平台自动跟踪停止。');
   }catch(e){if(valid()){setLocalStopped(true);stop('读取失败，已停止自动跟踪；没有自动重试。');callbacks.current.onError(e instanceof Error?e.message:'状态读取失败。')}}finally{inflight=false}
  };
  const timer=setInterval(()=>void poll(),2000);
  const deadline=watching?setTimeout(()=>{if(valid())stop('已达到2分钟边界，停止后续平台查询。')},Math.max(0,120000-(Date.now()-session.current.started))):null;
  return()=>{epoch.current++;abort.abort();clearInterval(timer);if(deadline!==null)clearTimeout(deadline)};
 },[scope,job?.status,pending,executing,watching,localStopped]);
 return {watching,rounds,note,remoteBusy,localStopped,start,stop,resumeLocal:()=>setLocalStopped(false)};
}
