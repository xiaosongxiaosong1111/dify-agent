import {useEffect,useRef,useState} from 'react';

const sections=[['requirements','需求'],['configuration','配置'],['workflow_plan','完整Workflow计划'],['agent_plan','Agent计划'],['test_cases','验收样例']] as const;
type Page={schema_version:1;task_id:string;revision:number;app_type:string;version_id:string;historical_revision:number|null;section:string;snapshot_token:string;content_sha256:string;page_sha256:string;total_chars:number;total_utf8_bytes:number;offset:number;next_offset:number|null;text:string;source_kind:string;verification:string;task_changed:false;network_requested:false;platform_checked:false;business_verified:false;note:string};
const digest=async(text:string)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),x=>x.toString(16).padStart(2,'0')).join('');
const sha=(v:unknown)=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const integer=(v:unknown,min:number,max:number)=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=min&&v<=max;
export default function VersionContentPanel({taskId,revision,appType,versionId,snapshotToken,disabled}:{taskId:string;revision:number;appType:string;versionId:string;snapshotToken:string;disabled:boolean}){
 const [section,setSection]=useState('requirements'),[page,setPage]=useState<Page|null>(null),[working,setWorking]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{epoch.current++;controller.current?.abort();setPage(null);setWorking(false);setError('');return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,appType,versionId,snapshotToken,section,disabled]);
 async function read(offset:number){
  if(disabled||working)return;const ticket=++epoch.current,abort=new AbortController();controller.current=abort;setWorking(true);setError('');
  const timer=setTimeout(()=>abort.abort(),10000);
  try{
   const q=new URLSearchParams({revision:String(revision),section,snapshot_token:snapshotToken,offset:String(offset),limit:'4000'});
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/versions/${encodeURIComponent(versionId)}/content?${q}`,{signal:abort.signal,cache:'no-store'});
   if(ticket!==epoch.current)return;
   if(!r.ok)throw Error(r.status===409?'当前内容或历史快照已变化，请重新比较后读取；未返回旧正文。':r.status===404?'此快照没有保存所选内容，不以当前版本补齐。':'历史正文暂不可读取，可能超限或包含敏感内容；未恢复或自动重试。');
   const v=await r.json() as Page;
   if(!v||v.schema_version!==1||v.task_id!==taskId||v.revision!==revision||v.app_type!==appType||v.version_id!==versionId||v.section!==section||v.snapshot_token!==snapshotToken||!(v.historical_revision===null||integer(v.historical_revision,1,Number.MAX_SAFE_INTEGER))||v.source_kind!=='historical_saved_value_json'||v.verification!=='local_history_content_read_only'||['task_changed','network_requested','platform_checked','business_verified'].some(k=>v[k as keyof Page]!==false)||!sha(v.content_sha256)||!sha(v.page_sha256)||typeof v.text!=='string'||!integer(v.total_chars,1,2_000_000)||!integer(v.total_utf8_bytes,v.total_chars,2_000_000)||v.offset!==offset||typeof v.note!=='string'||!v.note||v.note.length>500)throw Error('历史正文响应归属或范围不匹配，未显示。');
   const size=Array.from(v.text).length,end=offset+size;
   if(size!==Math.min(4000,v.total_chars-offset)||end>v.total_chars||v.next_offset!==(end<v.total_chars?end:null)||new TextEncoder().encode(v.text).length>16000||await digest(v.text)!==v.page_sha256||offset>0&&(!page||page.content_sha256!==v.content_sha256||page.total_chars!==v.total_chars||page.total_utf8_bytes!==v.total_utf8_bytes))throw Error('历史正文来源、页范围或摘要不匹配，未拼接不同来源。');
   if(ticket===epoch.current)setPage(v);
  }catch(e){if(ticket===epoch.current){setPage(null);setError(e instanceof Error?e.message:'历史正文读取失败，未恢复。')}}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 return <details className="version-content-panel configuration-proposal"><summary><b>只读查看此历史版本正文</b></summary><p className="hint">按需读取所选历史保存值，不恢复版本、不覆盖本页草稿，也不改变当前确认或App。每页最多4000字，代码和模板仅作文字显示。</p><label className="field"><span>历史正文分区</span><select aria-label="历史正文分区" value={section} disabled={disabled||working} onChange={e=>{epoch.current++;controller.current?.abort();setPage(null);setError('');setSection(e.target.value)}}>{sections.map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label><button className="secondary" disabled={disabled||working} onClick={()=>void read(0)}>读取所选历史正文（只读）</button>{working&&<p role="status">读取历史保存值…</p>}{error&&<p role="alert">{error}</p>}{page&&!disabled&&<><p className="hint">历史v{page.historical_revision??'?'} · 第{page.offset+1}—{page.offset+Array.from(page.text).length}字 / {page.total_chars}字 · JSON保存值</p><p className="hint">{page.note}</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:360,overflow:'auto'}}>{page.text}</pre><div className="actions"><button className="secondary" disabled={working||page.offset===0} onClick={()=>void read(Math.max(0,page.offset-4000))}>上一页历史正文</button><button className="secondary" disabled={working||page.next_offset===null} onClick={()=>page.next_offset!==null&&void read(page.next_offset)}>下一页历史正文</button></div></>}</details>;
}
