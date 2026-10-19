export default function ConversationCaseResult({value}: {value:unknown}){
 if(!value||typeof value!=='object')return null;
 const result=value as {conversation_case?:boolean;turns?:{index:number;input?:unknown;result?:{answer?:string;conversation_id?:string};evaluation?:{status?:string;details?:string}}[];pending_turn?:{index:number};stop_reason?:string;complete?:boolean};
 if(!result.conversation_case||!Array.isArray(result.turns))return null;
 return <section className="conversation-case-result"><b>逐轮验收结果</b>
  {result.turns.map(t=><div className="followup-card" key={t.index}><b>第 {t.index} 轮 · {t.evaluation?.status==='passed'?'规则通过':t.evaluation?.status==='failed'?'规则未通过':'待人工复核'}</b><p className="hint">实际会话：{t.result?.conversation_id||'尚未返回'}</p><pre>{JSON.stringify(t.input,null,2)}</pre><p className="turn-answer">{t.result?.answer}</p><p className="hint">{t.evaluation?.details}</p></div>)}
  {result.pending_turn&&<div className="callout amber">第 {result.pending_turn.index} 轮已派发或待核对，请查看运行状态，结果未知时不能重复运行。</div>}
  {result.stop_reason&&<div className="callout amber">{result.stop_reason==='rule_failed'?'自动规则未通过，后续轮次未派发。':result.stop_reason==='paused'?'已暂停，剩余轮次未派发。':'已达到采集时间上限。'}</div>}
  {!result.complete&&<p className="hint">轮次未全部完成，不能按完整多轮样例通过。</p>}
 </section>
}
