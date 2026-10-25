type Material={status?:string;source_kind?:string;partial_text?:string;extraction_coverage?:{scope_note?:string}};

export default function MaterialExtraction({material}:{material:Material}){
 if(material.source_kind==='user_supplied_text'||material.source_kind==='reviewed_model_image_text')return null;
 const note=material.extraction_coverage?.scope_note;
 if(!note)return null;
 return <div className="material-extraction"><p className="hint">{note}</p>{material.status==='needs_input'&&material.partial_text&&<details><summary>查看已提取的部分文字（覆盖未确认）</summary><p className="hint">以下仅供核对，不是完整材料正文。请核对未读页；需要提供文字替代时，由你明确填写正文及覆盖范围，仍需重新确认需求。</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:300,overflow:'auto'}}>{material.partial_text}</pre></details>}</div>;
}
