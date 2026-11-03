import {useState,useEffect} from 'react';
import RecordedJson from './RecordedJson';
import IterationResults from './IterationResults';
import {useOwnedActivity} from './useActivityOwnership';
import {parseRunInputText} from './RunInputText';
import CaseSetPanel from './CaseSetPanel';
import {sameJson} from './caseSetTransport';
import { CheckCircle2, Plus, Trash2 } from 'lucide-react';
import ConversationCaseEditor, {type TurnDraft} from './ConversationCaseEditor';
import ConversationCaseResult from './ConversationCaseResult';
import RunDiagnosticPanel, {type Diagnostic} from './RunDiagnosticPanel';
import RunComparisonPanel from './RunComparisonPanel';
import SavedRunInputCopy,{type InputCopyDraft} from './SavedRunInputCopy';
import AfterSalesCaseDrafts from './AfterSalesCaseDrafts';
import {LazyWaitingRunPanel,LazySchemaCaseTemplates} from './LazyNodeEditors';

export type ExpectationMode = 'contains' | 'equals' | 'json_keys' | 'json_schema' | 'manual';
export type TestCase = {
  id: string; name: string; input: Record<string, unknown>; required: boolean;
  expectation: { mode: ExpectationMode; target?: string; expected?: unknown; description?: string };
  followups?: {input:Record<string,unknown>;expectation:TestCase['expectation']}[];
};
export type CaseDraft = {
  id: string; name: string; inputText: string; required: boolean;
  mode: ExpectationMode; target: string; expectedText: string; description: string; keywordJson?:boolean; followups?:TurnDraft[];
};
export type AcceptanceSummary = {
  revision: number;
  cases: { id: string; name: string; required: boolean; status: string; method: string; details: string; run_id: string | null }[];
  required: { total: number; passed: number; failed: number; needs_review: number; not_run: number; unknown: number; running: number };
  all_required_passed: boolean; verification: string; blockers: string[];
};
export type RunRecord = {
  app_type?:string;
  case_sequence?:{token:string;start_count:number;index:number;case_ids:string[]};
  diagnostics?:Diagnostic[];
  waiting_state?:{platform_status?:string;checked_at?:string;note?:string};
  id: string; label?: string; status?: string; kind?: string; revision?: number; app_id?:string|null; environment_id?:string; conversation_context?:{source_run_id:string;conversation_id:string;revision:number;environment_id:string};
  input?: unknown; result?: unknown; error?: string | null; output?: unknown; created_at?: string;
  test_case?: TestCase;
  evaluation?: { status: string; mode: string; details: string; actual?: unknown };
  manual_review?: { decision: string; reason: string; source: string; created_at: string };
  review_history?: unknown[];
};

const modes: { value: ExpectationMode; label: string }[] = [
  { value: 'contains', label: '包含关键词' }, { value: 'equals', label: '严格等值' },
  { value: 'json_schema', label: '完整对象 Schema' }, { value: 'json_keys', label: '包含 JSON 字段' }, { value: 'manual', label: '人工复核' },
];
const stateNames: Record<string, string> = {
  waiting_platform:'平台等待处理',platform_finished:'平台已结束，业务未验收',not_run: '未试跑', running: '运行中', failed: '未通过', unknown: '结果未知',
  passed: '通过已声明规则', needs_review: '待人工复核', success: '请求成功', pending: '执行中',
};

export function newCaseDraft(appType: string): CaseDraft {
  return { id: crypto.randomUUID(), name: '', inputText: '{\n  "query": ""\n}', required: true,
    mode: 'contains', target: appType === 'workflow' ? 'result' : 'answer', expectedText: '', description: '' };
}

