import {useEffect,useRef,useState} from 'react';
import {useOwnedActivity} from './useActivityOwnership';
type Material={id:string;sha256?:string;name?:string;filename?:string;status?:string;reference_mode?:string|null;preserve_items?:string};
type Change={id:string;source_sha256:string;reference_mode:string;preserve_items:string};
type Row={id:string;source_sha256:string;name:string;status:string;source_token:string;before:{reference_mode:string|null;preserve_items:string};after:{reference_mode:string;preserve_items:string};changed:boolean};
type Preview={schema_version:1;task_id:string;revision:number;items:Row[];changed_count:number;review_token:string;note:string};
const modes:Record<string,string>={borrow:'借鉴思路',preserve:'保留指定部分',replicate:'严格复现'};
const hash=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
export default function MaterialReferenceBatchPanel({taskId,revision,materials,blocked,onActivity:report,onUpdated}:{taskId:string;revision:number;materials:Material[];blocked:boolean;onActivity:(label:string)=>void;onUpdated:(value:unknown)=>void}){
 const activity=useOwnedActivity(report,`${taskId}:${revision}`),[items,setItems]=useState<Change[]>([]),[preview,setPreview]=useState<Preview|null>(null),[ack,setAck]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),latest=useRef({onUpdated,activity});latest.current={onUpdated,activity};
 const scope=JSON.stringify([taskId,revision,materials.map(m=>[m.id,m.sha256,m.name,m.filename,m.status,m.reference_mode,m.preserve_items])]),activeScope=useRef(scope);activeScope.current=scope;
 useEffect(()=>{epoch.current++;setItems([]);setPreview(null);setAck(false);setBusy(false);setError('');return()=>{epoch.current++;activity('')}},[scope]);
 function edit(next:Change[]){epoch.current++;setItems(next);setPreview(null);setAck(false);setError('')}
 async function request(apply=false){
  if(blocked||busy)return;const ticket=++epoch.current,decision=items.map(item=>({...item}));setBusy(true);setError('');activity(apply?'保存逐份材料引用方式':'预览逐份材料引用方式');
  const current=()=>ticket===epoch.current&&activeScope.current===scope;
  try{
   const body={revision,items:decision,...(apply?{review_token:preview?.review_token,acknowledge:ack}:{})};const response=await fetch(`${import.meta.env.VITE_API_BASE||'/api'}/tasks/${encodeURIComponent(taskId)}/materials/reference-batch/${apply?'apply':'preview'}`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),cache:'no-store'});const value=await response.json();if(!current())return;
   if(!response.ok){if(response.status===409){setPreview(null);setAck(false)}throw Error(typeof value.detail==='string'?value.detail:'材料引用方案未完成，请核对原记录，不自动重试。')}
   if(apply){
    if(value.id!==taskId||value.revision!==revision+1||!Array.isArray(value.materials)||decision.some(item=>{const rows=value.materials.filter((m:Material)=>m.id===item.id);return rows.length!==1||rows[0].sha256!==item.source_sha256||rows[0].reference_mode!==item.reference_mode||rows[0].preserve_items!==item.preserve_items.trim()}))throw Error('保存回执归属或逐份设置无法核对，请刷新原任务，不自动重传。');
    latest.current.onUpdated(value);return;
   }
   if(value.schema_version!==1||value.task_id!==taskId||value.revision!==revision||!Array.isArray(value.items)||value.items.length!==decision.length||!hash(value.review_token)||typeof value.note!=='string'||['task_modified','original_files_changed','model_called','external_network_requested','business_verified'].some(k=>value[k]!==false))throw Error('材料引用预览归属或只读范围不匹配，未启用保存。');
   let changes=0;
   for(let i=0;i<decision.length;i++){
    const proposed=decision[i],row=value.items[i] as Row,original=materials.find(m=>m.id===proposed.id);
    if(!row||!original||row.id!==proposed.id||row.source_sha256!==proposed.source_sha256||row.name!==(original.name??original.filename??original.id)||row.status!==original.status||!hash(row.source_token)||row.before?.reference_mode!==(original.reference_mode??null)||row.before?.preserve_items!==(original.preserve_items??'')||row.after?.reference_mode!==proposed.reference_mode||row.after?.preserve_items!==proposed.preserve_items.trim()||row.changed!==(row.before.reference_mode!==row.after.reference_mode||row.before.preserve_items!==row.after.preserve_items))throw Error('逐份预览与本页原设置/选择不一致，未启用保存。');
    if(row.changed)changes++;
   }
   if(value.changed_count!==changes)throw Error('材料变更数量不一致，未启用保存。');setPreview(value);setAck(false);
  }catch(e){if(current()){setPreview(null);setAck(false);setError(e instanceof Error?e.message:'材料引用操作失败；请核对，不自动重试。')}}finally{if(current()){setBusy(false);activity('')}}
 }
 const valid=items.length>0&&items.every(item=>!!modes[item.reference_mode]&&(item.reference_mode!=='preserve'||item.preserve_items.trim())&&Array.from(item.preserve_items).length<=300);
 return <section className="material-reference-batch"><p className="hint">每次最多10份，每份须主动选择引用方式；保留说明最多300码点，更长请用原单份入口。预览不保存；明确保存才生成一次新修订并使相关确认失效。未选材料和原件保持，未解析材料不因此算已读。关闭不会保存草稿，也不能取消已派发保存，请先核对原记录再操作。</p><fieldset disabled={blocked||busy}>{materials.map(material=>{const chosen=items.find(item=>item.id===material.id),available=hash(material.sha256)&&/^[A-Za-z0-9_-]{1,64}$/.test(material.id);return <div className="reference-batch-row" key={material.id}><label><input type="checkbox" aria-label={`选择材料 ${material.name||material.filename||material.id}`} checked={!!chosen} disabled={!available} onChange={e=>{if(e.target.checked){if(items.length>=10){setError('一次最多选择10份，未截断或替换已选材料。');return}edit([...items,{id:material.id,source_sha256:material.sha256!,reference_mode:'',preserve_items:''}])}else edit(items.filter(item=>item.id!==material.id))}}/>{material.name||material.filename||material.id} · {material.status||'状态未知'}</label><p className="hint">原设置：{modes[material.reference_mode||'']||'未明确'}{material.preserve_items?`；${material.preserve_items}`:''}{!available?'；保存摘要或ID缺失，不能在本批猜测来源，请用原记录核对。':''}</p>{chosen&&<><label className="field"><span>本份引用方式</span><select aria-label={`引用方式 ${material.name||material.id}`} value={chosen.reference_mode} onChange={e=>edit(items.map(item=>item.id===material.id?{...item,reference_mode:e.target.value,preserve_items:''}:item))}><option value="">请主动选择</option>{Object.entries(modes).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>{chosen.reference_mode==='preserve'&&<label className="field"><span>本份指定保留内容</span><textarea aria-label={`保留说明 ${material.name||material.id}`} maxLength={2400} value={chosen.preserve_items} onChange={e=>edit(items.map(item=>item.id===material.id?{...item,preserve_items:e.target.value}:item))}/>{Array.from(chosen.preserve_items).length>300&&<p role="alert">保留说明超过300码点，未截断或派发。</p>}</label>}</>}</div>})}<button className="secondary" disabled={!valid} onClick={()=>void request()}>预览所选材料引用变化</button></fieldset>
 {busy&&<p role="status">正在核对逐份引用方案……</p>}{error&&<p role="alert" className="callout amber">{error}</p>}
 {preview&&<div className="material-reference-preview"><p role="status">所选{preview.items.length}份，实际变化{preview.changed_count}份。</p>{preview.items.map(row=><div key={row.id}><b>{row.name} · {row.changed?'将修改':'保持原设置'}</b><p>原：{modes[row.before.reference_mode||'']||'未明确'} {row.before.preserve_items}</p><p>新：{modes[row.after.reference_mode]} {row.after.preserve_items}</p><small>材料{row.id} · {row.status}，来源摘要已绑定。</small></div>)}<p className="hint">{preview.note}</p>{preview.changed_count===0?<p>设置全部相同，不生成空修订或使确认失效。</p>:<><label><input type="checkbox" checked={ack} disabled={blocked||busy} onChange={e=>setAck(e.target.checked)}/>我已逐份核对旧新引用设置，接受保存为新修订并重新确认需求与配置</label><button className="primary" disabled={blocked||busy||!ack} onClick={()=>void request(true)}>确认并一次保存所选引用方式</button></>}</div>}
 </section>;
}
