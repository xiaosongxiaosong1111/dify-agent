const fields=['question','recommendation','reason','experience','cost','manual_work'] as const;
type Question=Record<typeof fields[number],string>;
type Report={schema_version:1;verification:'model_clarification_only';message:string;questions:Question[];incomplete:boolean;format_valid:boolean};
const labels={recommendation:'建议行为',reason:'理由',experience:'体验变化',cost:'费用影响',manual_work:'人工工作'};
function parse(value:unknown):Report|null{
 if(!value||typeof value!=='object'||Array.isArray(value))return null;
 const r=value as Report;
 if(Object.keys(r).sort().join(',')!=='format_valid,incomplete,message,questions,schema_version,verification'||r.schema_version!==1||r.verification!=='model_clarification_only'||typeof r.message!=='string'||!r.message.trim()||[...r.message].length>2000||typeof r.incomplete!=='boolean'||typeof r.format_valid!=='boolean'||!Array.isArray(r.questions)||r.questions.length>20)return null;
 if(r.questions.some(q=>!q||typeof q!=='object'||Array.isArray(q)||Object.keys(q).sort().join(',')!==[...fields].sort().join(',')||fields.some(f=>typeof q[f]!=='string'||[...q[f]].length>2000||(q[f].length>0&&!q[f].trim()))||!q.question.trim()))return null;
 return r;
}
export default function PlanningDecision({value,revision,currentRevision,onDiscuss}:{value:unknown;revision:number;currentRevision:number;onDiscuss?:(text:string)=>void}){
 const report=parse(value);
 if(!report)return <p className="hint">澄清记录格式无法识别，请查看保留响应；没有自动继续或代为确认。</p>;
 return <div className="planning-decision callout amber">
  <b>模型提出的待确认问题 · 输入修订 v{revision}</b>
  {currentRevision!==revision&&<p>这是历史修订的问题；当前为 v{currentRevision}，不能作为当前方案的确认。</p>}
  <p>{report.message}</p>
  {report.questions.length>0?<ol>{report.questions.map((q,i)=><li key={i}><p>{q.question}</p>{(Object.keys(labels) as (keyof typeof labels)[]).map(f=>q[f]&&<p key={f}><strong>{labels[f]}：</strong>{q[f]}</p>)}{onDiscuss&&<button type="button" className="secondary" disabled={currentRevision!==revision} onClick={()=>onDiscuss(`请先解释下面这个模型提出但尚未核实的问题，说明选择、理由以及体验、费用和人工影响。仅讨论，不替我决定或确认，不修改或执行。输入修订 v${revision}，问题 ${i+1}：\n${q.question}\n${(Object.keys(labels) as (keyof typeof labels)[]).filter(f=>q[f]).map(f=>`${labels[f]}：${q[f]}`).join('\n')}`)}>放入只读讨论框（尚未发送）</button>}</li>)}</ol>:<p>模型没有提供可展开的问题清单，请按说明补充条件。</p>}
  {(!report.format_valid||report.incomplete)&&<p>响应包含未支持、超限或无法展开的内容；以上不是完整响应，请一并核对保留的原始预览。</p>}
  <p className="hint">这些问题与建议来自模型，尚未核实。请在需求／配置中明确填写选择，再主动发起规划；不会据此修改方案、确认资源、调用模型或运行 Dify。</p>
 </div>;
}