function expectedDraft(expectation:TestCase['expectation']):{expectedText:string;keywordJson?:boolean}{
  const value=expectation.expected;
  if(['contains','json_keys'].includes(expectation.mode)&&!(Array.isArray(value)&&value.length>0&&value.every(x=>typeof x==='string'&&x.length>0&&x.trim()===x&&!/[\r\n]/.test(x))))return {expectedText:JSON.stringify(value,null,2)??'',keywordJson:true};
  return {expectedText:expectation.mode==='json_schema'&&typeof value==='string'?value:['equals','json_schema'].includes(expectation.mode)?JSON.stringify(value,null,2):Array.isArray(value)?value.join('\n'):String(value??'')};
}
export function casesToDrafts(cases: TestCase[]): CaseDraft[] {
  return cases.map(c => ({ id: c.id, name: c.name, inputText: JSON.stringify(c.input, null, 2),
    required: c.required !== false, mode: c.expectation.mode, target: c.expectation.target || '',
    description: c.expectation.description || '',
    ...expectedDraft(c.expectation),
    followups:c.followups?.map(t=>({inputText:JSON.stringify(t.input,null,2),mode:t.expectation.mode,target:t.expectation.target||'answer',description:t.expectation.description||'',...expectedDraft(t.expectation)})) }));
}

function draftToTurn(c:TurnDraft,prefix:string):{input:Record<string,unknown>;expectation:TestCase['expectation']}{
    let input: unknown;
    try { input = parseRunInputText(c.inputText); } catch(e) { throw Error(`${prefix}的输入：${e instanceof Error?e.message:'JSON原文无法完整核对，未保存。'}`); }
    if (!input || typeof input !== 'object' || Array.isArray(input)) throw Error(`${prefix}的输入必须是 JSON 对象。`);
    const expectation: TestCase['expectation'] = { mode: c.mode };
    if (c.mode === 'manual') {
      if (!c.description.trim()) throw Error(`${prefix}需要填写人工判断标准。`);
      expectation.description = c.description;
    } else {
      if (!c.target.trim()) throw Error(`${prefix}需要填写待检查的输出路径。`);
      expectation.target = c.target;
      if(c.mode==='json_schema'){
        if(!c.expectedText.trim())throw Error(`${prefix}需要填写完整对象Schema。`);
        expectation.expected=c.expectedText;
      } else if (c.mode === 'equals') {
        // Validate the original grammar before wrapping; do not accept extra members.
        try { JSON.parse(c.expectedText); } catch { throw Error(`${prefix}的期望值必须是有效 JSON，文本请用双引号包裹。`); }
        try { expectation.expected = parseRunInputText(`{"expected":${c.expectedText}}`).expected; } catch(e) { throw Error(`${prefix}的期望值：${e instanceof Error?e.message:'JSON原文无法完整核对，未保存。'}`); }
      } else if(c.keywordJson){
        let value:unknown;
        try{JSON.parse(c.expectedText);value=parseRunInputText(`{"expected":${c.expectedText}}`).expected}catch{throw Error(`${prefix}的关键词或字段规则须为完整JSON，未拆行、裁剪或保存。`)}
        if(!(c.mode==='contains'&&typeof value==='string'&&value.length>0)&&!(Array.isArray(value)&&value.length>0&&value.every(x=>typeof x==='string'&&x.length>0)))throw Error(`${prefix}的规则须为非空文字${c.mode==='contains'?'或文字列表':'列表'}；保留JSON类型、空格和换行，未自动转换。`);
        expectation.expected=value;
      } else {
        const entries = c.expectedText.split('\n').map(s => s.trim()).filter(Boolean);
        if (!entries.length) throw Error(`${prefix}需要至少一项关键词或字段。`);
        expectation.expected = entries;
      }
    }
    return {input:input as Record<string,unknown>,expectation};
}
export function draftsToCases(drafts:CaseDraft[]):TestCase[]{
 return drafts.map((c,i)=>{
  const prefix=`第 ${i+1} 个样例`;
  if(!c.name.trim())throw Error(`${prefix}需要填写场景名称。`);
  const first=draftToTurn(c,prefix),followups=(c.followups||[]).map((t,j)=>draftToTurn(t,`${prefix}第 ${j+2} 轮`));
  if(followups.length){
   if(followups.length>9)throw Error('每个多轮样例最多 10 轮。');
   for(const turn of [first,...followups])if(typeof turn.input.query!=='string'||!turn.input.query.trim()||'conversation_id' in turn.input)throw Error(`${prefix}每轮须有非空 query，不能手填 conversation_id。`);
  }
  return {id:c.id,name:c.name.trim(),required:c.required,...first,...(followups.length?{followups}:{})};
 });
}

