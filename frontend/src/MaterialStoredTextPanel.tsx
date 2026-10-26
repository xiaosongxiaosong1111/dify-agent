import {useEffect,useRef,useState} from 'react';
import {validateTextIndex,validateTextPage,type StoredTextIndex,type TextMaterial} from './materialStoredTextTransport';
type Page={text:string;start:number;end:number;total:number};
export default function MaterialStoredTextPanel({taskId,revision,material}:{taskId:string;revision:number;material:TextMaterial}){
 const [index,setIndex]=useState<StoredTextIndex|null>(null),[page,setPage]=useState<Page|null>(null),[field,setField]=useState<'text'|'partial_text'>('text'),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const generation=useRef(0),controller=useRef<AbortController|null>(null);
 const scope=JSON.stringify([taskId,revision,material.id,material.sha256,material.status,material.source_kind,material.source_coverage_note,material.reference_mode,material.preserve_items,material.extraction_coverage,material.text_view?.source_token]);
 const activeScope=useRef(scope);activeScope.current=scope;
 useEffect(()=>{generation.current++;controller.current?.abort();setIndex(null);setPage(null);setError('');setBusy(false);return()=>{generation.current++;controller.current?.abort()}},[scope]);
 async function read(selected?:'text'|'partial_text',offset=0){
  controller.current?.abort();const abort=new AbortController();controller.current=abort;const ticket=++generation.current;setBusy(true);setError('');
  const current=()=>ticket===generation.current&&activeScope.current===scope&&!abort.signal.aborted;
  async function request(endpoint:string,body:Record<string,unknown>){const response=await fetch(`${import.meta.env.VITE_API_BASE||'/api'}/tasks/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(material.id)}/stored-text/${endpoint}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store',signal:abort.signal});if(!response.ok){if(response.status===409&&current()){setPage(null);setIndex(null)}let message=`文字读取失败（HTTP ${response.status}）`;try{const value=await response.json();if(typeof value.detail==='string')message=value.detail}catch{}throw Error(message)}return response.json()}
  try{
   const base={revision,source_sha256:material.sha256&&/^[a-f0-9]{64}$/.test(material.sha256)?material.sha256:null};
   let meta=index;
   if(!meta){const value:unknown=await request('index',{...base,source_token:material.text_view?.source_token??null});validateTextIndex(value,taskId,revision,material);meta=value;if(current())setIndex(meta)}
   if(!current())return;
   if(selected){const value=await request('page',{...base,source_token:meta.source_token,field:selected,offset});const checked=await validateTextPage(value,meta,material,selected,offset);if(current()){setField(selected);setPage(checked)}}
  }catch(e){if(current())setError(e instanceof Error?e.message:'保存文字无法核对。')}finally{if(current())setBusy(false)}
 }
 return <div className="material-stored-text">
  <button className="secondary" disabled={busy} onClick={()=>void read()}>核对保存的材料文字</button>
  {busy&&<p role="status">正在读取保存文字……</p>}{error&&<p role="alert" className="callout amber">{error}</p>}
  {index&&<div><p className="hint">{index.source_metadata.source_kind==='user_supplied_text'?'用户补充文字／原文件未解析':index.source_metadata.source_kind==='reviewed_model_image_text'?'人工核对图像候选／非OCR':'文件文字提取记录'}；{typeof index.source_metadata.source_coverage_note==='string'?index.source_metadata.source_coverage_note:'覆盖范围未记录，不能推断已完整读取。'}</p>
   {index.source_metadata.image_uncertainties.length>0&&<p className="hint">原图像未知项：{index.source_metadata.image_uncertainties.filter(v=>typeof v==='string').join('；')}</p>}
   <p className="hint">{index.note}</p><div className="actions">{(['text','partial_text'] as const).map(key=><button key={key} className="secondary" disabled={busy||index.entries[key].state!=='available'} onClick={()=>void read(key)}>{key==='text'?'读取已保存正文':'读取原解析片段（未确认）'}</button>)}</div>
   {(['text','partial_text'] as const).map(key=><p className="hint" key={key}>{key==='text'?'保存正文':'原解析片段'}：{index.entries[key].note}{index.entries[key].source_length!==null&&`（${index.entries[key].source_length}码点）`}</p>)}
   {page&&<div data-testid="material-text-page"><b>{field==='partial_text'?'原解析片段／未确认，不是当前采用正文':'保存正文／按上述来源理解'}</b><p className="hint">码点 {page.start+1}–{page.end} / {page.total}；本页摘要已核对，完整字段来源由服务端指纹绑定，浏览器未独立核对全部字段。未重新读取原文件。</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:300,overflow:'auto'}}>{page.text}</pre><div className="actions"><button className="secondary" disabled={busy||page.start===0} onClick={()=>void read(field,0)}>文字首页</button><button className="secondary" disabled={busy||page.start===0} onClick={()=>void read(field,Math.max(0,page.start-4000))}>文字上一页</button><button className="secondary" disabled={busy||page.end===page.total} onClick={()=>void read(field,page.end)}>文字下一页</button><button className="secondary" disabled={busy||page.end===page.total} onClick={()=>void read(field,Math.floor((page.total-1)/4000)*4000)}>文字末页</button></div></div>}
  </div>}
 </div>;
}
