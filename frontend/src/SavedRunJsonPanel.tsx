import {useEffect,useRef,useState} from 'react';
const parts=[['input','保存输入'],['test_case','运行时样例快照'],['result','保存返回'],['output','旧输出字段'],['evaluation','原评估记录']] as const;
type Entry={key:string;label:string;state:'available'|'missing'|'unavailable';total_chars:number|null;total_utf8_bytes:number|null;content_sha256:string|null};
type Base={schema_version:1;task_id:string;revision:number;app_type:string;run_id:string;run_revision:number|null;source_token:string;verification:string;task_changed:false;model_called:false;network_requested:false;platform_checked:false;business_verified:false;note:string};
type Index=Base&{parts:Entry[]};
type Page=Base&{part:string;source_kind:string;text:string;offset:number;next_offset:number|null;total_chars:number;total_utf8_bytes:number;content_sha256:string;page_sha256:string};
const sha=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const integer=(v:unknown,min:number,max:number)=>Number.isSafeInteger(v)&&Number(v)>=min&&Number(v)<=max;
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
function base(v:unknown,id:string,revision:number,run:string):v is Base{return object(v)&&v.schema_version===1&&v.task_id===id&&v.revision===revision&&v.run_id===run&&typeof v.app_type==='string'&&['workflow','advanced-chat','agent'].includes(v.app_type)&&(v.run_revision===null||integer(v.run_revision,1,Number.MAX_SAFE_INTEGER))&&sha(v.source_token)&&typeof v.note==='string'&&!!v.note&&v.note.length<=600&&['task_changed','model_called','network_requested','platform_checked','business_verified'].every(k=>v[k]===false)}
async function digest(text:string){return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(n=>n.toString(16).padStart(2,'0')).join('')}

export default function SavedRunJsonPanel({taskId,revision,runId,scope}:{taskId:string;revision:number;runId:string;scope:string}){
 const [index,setIndex]=useState<Index|null>(null),[part,setPart]=useState('result'),[page,setPage]=useState<Page|null>(null),[working,setWorking]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{epoch.current++;controller.current?.abort();setIndex(null);setPage(null);setWorking(false);setError('');return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,runId,scope]);
 useEffect(()=>{epoch.current++;controller.current?.abort();setPage(null);setWorking(false);setError('')},[part]);
 const selected=index?.parts.find(p=>p.key===part);
 async function read(offset:number|null){
  if(working||offset!==null&&(!index||selected?.state!=='available'))return;
  const ticket=++epoch.current,abort=new AbortController();controller.current=abort;setWorking(true);setError('');if(offset===null){setIndex(null);setPage(null)}const timer=setTimeout(()=>abort.abort(),10000);
  try{
   const q=new URLSearchParams({revision:String(revision)});if(offset!==null){q.set('source_token',index!.source_token);q.set('part',part);q.set('offset',String(offset));q.set('limit','4000')}
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/runs/${encodeURIComponent(runId)}/${offset===null?'content-index':'content'}?${q}`,{signal:abort.signal,cache:'no-store'});
   if(ticket!==epoch.current)return;
   if(!response.ok){if(response.status===409)setIndex(null);throw Error(response.status===409?'任务或记录来源已变化，请重新读取索引；未混合旧正文。':'本机保存JSON暂不可读取，可能缺失、超限或疑似含凭据；未返回部分成功或自动重试。')}
   const v:unknown=await response.json();if(!base(v,taskId,revision,runId))throw Error('运行JSON的任务、记录或来源范围无法核对，未显示。');
   if(offset===null){
    const value=v as Index;if(value.verification!=='saved_run_json_index_only'||!Array.isArray(value.parts)||value.parts.length!==5)throw Error('运行JSON索引范围无法核对。');const seen=new Set();
    for(const row of value.parts){if(!object(row)||!parts.some(([key,label])=>row.key===key&&row.label===label)||seen.has(row.key)||!['available','missing','unavailable'].includes(row.state))throw Error('运行JSON分区无法核对。');seen.add(row.key);if(row.state==='available'){if(!integer(row.total_chars,1,2000000)||!integer(row.total_utf8_bytes,Number(row.total_chars),2000000)||!sha(row.content_sha256))throw Error('运行JSON分区大小或摘要无法核对。')}else if(row.total_chars!==null||row.total_utf8_bytes!==null||row.content_sha256!==null)throw Error('不可读分区不应含部分摘要。')}
    if(ticket===epoch.current)setIndex(value);
   }else{
    const value=v as Page;if(!index||!selected||value.verification!=='saved_run_json_page_only'||value.source_kind!=='saved_run_value_json'||value.part!==part||value.source_token!==index.source_token||value.app_type!==index.app_type||value.run_revision!==index.run_revision||typeof value.text!=='string'||value.offset!==offset||value.total_chars!==selected.total_chars||value.total_utf8_bytes!==selected.total_utf8_bytes||value.content_sha256!==selected.content_sha256||!sha(value.page_sha256))throw Error('运行JSON正文与所选索引不一致，未显示或拼接。');
    const size=Array.from(value.text).length,end=offset+size;if(size!==Math.min(4000,value.total_chars-offset)||value.next_offset!==(end<value.total_chars?end:null)||new TextEncoder().encode(value.text).length>16000||await digest(value.text)!==value.page_sha256)throw Error('运行JSON页范围或摘要不一致，未显示。');
    if(ticket===epoch.current)setPage(value);
   }
  }catch(e){if(ticket===epoch.current){setPage(null);setError(e instanceof Error?e.message:'运行JSON读取失败，未写入。')}}finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 return <details className="saved-run-json configuration-proposal"><summary><b>精确查看本机保存JSON（只读）</b></summary><p className="hint">上方是浏览器格式化预览；本入口按后端保存值核对数值/分区。不是原始网络字节，不重评旧结论、不改变当前草稿、确认或费用，不调用Dify。</p><button className="secondary" disabled={working} onClick={()=>void read(null)}>读取保存JSON索引（只读）</button>{working&&<p role="status">读取本机保存记录…</p>}{error&&<p role="alert">{error}</p>}{index&&<><ul>{index.parts.map(p=><li key={p.key}>{p.label}：{p.state==='available'?'可读取':p.state==='missing'?'未保存':'不可安全读取'}</li>)}</ul><label className="field"><span>运行JSON分区</span><select aria-label="运行JSON分区" value={part} disabled={working} onChange={e=>setPart(e.target.value)}>{parts.map(([key,label])=><option key={key} value={key} disabled={index.parts.find(p=>p.key===key)?.state!=='available'}>{label}</option>)}</select></label><button className="secondary" disabled={working||selected?.state!=='available'} onClick={()=>void read(0)}>读取所选运行JSON（只读）</button><p className="hint">{index.note}</p></>}{page&&<><p className="hint">运行保存修订 v{page.run_revision??'?'} · 当前任务 v{revision} · 第{page.offset+1}—{page.offset+Array.from(page.text).length}码点 / {page.total_chars}码点</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:360,overflow:'auto'}}>{page.text}</pre><div className="actions"><button className="secondary" disabled={working||page.offset===0} onClick={()=>void read(Math.max(0,page.offset-4000))}>上一页运行JSON</button><button className="secondary" disabled={working||page.next_offset===null} onClick={()=>void read(page.next_offset)}>下一页运行JSON</button></div></>}</details>;
}
