import type {AcceptanceSummary,RunRecord} from './AcceptancePanel';
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const result=(r:RunRecord)=>object(r.result)?r.result:{};
type Scope={artifact?:unknown;requirements_confirmed?:boolean;configuration_confirmed?:boolean;plan_stale?:boolean;revision:number;environment_id:string|null;dify_app_id?:string|null;runs:RunRecord[]};
export function savedAppProgress(task:Scope){
 const artifact=object(task.artifact)?task.artifact:null;
 const built=task.requirements_confirmed===true&&task.configuration_confirmed===true&&task.plan_stale!==true&&!!artifact&&artifact.revision===task.revision&&object(artifact.validation)&&artifact.validation.valid===true;
 const appId=task.dify_app_id||'';
 const bound=!!appId.trim()&&!!task.environment_id;
 const rows=bound?task.runs.filter(r=>r.revision===task.revision&&r.environment_id===task.environment_id):[];
 const imported=rows.some(r=>r.kind==='import'&&r.status==='success'&&result(r).app_id===appId);
 const publications=rows.filter(r=>r.kind==='publish'&&r.app_id===appId&&result(r).app_id===appId),last=publications.at(-1);
 const value=last?result(last):{};
 const publishedWorkflowId=last?.status==='success'&&value.state==='succeeded'&&typeof value.workflow_id==='string'&&value.workflow_id.trim()?value.workflow_id:null;
 const publicationUncertain=!!last&&['pending','unknown'].includes(last.status||'');
 const successfulRunIds=rows.filter(r=>r.kind==='run'&&r.app_id===appId&&r.status==='success').map(r=>r.id);
 const successfulRuns=successfulRunIds.length;
 return {appId,revision:task.revision,built,imported,publishedWorkflowId,publicationUncertain,successfulRuns,successfulRunIds};
}
export default function SavedAppProgress({value,runtimeKeyPaired,summary,blocked,onReport}:{value:ReturnType<typeof savedAppProgress>;runtimeKeyPaired:boolean;summary:AcceptanceSummary|null;blocked:boolean;onReport:()=>void}){
 const current=summary?.revision===value.revision&&summary.cases.filter(c=>c.status==='passed').every(c=>!!c.run_id&&value.successfulRunIds.includes(c.run_id))?summary:null;
 return <section className="saved-app-progress configuration-proposal"><div className="listhead"><b>当前App已保存进度</b><small>仅读本机记录</small></div><p>r{value.revision} · App {value.appId||'尚未导入'}</p>{blocked&&<p className="callout amber">当前有未保存编辑或确认条件待复核；以下仅为已保存修订记录，不代表编辑后的方案已验证。</p>}<ul><li>{value.imported?'已有匹配的成功导入记录。':'尚无当前修订与App匹配的成功导入记录。'}</li><li>{value.publishedWorkflowId?`已保存发布成功回执，图ID：${value.publishedWorkflowId}。`:value.publicationUncertain?'发布结果尚未确认，请核对原记录，禁止重复发布。':'尚无当前App的发布成功回执；不从其他App或试跑推断。'}</li><li>{runtimeKeyPaired?'本机已有与当前App配对的加密运行Key，无需再次创建。':'本机尚无与当前App配对的运行Key。'}</li><li>当前App成功运行返回 {value.successfulRuns} 次；{current?`已声明必选样例 ${current.required.passed} / ${current.required.total} 通过。`:'样例汇总尚未读取，不推断通过。'}</li></ul><p className="hint">发布与Key记录不是Dify实时状态；外部编辑、删除或撤销仍须核对。规则通过不代表全部业务验收，刷新不会发布、创建Key或试跑。</p>{current?.all_required_passed&&<p>已声明必选样例已通过，接下来核对输出、未覆盖场景和交付说明。</p>}<button className="secondary" disabled={blocked} onClick={onReport}>下载当前交付说明</button></section>;
}