export function AcceptancePanel({ taskId,revision,artifactStamp,drafts, appType, dirty, busy, canSave, onChange, onSave, onDiscard, summary,mockDependencies=[] }: {
  mockDependencies?:string[];
  taskId:string;revision:number;artifactStamp:string;
  drafts: CaseDraft[]; appType: string; dirty: boolean; busy: boolean; canSave: boolean;
  onChange: (drafts: CaseDraft[]) => void; onSave: () => void; onDiscard: () => void;
  summary: AcceptanceSummary | null;
}) {
  const update = (id: string, patch: Partial<CaseDraft>) => onChange(drafts.map(c => c.id === id ? { ...c, ...patch } : c));
  return <section className="acceptance-panel">
    <div className="paneltitle"><CheckCircle2 size={17}/><span><b>验收样例</b><small>定义输入、预期和关键分支</small></span></div>
    <CaseSetPanel taskId={taskId} revision={revision} appType={appType} draftScope={JSON.stringify(drafts)} disabled={busy||!canSave} onAppend={rows=>{if(rows.some(row=>drafts.some(d=>d.id===row.id)))return false;const added=casesToDrafts(rows);try{if(!sameJson(draftsToCases(added),rows))return false}catch{return false}onChange([...drafts,...added]);return true}}/>
    <div className="callout">保存样例后需要重新确认需求与配置；已有流程计划也需复核。关键词或结构通过只证明已声明的规则。</div><p className="hint">首轮、追问输入和严格等值期望会核对完整JSON原文；重复字段或数值舍入会阻止保存并保留草稿，不自动选最后一项、转成文字或null。长编号若需精确保留，请先明确采用文本方案。</p>
    {appType==='advanced-chat'&&<AfterSalesCaseDrafts taskId={taskId} revision={revision} scope={artifactStamp} dependencies={mockDependencies} disabled={busy||!canSave||dirty} onAppend={rows=>{
      const duplicate=rows.some(row=>drafts.some(d=>{try{return sameJson(draftToTurn(d,'原样例'),{input:row.input,expectation:row.expectation})&&sameJson((d.followups||[]).map((t,i)=>draftToTurn(t,`原样例第${i+2}轮`)),row.followups||[])}catch{return false}}));
      if(duplicate)return false;
      onChange([...drafts,...casesToDrafts(rows.map(row=>({id:crypto.randomUUID(),name:row.name,input:row.input,expectation:row.expectation,required:true,...(row.followups?{followups:row.followups}:{})})))]);return true;
    }}/>}
    {drafts.map((c, i) => <fieldset className="case-card" key={c.id} disabled={busy}>
      <legend>样例 {i + 1}</legend>
      <label className="field"><span>场景名称</span><input value={c.name} placeholder="例如：知识库无结果时说明不足" onChange={e => update(c.id, { name: e.target.value })}/></label>
      <label className="field"><span>样例输入 JSON</span><textarea aria-label="样例输入 JSON" className="json case-input" spellCheck={false} value={c.inputText} onChange={e => update(c.id, { inputText: e.target.value })}/></label>
      <label className="field"><span>检查方式</span><select aria-label="检查方式" value={c.mode} onChange={e => update(c.id, { mode: e.target.value as ExpectationMode })}>{modes.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}</select></label>
      {c.mode === 'manual' ? <label className="field"><span>人工判断标准</span><textarea aria-label="人工判断标准" value={c.description} placeholder="描述需要人工检查的具体行为" onChange={e => update(c.id, { description: e.target.value })}/></label> : <>
        <label className="field"><span>输出路径</span><input value={c.target} placeholder={appType === 'advanced-chat' ? 'answer' : 'result 或 data.summary'} onChange={e => update(c.id, { target: e.target.value })}/></label>
        <label className="field"><span>{c.mode === 'json_schema' ? '完整对象 Schema JSON' : c.mode === 'equals' ? '期望值 JSON' : c.keywordJson ? '关键词／字段规则 JSON（保留原格式）' : c.mode === 'json_keys' ? '必含字段（每行一项）' : '必含关键词（每行一项）'}</span><textarea aria-label={c.mode === 'json_schema' ? '完整对象 Schema JSON' : c.mode === 'equals' ? '期望值 JSON' : c.keywordJson ? '关键词／字段规则 JSON（保留原格式）' : c.mode === 'json_keys' ? '必含字段（每行一项）' : '必含关键词（每行一项）'} spellCheck={false} value={c.expectedText} placeholder={c.mode === 'json_schema' ? '明确闭合对象Schema，不自动补字段' : c.mode === 'equals' ? '"保修一年" 或 {"ok":true}' : c.mode === 'json_keys' ? 'summary\nconfidence' : '一年\n人工客服'} onChange={e => update(c.id, { expectedText: e.target.value })}/></label>
      </>}
      {c.keywordJson&&['contains','json_keys'].includes(c.mode)&&<p className="hint">按JSON原样编辑，保留原字符串／列表类型及关键词内部的空格和换行，不拆成多项；仅修改名称等字段不会改变原匹配规则。</p>}
      {c.mode==='json_schema'&&<p className="hint">核对返回对象或严格JSON对象文字的完整Schema（必填、类型、额外字段、范围）。不修复JSON、不补默认；不证明Dify入口强制、模型事实正确或客户业务通过。仅已适配闭合对象子集；对象及Schema各64000字节，整数须在无损范围内。Schema文字保留重复键，保存时后台明确拒绝。</p>}
      {['advanced-chat','agent'].includes(appType)&&<ConversationCaseEditor turns={c.followups||[]} onChange={followups=>update(c.id,{followups})}/>}
      <div className="case-actions"><label className="case-required"><input type="checkbox" checked={c.required} onChange={e => update(c.id, { required: e.target.checked })}/>必选验收样例</label><button className="secondary" type="button" onClick={() => onChange(drafts.filter(x => x.id !== c.id))}><Trash2 size={14}/>移除样例 {i + 1}</button></div>
    </fieldset>)}
    {!drafts.length && <div className="empty-small bordered">还没有验收样例。建议覆盖正常输入、无检索结果、异常和关键业务分支。</div>}
    {appType==='workflow'&&<LazySchemaCaseTemplates taskId={taskId} revision={revision} artifactStamp={artifactStamp} disabled={busy||!canSave} onCreate={(target,schema)=>onChange([...drafts,{...newCaseDraft(appType),name:`结构验收 ${target}`,inputText:'{}',mode:'json_schema',target,expectedText:typeof schema==='string'?schema:JSON.stringify(schema,null,2)}])}/>}
    <button className="secondary full" disabled={busy} onClick={() => onChange([...drafts, newCaseDraft(appType)])}><Plus size={14}/>新增验收样例</button>
    {dirty && <div className="callout amber">验收样例有未保存编辑。构建、导入和运行暂时不可用，切换面板会保留草稿。</div>}
    <div className="actions"><button className="primary" disabled={!dirty || busy || !canSave} onClick={onSave}>保存验收样例</button><button className="secondary" disabled={!dirty || busy} onClick={onDiscard}>撤销样例编辑</button></div>
    {summary && <div className="acceptance-summary">
      <b>当前修订 v{summary.revision} · 必选样例 {summary.required.passed} / {summary.required.total} 通过</b>
      {summary.cases.map(c => <div className="case-result" key={c.id}><b>{c.name}{c.required ? ' · 必选' : ' · 可选'}</b><span className={`result-state ${c.status}`}>{c.method === 'human' ? `人工确认${c.status === 'passed' ? '通过' : '未通过'}` : stateNames[c.status] || c.status}</span><small>{c.details}</small></div>)}
      {summary.blockers.map((b, i) => <p className="hint" key={i}>{b}</p>)}
    </div>}
  </section>;
}

