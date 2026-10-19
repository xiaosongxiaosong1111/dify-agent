import type {Ref} from 'react';
type Props={replaceBlocked?:boolean;editorRef?:Ref<HTMLTextAreaElement>;text:string;dirty:boolean;stale:boolean;saved:boolean;blocked:boolean;datasetIds:string[];topK:number;onChange:(s:string)=>void;onGenerate:()=>void;onSave:()=>void;onReset:()=>void};
export default function AgentPlanPanel(p:Props){
 let summary:Record<string,unknown>|null=null;try{const v=JSON.parse(p.text);if(v&&typeof v==='object'&&!Array.isArray(v))summary=v;}catch{/* Backend validates on save. */}
 return <>
  <div className="callout">生成原生 Agent 配置包，保持 Agent 应用类型。支持文本指令、模型、开场白，以及明确的知识集检索方案。知识集里的库必须与配置页所选 ID 一致；当前按 Agent 自主生成词检索，不承诺每轮必检索。自定义工具、文件、Skills、人工介入尚待适配。</div>
  <div className="callout amber">Dify 原生 Agent 会由部署提供配置 CLI／沙箱；空自定义工具列表不表示没有内建能力。请在资源方案中明确目标部署能力，导入后核对发布与 API 开启状态。</div>
  <button className="secondary full" disabled={p.blocked||p.dirty} onClick={p.onGenerate}>请求模型生成 Agent 指令方案</button>
  <button className="secondary full" disabled={p.blocked||p.dirty||p.replaceBlocked} onClick={()=>p.onChange(JSON.stringify({schema_version:1,scope:'text',system_prompt:'请填写具体职责、业务规则、信息不足处理与输出要求；本片段尚未保存或确认。'},null,2))}>填入 Agent 文本方案骨架</button>
  <button className="secondary full" disabled={p.blocked||p.dirty||p.replaceBlocked||!p.datasetIds.length} onClick={()=>p.onChange(JSON.stringify({schema_version:1,scope:'knowledge',system_prompt:'请填写具体问答职责。回答资料问题前查询所配置知识集，只使用检索支持的事实，资料不足时明确说明；不得编造或使用通用常识代替检索。',knowledge_sets:[{name:'业务资料',description:'请明确资料用途和需要检索的场景。',dataset_ids:p.datasetIds,query_mode:'generated_query',top_k:p.topK}]},null,2))}>填入已选知识库的 Agent 骨架</button>
  <label className="field"><span>Agent Plan JSON{p.dirty?' · 未保存':''}</span><textarea ref={p.editorRef} className="plan-editor" aria-label="Agent Plan JSON" spellCheck={false} value={p.text} onChange={e=>p.onChange(e.target.value)}/></label>
  <div className="state"><span>方案范围</span><b>{summary?.scope==='text'?'文本 Agent':summary?.scope==='knowledge'?'带知识集的 Agent':p.text?'待后台检查':'尚未规划'}</b></div>
  {summary&&typeof summary.system_prompt==='string'&&<details className="dsl"><summary>检查系统指令</summary><pre>{summary.system_prompt}</pre></details>}
  {summary?.scope==='knowledge'&&<details className="dsl"><summary>检查知识集和检索方案</summary><pre>{JSON.stringify(summary.knowledge_sets,null,2)}</pre></details>}
  {p.dirty&&<div className="callout amber">方案草稿尚未保存，构建／导入／运行会被阻止。</div>}
  <div className="actions"><button className="secondary" disabled={p.blocked||(!p.dirty&&!p.stale)} onClick={p.onSave}>后台校验并保存 Agent 方案</button>{(p.saved||p.dirty)&&<button className="secondary" disabled={p.blocked} onClick={p.onReset}>清除 Agent 方案</button>}</div>
 </>;
}
