import {usdText} from './MoneyText';
import { Pause, RotateCcw } from 'lucide-react';
import PlanningDecision from './PlanningDecision';
import RetainedPlanCandidate,{type RetainedDraft} from './RetainedPlanCandidate';

export type Pricing = { input_per_million_usd: number; output_per_million_usd: number; cached_input_per_million_usd?: number };
export type PlanningRun = {
  kind?: string; id: string; revision: number; result_revision?: number; status: string; model: string;
  message?: string; stop_reason?: string; estimated_cost_usd: number; elapsed_seconds?: number;
  settings: { max_retries: number; max_minutes: number; max_cost_usd: number };
  diagnostics?: string[]; last_candidate?: unknown; last_response_excerpt?: string; response_truncated?: boolean;
  decision_report?: unknown;
  scope_change_summary?:{verification:string;areas:string[];nodes:{position:string;areas:string[]}[];truncated:boolean;note:string};
  attempts: { number: number; status: string; usage: unknown; cost_basis?: string; estimated_cost_usd?: number;
    reserved_cost_usd?: number; deterministic_fixes?: string[]; diagnostics?: string[] }[];
};

const labels: Record<string, string> = {
  running: '规划中', ready_to_confirm: '准备提交候选', succeeded: '候选已保存', paused: '已暂停', interrupted: '已中断',
  pending: '已预检，等待响应', returned: '已返回', invalid: '未通过校验', valid: '静态校验通过',
  unknown_usage: '用量可能未知', not_dispatched: '未派发', needs_decision: '需要确认条件',
};

export default function PlanningProgress({ run, generating, onPause, onRefresh, currentRevision, onDiscuss, taskId, appType, candidateBlocked, onLoadCandidate }: {
  run: PlanningRun | null; generating: boolean; onPause: () => void; onRefresh: () => void; currentRevision:number; onDiscuss?:(text:string)=>void;taskId:string;appType:string;candidateBlocked:boolean;onLoadCandidate:(draft:RetainedDraft)=>boolean;
}) {
  if (!run && !generating) return null;
  const active = generating || run?.status === 'running' || run?.status === 'ready_to_confirm';
  return <section className="planning-progress">
    <div className="listhead"><b>{run ? labels[run.status] || run.status : '正在准备规划'}</b>
      <div className="actions">{active && <button className="secondary" onClick={onPause}><Pause size={13}/>暂停规划</button>}
        {!active && <button className="iconbtn" title="刷新规划记录" onClick={onRefresh}><RotateCcw size={13}/></button>}</div>
    </div>
    {run && <>
      <small>{run.kind==='repair'?'代码修复候选 · ':run.kind==='cases'?'验收样例建议 · ':run.kind==='configuration'?'具体配置建议 · ':run.kind==='coverage'?'需求覆盖建议 · ':run.kind==='conflicts'?'需求冲突建议 · ':'流程方案 · '}{run.model} · 输入修订 v{run.revision}{run.result_revision ? ` → 结果 v${run.result_revision}` : ''}</small>
      <p>本轮费用估算 {usdText(run.estimated_cost_usd)} / {usdText(run.settings.max_cost_usd)} · 上限 {run.settings.max_minutes} 分钟、{run.settings.max_retries} 次自动修复</p>
      {run.message && <div className="callout amber">{run.message}</div>}
      {run.stop_reason==='needs_decision'&&['paused','interrupted'].includes(run.status)&&run.decision_report&&<PlanningDecision value={run.decision_report} revision={run.revision} currentRevision={currentRevision} onDiscuss={onDiscuss}/>}
      {run.scope_change_summary&&<div className="callout amber planning-scope-summary"><b>修复为何暂停：候选改变了方案</b>{run.scope_change_summary.areas.map((area,i)=><p key={i}>{area}</p>)}{run.scope_change_summary.nodes.length>0&&<details><summary>查看节点变化 · {run.scope_change_summary.nodes.length} 项</summary>{run.scope_change_summary.nodes.map((node,i)=><p key={i}>{node.position}：{node.areas.join('；')}</p>)}</details>}{run.scope_change_summary.truncated&&<p>变化摘要达到上限，不能据此认为其他部分没有变化。</p>}<p className="hint">{run.scope_change_summary.note}</p></div>}
      {run.diagnostics?.length ? <details><summary>查看待处理问题</summary>{run.diagnostics.map((e, i) => <p key={i}>{e}</p>)}</details> : null}
      <details><summary>调用与修复记录 · {run.attempts.length} 次</summary>
        {run.attempts.map(a => <div className="planning-attempt" key={a.number}><b>调用 {a.number} · {labels[a.status] || a.status}</b>
          <small>{a.cost_basis === 'reserved_unknown_usage' ? '用量未知，按预留估算计入' : a.cost_basis === 'reported_usage' ? '按返回用量估算' : '调用前费用预检'} · {usdText(a.estimated_cost_usd ?? a.reserved_cost_usd ?? null)}</small>
          {a.deterministic_fixes?.map((fix, i) => <p key={i}>格式修正：{fix}</p>)}
          {a.usage ? <pre>{JSON.stringify(a.usage, null, 2)}</pre> : <p className="hint">未记录可用的供应商用量，不按零用量处理。</p>}
        </div>)}
      </details>
      {['paused', 'interrupted'].includes(run.status) && (run.last_candidate || run.last_response_excerpt) && <details><summary>查看保留候选（尚未应用）</summary><pre>{run.last_candidate ? JSON.stringify(run.last_candidate, null, 2) : run.last_response_excerpt}</pre>{run.response_truncated && <p className="hint">文本预览已截断；不能当作完整计划导入。</p>}</details>}
      {['paused','interrupted'].includes(run.status)&&(!run.kind||run.kind==='plan')&&!!run.last_candidate&&<><p className="hint">浏览器对象预览中的精确大整数可能舍入；继续编辑请读取下方候选原文，不复制上方对象预览。</p><RetainedPlanCandidate taskId={taskId} revision={currentRevision} runId={run.id} inputRevision={run.revision} appType={appType} blocked={candidateBlocked||active} onLoad={onLoadCandidate}/></>}
      <p className="hint">本记录只覆盖本轮模型建议（流程、覆盖清单、冲突检查、具体配置或验收样例）。费用基于配置单价估算，不是账单保证；候选保存后仍按修订确认，不代表 Dify 已导入或运行。</p>
      {run.kind==='repair'&&<p className="hint">本轮只生成纯计算代码候选，不自动采纳；可能改变业务行为，须核对差异后重新确认需求和配置。每次主动确认只派发一次，不自动重试、换模型或重跑 Dify。</p>}
      {!['repair','cases','configuration','coverage','conflicts'].includes(run.kind||'')&&<p className="hint">流程自动修复支持 JSON 格式，明确缺少语句头单个冒号的 Python 代码由本机修正，不为此追加模型调用；调用／索引、缩进语义、注释、节点顺序和已确认选择保持。其他语法或业务变化先暂停核对，不继续追加模型请求。这里还不是 Dify 运行后的自动修复。</p>}
    </>}
  </section>;
}
