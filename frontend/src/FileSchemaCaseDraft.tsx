import {validStructuredFileOutput,type StructuredFileOutput} from './FileStructuredOutput';
export default function FileSchemaCaseDraft({offer,disabled,canAdopt,catalogReady,onDraft}:{offer:StructuredFileOutput;disabled:boolean;canAdopt:boolean;catalogReady:boolean;onDraft:(name:string,expectation:string)=>void}){
 if(!validStructuredFileOutput(offer))return <p className="error">冻结Schema建议不完整，未生成文件样例草稿。</p>;
 const expectation=`{"mode":"json_schema","target":${JSON.stringify(offer.output_variable)},"expected":${offer.schema_text}}`;
 return <div className="file-schema-case-draft callout" style={{display:'block'}}><b>用本次冻结Schema准备文件样例</b><p>来源：{offer.node_id}.structured_output → {offer.output_variable}。填入未保存的名称与json_schema完整规则；当前文件输入保持原文。保存和单次试跑仍需你主动操作。</p><p className="hint">规则沿用冻结Schema文字，保留数字原文；这里只核对声明结构，字段真实性、提取完整性及业务含义仍需补充场景和人工核对。</p>{!catalogReady?<p className="hint">先读取并核对当前文件样例集，再重新准备这份结构化试跑方案，即可填入空白草稿；原方案因读取样例而失效时不会自动恢复。</p>:!canAdopt&&<p className="hint">当前样例草稿已有编辑，保留你的名称、规则及必选设置；恢复初始空白草稿后才能采用建议。</p>}<button className="secondary" disabled={disabled||!catalogReady||!canAdopt} onClick={()=>onDraft('文档对象Schema核对',expectation)}>将冻结输出Schema填入文件样例草稿</button></div>;
}
