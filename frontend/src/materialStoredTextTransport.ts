export type TextEntry={state:'available'|'empty'|'missing'|'oversized'|'unavailable';source_length:number|null;source_bytes:number|null;content_sha256:string|null;note:string};
export type StoredTextIndex={schema_version:1;task_id:string;revision:number;material_id:string;source_sha256:string|null;status:unknown;source_token:string;entries:Record<'text'|'partial_text',TextEntry>;source_metadata:{source_kind:string;source_file_parsed:boolean;source_coverage_note:unknown;image_uncertainties:unknown[]};note:string};
export type TextMaterial={id:string;sha256?:string;status?:string;source_kind?:string;source_coverage_note?:string;reference_mode?:string|null;preserve_items?:string;extraction_coverage?:{scope_note?:string};text_view?:StoredTextIndex};
export const digest=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const count=(v:unknown):v is number=>Number.isSafeInteger(v)&&Number(v)>=0;
const failure=()=>Error('保存文字的来源、范围或页摘要无法核对，请刷新任务后重新读取。');
export function validateTextIndex(v:unknown,taskId:string,revision:number,material:TextMaterial,page=false):asserts v is StoredTextIndex{
 if(!object(v)||v.schema_version!==1||v.task_id!==taskId||v.revision!==revision||v.material_id!==material.id||v.source_sha256!==(digest(material.sha256)?material.sha256:null)||v.status!==material.status||!digest(v.source_token)||v.verification!==(page?'saved_material_text_page_only':'saved_material_text_index_only')||['task_modified','model_called','external_network_requested','original_file_rechecked','material_reparsed','business_verified'].some(k=>v[k]!==false)||typeof v.note!=='string'||!object(v.entries)||Object.keys(v.entries).sort().join(',')!=='partial_text,text')throw failure();
 const source=v.source_metadata;
 const kind=['user_supplied_text','reviewed_model_image_text'].includes(material.source_kind||'')?material.source_kind:'file_text_parser';
 if(!object(source)||source.source_kind!==kind||source.source_file_parsed!==(kind==='file_text_parser'&&material.status==='parsed')||!Array.isArray(source.image_uncertainties)||typeof source.image_model_response_received!=='boolean')throw failure();
 for(const field of ['text','partial_text']){
  const entry=v.entries[field];if(!object(entry)||!['available','empty','missing','oversized','unavailable'].includes(String(entry.state))||typeof entry.note!=='string'||!(entry.source_length===null||count(entry.source_length))||!(entry.source_bytes===null||count(entry.source_bytes))||!(entry.content_sha256===null||digest(entry.content_sha256)))throw failure();
  if(entry.state==='available'&&(!count(entry.source_length)||entry.source_length<1||!count(entry.source_bytes)||entry.source_bytes<entry.source_length||entry.source_bytes>2_000_000||!digest(entry.content_sha256)))throw failure();
  if(['empty','missing'].includes(String(entry.state))&&(entry.source_length!==0||entry.source_bytes!==0))throw failure();
 }
}
export async function validateTextPage(v:unknown,index:StoredTextIndex,material:TextMaterial,field:'text'|'partial_text',offset:number){
 validateTextIndex(v,index.task_id,index.revision,material,true);const page=v as unknown as Record<string,unknown>,source=index.entries[field];
 if(page.source_token!==index.source_token||JSON.stringify(page.entries)!==JSON.stringify(index.entries)||JSON.stringify(page.source_metadata)!==JSON.stringify(index.source_metadata)||source.state!=='available'||page.field!==field||page.page_start!==offset||page.page_size_limit!==4000||typeof page.content_chunk!=='string'||page.content_chunk.length>8000||!digest(page.page_sha256))throw failure();
 const length=Array.from(page.content_chunk).length,end=offset+length,total=source.source_length!;
 if(length!==Math.min(4000,total-offset)||length<1||page.page_end!==end||page.has_previous!==(offset>0)||page.has_next!==(end<total)||page.complete_field!==(offset===0&&end===total)||page.partial_extraction!==(field==='partial_text'))throw failure();
 const sha=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(page.content_chunk)))).map(n=>n.toString(16).padStart(2,'0')).join('');if(sha!==page.page_sha256)throw failure();
 return {text:page.content_chunk,start:offset,end,total};
}
