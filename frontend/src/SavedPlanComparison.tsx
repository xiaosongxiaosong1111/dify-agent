import {useEffect,useState} from 'react';

type Result={task_id:string;planning_run_id:string;current_revision:number;input_revision:number;comparison:'same'|'different'|'missing';plan_stale:boolean;verification:'local_saved_plan_comparison';network_requested:false;task_changed:false;platform_checked:false;business_verified:false};
const keys='business_verified,comparison,current_revision,input_revision,network_requested,plan_stale,planning_run_id,platform_checked,task_changed,task_id,verification';
export default function SavedPlanComparison({taskId,runId,revision,inputRevision}:{taskId:string;runId:string;revision:number;inputRevision:number}){
 const [result,setResult]=useState<Result|null>(null),[failed,setFailed]=useState(false);
 useEffect(()=>{let current=true;const controller=new AbortController();setResult(null);setFailed(false);
  void(async()=>{try{const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/planning/${encodeURIComponent(runId)}/saved-state`,{signal:controller.signal});if(!response.ok)throw Error();const v=await response.json() as Result;
   if(!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).sort().join(',')!==keys||v.task_id!==taskId||v.planning_run_id!==runId||v.current_revision!==revision||v.input_revision!==inputRevision||!['same','different','missing'].includes(v.comparison)||typeof v.plan_stale!=='boolean'||v.verification!=='local_saved_plan_comparison'||v.network_requested!==false||v.task_changed!==false||v.platform_checked!==false||v.business_verified!==false)throw Error();if(current)setResult(v);
  }catch{if(current)setFailed(true)}})();return()=>{current=false;controller.abort()};
 },[taskId,runId,revision,inputRevision]);
 // Do not reuse an old answer for a newly selected Task or revision before the effect runs.
 const visible=result?.task_id===taskId&&result.planning_run_id===runId&&result.current_revision===revision&&result.input_revision===inputRevision?result:null;
 return <div className="callout saved-plan-comparison" role="status" style={{display:'block'}}>
  <b>{visible?.comparison==='same'?(visible.plan_stale?'当前保存图与保留候选一致，但方案已过期':'当前已保存流程与这份保留候选完全一致'):visible?.comparison==='different'?'当前已保存流程与这份保留候选不同':visible?.comparison==='missing'?'当前尚无已保存流程':failed?'当前保存状态未核实':'正在核对当前已保存流程'}</b>
  <p>下方暂停或中断状态属于原规划记录。内容一致只比较已保存流程，不证明采纳来源、确认或平台验证，也不包含未保存编辑。</p>
 </div>;
}