export function RunHistory({ currentAppId, runs, revision, busy, hasUnsaved, reasons, onReason, onReview, taskId, onActivity:reportActivity, onUpdated, onLocateNode,onPrepareRun,inputDraft,inputSelectionScope,onCopyInput }: {
  inputDraft?:string;inputSelectionScope?:string;onCopyInput?:(draft:InputCopyDraft)=>boolean;
  currentAppId?:string|null;taskId?:string;onLocateNode?:(nodeId:string,section?:string)=>void;onActivity?:(label:string)=>void;onUpdated?:(task:unknown)=>void;onPrepareRun?:(recipe:{input:Record<string,unknown>;case_id:string|null})=>void;
  runs: RunRecord[]; revision: number; busy: boolean; hasUnsaved: boolean;
  reasons: Record<string, string>; onReason: (id: string, reason: string) => void;
  onReview: (id: string, decision: 'passed' | 'failed') => void;
}) {
 const onActivity=useOwnedActivity(reportActivity,`${taskId}:${revision}`);
 const [filters,setFilters]=useState({taskId,revisionOnly:false,appOnly:false,status:'all'}),[windowState,setWindowState]=useState<{scope:string;anchor:string|null}>({scope:'',anchor:null});
 useEffect(()=>{setFilters({taskId,revisionOnly:false,appOnly:false,status:'all'});setWindowState({scope:'',anchor:null})},[taskId]);
 useEffect(()=>setWindowState({scope:'',anchor:null}),[revision,currentAppId]);
 const currentFilters=filters.taskId===taskId?filters:{taskId,revisionOnly:false,appOnly:false,status:'all'};
 const scope=JSON.stringify([taskId,revision,currentAppId,currentFilters.revisionOnly,currentFilters.appOnly,currentFilters.status]);
 const filtered=[...runs].reverse().filter(run=>(!currentFilters.revisionOnly||run.revision===revision)&&(!currentFilters.appOnly||!!currentAppId&&run.app_id===currentAppId)&&(currentFilters.status==='all'||currentFilters.status==='failed'&&(['error','failed','not_passed'].includes(run.status||'')||run.evaluation?.status==='failed'||run.manual_review?.decision==='failed')||currentFilters.status==='attention'&&(!run.status||['unknown','pending','running','waiting_platform','platform_finished','paused'].includes(run.status))||currentFilters.status==='success'&&run.status==='success'));
 const anchor=windowState.scope===scope?windowState.anchor:null,anchorIndex=anchor?filtered.findIndex(run=>run.id===anchor):0,anchorLost=!!anchor&&anchorIndex<0,start=Math.max(0,anchorIndex),visible=filtered.slice(start,start+20);
 const move=(offset:number)=>setWindowState({scope,anchor:offset<=0?null:filtered[offset]?.id??null});
 const changeFilter=(patch:Partial<typeof currentFilters>)=>{setWindowState({scope:'',anchor:null});setFilters({...currentFilters,...patch})};

  return <div className="history run-history">{taskId&&<RunComparisonPanel taskId={taskId} revision={revision} runs={runs} blocked={busy||hasUnsaved}/>} <section className="run-history-window"><b>已保存运行记录</b><p role="status">全部保存{runs.length}条，当前筛选{filtered.length}条，本窗{filtered.length?start+1:0}—{start+visible.length}，每窗最多20条，按保存顺序从新到旧。</p><label><input type="checkbox" aria-label="运行历史只看当前修订" checked={currentFilters.revisionOnly} onChange={e=>changeFilter({revisionOnly:e.target.checked})}/> 只看当前修订</label><label><input type="checkbox" aria-label="运行历史只看当前App" checked={currentFilters.appOnly} disabled={!currentAppId&&!currentFilters.appOnly} onChange={e=>changeFilter({appOnly:e.target.checked})}/> 只看当前App</label><label className="field"><span>记录状态范围</span><select aria-label="运行历史状态范围" value={currentFilters.status} onChange={e=>changeFilter({status:e.target.value})}><option value="all">全部记录</option><option value="failed">运行错误或规则／人工未通过</option><option value="attention">未知／处理中／待核对</option><option value="success">原返回成功（不等于业务通过）</option></select></label><p className="hint">筛选仅读取保存状态，不重评或派发。旧修订／其他App仍可选全部查看；不同记录的成功、规则与人工意见不合并为业务结论。</p>{anchorLost&&<p role="status">原窗口首记录已不在当前筛选，已显示最近窗口；请按当前记录重新定位。</p>}{anchor&&start>0&&<p className="hint">当前窗口按原首记录定位，有{start}条较新筛选记录；新到记录不强行切走。</p>}{!visible.length&&<p>当前筛选没有记录，不代表任务从未运行；可取消条件查看全部保存记录。</p>}<div className="actions"><button className="secondary" disabled={start===0&&!anchorLost} onClick={()=>move(0)}>最近运行记录</button><button className="secondary" disabled={start===0} onClick={()=>move(Math.max(0,start-20))}>较新20条运行记录</button><button className="secondary" disabled={start+20>=filtered.length} onClick={()=>move(start+20)}>更早20条运行记录</button></div></section>{visible.map(run => <details key={run.id} data-run-id={run.id}>
    <summary>{run.test_case?.name || run.label || (run.kind === 'import' ? '导入记录' : '自由试跑')} · v{run.revision ?? '未知'} · {stateNames[run.status || ''] || run.status || '未知'}</summary>
    {run.revision !== revision && <div className="callout amber">旧修订记录，仅作参考，不计入当前样例汇总。</div>}
    {run.error && <div className="alert error">{run.error}</div>}
    {run.conversation_context&&<div className="callout">本轮复用会话 {run.conversation_context.conversation_id}，来源记录 {run.conversation_context.source_run_id}。上下文属于实际输入，不作为固定样例通过数。</div>}
    {run.test_case && <><b>运行时样例与输入快照</b><RecordedJson value={run.test_case} scope={JSON.stringify([taskId,revision,run.id,'case'])} label="样例输入快照"/></>}
    {taskId&&onCopyInput&&inputDraft!==undefined&&<SavedRunInputCopy taskId={taskId} revision={revision} run={run} input={inputDraft} selectionScope={inputSelectionScope||''} blocked={busy||hasUnsaved} onAdopt={onCopyInput}/>}
    {run.kind==='run'&&<p className="hint">用量及价格来自 Dify 返回。插件价格为 0 不证明供应商免费；实际费用需核对供应商账单，本次规划上限不覆盖这些运行费用。</p>}
    {taskId&&onUpdated&&['waiting_platform','platform_finished'].includes(run.status||'')&&<LazyWaitingRunPanel taskId={taskId} run={run} blocked={busy||hasUnsaved} onUpdated={onUpdated}/>}
    <ConversationCaseResult value={run.result}/>
    {taskId&&run.kind==='run'&&run.app_type==='workflow'&&<IterationResults taskId={taskId} revision={revision} run={run} currentAppId={currentAppId} blocked={busy||hasUnsaved}/>}
    <b>实际返回结果</b><RecordedJson value={run.result ?? run.output ?? run.input} scope={JSON.stringify([taskId,revision,run.id,'result'])} label="实际返回结果"/>
    {run.evaluation && <div className={`validation ${run.evaluation.status === 'passed' ? 'ok' : 'bad'}`}><b>{stateNames[run.evaluation.status] || run.evaluation.status}</b><p>{run.evaluation.details}</p></div>}
    {taskId&&reportActivity&&onUpdated&&<RunDiagnosticPanel currentAppId={currentAppId} taskId={taskId} revision={revision} run={run} blocked={busy||hasUnsaved} onActivity={onActivity} onUpdated={onUpdated} onLocateNode={onLocateNode} onPrepareRun={onPrepareRun}/>}
    {run.manual_review && <div className="callout"><b>人工确认{run.manual_review.decision === 'passed' ? '通过' : '未通过'}</b><p>{run.manual_review.reason}</p><small>{new Date(run.manual_review.created_at).toLocaleString('zh-CN')}</small></div>}
    {run.revision === revision && run.status === 'success' && run.evaluation?.mode === 'manual' && <div className="manual-review">
      <label className="field"><span>人工复核意见</span><textarea aria-label="人工复核意见" value={reasons[run.id] || ''} onChange={e => onReason(run.id, e.target.value)} placeholder="核对全部轮次输入、每项人工标准和实际结果后填写具体理由" maxLength={2000}/></label>
      <div className="actions"><button className="primary" disabled={busy || hasUnsaved || !reasons[run.id]?.trim()} onClick={() => onReview(run.id, 'passed')}>人工确认通过</button><button className="secondary" disabled={busy || hasUnsaved || !reasons[run.id]?.trim()} onClick={() => onReview(run.id, 'failed')}>人工确认不通过</button></div>
      <p className="hint">意见会留存历史；只影响这次人工样例检查，不代表整个应用已交付。</p>
    </div>}
  </details>)}</div>;
}
