import {Plus, Trash2} from 'lucide-react';
import type {ExpectationMode} from './AcceptancePanel';
export type TurnDraft={inputText:string;mode:ExpectationMode;target:string;expectedText:string;description:string};
export const newTurnDraft=():TurnDraft=>({inputText:'{\n  "query": ""\n}',mode:'contains',target:'answer',expectedText:'',description:''});
const modes=[['contains','包含关键词'],['equals','严格等值'],['json_schema','完整对象 Schema'],['json_keys','包含 JSON 字段'],['manual','人工复核']];
export default function ConversationCaseEditor({turns,onChange}: {turns:TurnDraft[];onChange:(turns:TurnDraft[])=>void}){
 const update=(index:number,patch:Partial<TurnDraft>)=>onChange(turns.map((t,i)=>i===index?{...t,...patch}:t));
 return <div className="conversation-case-editor">
  <p className="hint">追加后成为正式多轮样例：首轮新建会话，后续沿用同一实际会话；每轮都按自己的预期检查。自动规则失败时停止后续调用。最多 10 轮，增加模型费用；人工轮次需整体复核。</p>
  {turns.map((t,index)=>{const label=`第 ${index+2} 轮`;return <div className="followup-card" key={index}>
   <div className="listhead"><b>{label} · 追问</b><button type="button" className="secondary" aria-label={`移除${label}`} onClick={()=>onChange(turns.filter((_,i)=>i!==index))}><Trash2 size={13}/>移除</button></div>
   <label className="field"><span>{label}输入 JSON</span><textarea className="json case-input" aria-label={`${label}输入 JSON`} value={t.inputText} onChange={e=>update(index,{inputText:e.target.value})}/></label>
   <label className="field"><span>{label}检查方式</span><select aria-label={`${label}检查方式`} value={t.mode} onChange={e=>update(index,{mode:e.target.value as ExpectationMode})}>{modes.map(([v,n])=><option key={v} value={v}>{n}</option>)}</select></label>
   {t.mode==='manual'?<label className="field"><span>{label}人工判断标准</span><textarea aria-label={`${label}人工判断标准`} value={t.description} onChange={e=>update(index,{description:e.target.value})}/></label>:<>
    <label className="field"><span>{label}输出路径</span><input aria-label={`${label}输出路径`} value={t.target} onChange={e=>update(index,{target:e.target.value})}/></label>
    <label className="field"><span>{label}{t.mode==='json_schema'?'完整对象Schema JSON':t.mode==='equals'?'期望值 JSON':t.mode==='json_keys'?'必含字段（每行一项）':'必含关键词（每行一项）'}</span><textarea aria-label={`${label}预期`} value={t.expectedText} placeholder={t.mode==='equals'?'"上一轮的编号"':'需要命中的内容'} onChange={e=>update(index,{expectedText:e.target.value})}/></label>
   </>}
  </div>})}
  <button className="secondary full" type="button" disabled={turns.length>=9} onClick={()=>onChange([...turns,newTurnDraft()])}><Plus size={14}/>追加对话轮次</button>
 </div>
}
