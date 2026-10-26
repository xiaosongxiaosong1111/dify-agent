import {useEffect,useRef,useState} from 'react';
import type {TestCase} from './AcceptancePanel';
import {CASE_SET_LIMIT,casePackage,fail,hash,object,sameJson,sha256} from './caseSetTransport';
type Preview={source:{name:string;bytes:number;sha256:string;encoding:'utf-8'};cases:TestCase[];note:string};
export default function CaseSetPanel({taskId,revision,appType,draftScope,disabled,onAppend}:{taskId:string;revision:number;appType:string;draftScope:string;disabled:boolean;onAppend:(cases:TestCase[])=>boolean}){
 const [file,setFile]=useState<File|null>(null),[value,setValue]=useState<Preview|null>(null),[selected,setSelected]=useState<string[]>([]),[ack,setAck]=useState(false),[working,setWorking]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),consumed=useRef(false),latest=useRef({disabled,onAppend});latest.current={disabled,onAppend};
 const scope=JSON.stringify([taskId,revision,appType,draftScope]),activeScope=useRef(scope);activeScope.current=scope;
 useEffect(()=>{epoch.current++;controller.current?.abort();setValue(null);setSelected([]);setAck(false);setWorking(false);setError('');consumed.current=false;return()=>{epoch.current++;controller.current?.abort()}},[scope,disabled]);
 useEffect(()=>{setFile(null);setNotice('')},[taskId,revision]);
 function clear(){epoch.current++;controller.current?.abort();setValue(null);setSelected([]);setAck(false);setWorking(false);setError('');setNotice('');consumed.current=false}
 async function read(exporting=false){
  if(disabled||working||!exporting&&!file)return;clear();const ticket=++epoch.current,abort=new AbortController();controller.current=abort;setWorking(true);const current=()=>ticket===epoch.current&&activeScope.current===scope&&!abort.signal.aborted;
  const timer=setTimeout(()=>abort.abort(),15000);
  try{
   if(exporting){
    const response=await fetch(`${import.meta.env.VITE_API_BASE||'/api'}/tasks/${encodeURIComponent(taskId)}/test-cases/export?revision=${revision}`,{cache:'no-store',signal:abort.signal});
    if(!response.ok){const body=await response.json();throw Error(typeof body.detail==='string'?body.detail:'后台已保存定义包读取失败。')}
    if(!current())return;if(response.headers.get('x-sierra-task-id')!==taskId||response.headers.get('x-sierra-revision')!==String(revision)||!hash(response.headers.get('x-sierra-definitions-sha256'))||!response.headers.get('content-type')?.includes('application/json'))throw fail();
    const bytes=await response.arrayBuffer();casePackage(bytes,appType);if(await sha256(bytes)!==response.headers.get('x-sierra-definitions-sha256'))throw fail();if(!current())return;
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`sierra-cases-r${revision}.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);setNotice('已下载后台本修订保存的样例定义；未保存草稿、旧ID、运行成绩和确认不在包内。');return;
   }
   const source=file!;if(source.size<1||source.size>CASE_SET_LIMIT)throw Error('样例JSON文件须为1—512000字节，未截断或上传。');
   const bytes=await source.arrayBuffer(),input=casePackage(bytes,appType),sourceHash=await sha256(bytes);if(!current())return;
   const nonce=crypto.randomUUID(),form=new FormData();form.append('file',source);form.append('revision',String(revision));form.append('request_nonce',nonce);
   const response=await fetch(`${import.meta.env.VITE_API_BASE||'/api'}/tasks/${encodeURIComponent(taskId)}/test-cases/import-preview`,{method:'POST',body:form,cache:'no-store',signal:abort.signal});const data=await response.json();if(!current())return;
   if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'定义预览未完成，原草稿保持。');
   if(data.schema_version!==1||data.task_id!==taskId||data.revision!==revision||data.app_type!==appType||data.request_nonce!==nonce||data.verification!=='case_definitions_only'||['task_changed','network_requested','model_called','run_started','business_verified'].some(k=>data[k]!==false)||typeof data.note!=='string'||data.note.length>2000||!object(data.source)||data.source.name!==source.name||data.source.bytes!==source.size||data.source.sha256!==sourceHash||data.source.encoding!=='utf-8'||!Array.isArray(data.cases)||data.cases.length!==input.cases.length)throw fail();
   const ids=new Set<string>();const definitions=data.cases.map((row:unknown)=>{if(!object(row)||typeof row.id!=='string'||!/^[a-f0-9-]{36}$/.test(row.id)||ids.has(row.id))throw fail();ids.add(row.id);const {id,...definition}=row;return definition});
   if(!sameJson(definitions,input.cases))throw fail();setValue(data);setSelected([]);setAck(false);
  }catch(e){if(current()||abort.signal.aborted&&ticket===epoch.current){setValue(null);setSelected([]);setAck(false);setError(abort.signal.aborted?'定义读取已停止或超时，未追加或自动重试。':e instanceof Error&&!(e instanceof TypeError||e instanceof SyntaxError||e instanceof DOMException)?e.message:'定义读取或文件编码无法完整核对，请保留原稿，不自动重试。')}}finally{clearTimeout(timer);if(ticket===epoch.current){setWorking(false)}}
 }
 function append(){
  if(!value||!ack||!selected.length||working||latest.current.disabled||consumed.current)return;
  consumed.current=true;const rows=value.cases.filter(row=>selected.includes(row.id));
  if(latest.current.onAppend(rows)){setValue(null);setSelected([]);setAck(false);setNotice(`已追加${rows.length}个新ID样例到未保存草稿；原草稿保持，尚未保存、确认或运行。`)}else{setError('当前草稿或来源已变化，未替换原编辑；请重新预览。')}
 }
 return <details className="case-set-panel"><summary>样例定义集 · JSON导入／导出</summary><p className="hint">只处理定义：当前应用类型、最多20例／512000字节。导出读取后台已保存内容，未保存稿不会导出；导入先预览并选择，只追加到未保存稿，不带旧ID、成绩、确认或资源许可。原文件请自行保留。</p><button className="secondary" disabled={disabled||working} onClick={()=>void read(true)}>下载后台已保存样例定义包</button><label className="field"><span>选择样例定义JSON文件</span><input aria-label="样例定义JSON文件" type="file" accept=".json,application/json" disabled={disabled||working} onChange={e=>{clear();setFile(e.target.files?.[0]??null);e.currentTarget.value=''}}/></label>{file&&<p>{file.name} · {file.size}字节</p>}<button className="secondary" disabled={disabled||working||!file} onClick={()=>void read()}>只读预览所选样例文件</button>{working&&<p role="status">正在核对定义包，未保存或运行……</p>}{error&&<p role="alert" className="callout amber">{error}</p>}
 {value&&<div className="case-set-preview"><p className="hint">{value.note}</p><details><summary>本次文件来源</summary><p>{value.source.name} · {value.source.bytes}字节 · SHA256 {value.source.sha256}</p><p>文件摘要核对不证明作者或业务正确，不会将原JSON归档为任务材料。</p></details>{value.cases.map((row,index)=><div className="case-set-row" key={row.id}><label><input type="checkbox" aria-label={`选择导入样例 ${index+1} ${row.name}`} checked={selected.includes(row.id)} disabled={disabled||working} onChange={e=>{setSelected(xs=>e.target.checked?[...xs,row.id]:xs.filter(id=>id!==row.id));setAck(false)}}/>第{index+1}例 · {row.name} · {row.required?'必选':'非必选'} · {1+(row.followups?.length??0)}轮</label><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:240,overflow:'auto'}}>{JSON.stringify({input:row.input,expectation:row.expectation,followups:row.followups},null,2)}</pre></div>)}<label><input type="checkbox" disabled={disabled||working||!selected.length} checked={ack} onChange={e=>setAck(e.target.checked)}/>我已核对所选定义，仅追加未保存草稿，不采用旧成绩或自动运行</label><button className="secondary" disabled={disabled||working||!selected.length||!ack} onClick={append}>追加所选定义到未保存样例</button></div>}
 {notice&&<p role="status" className="case-set-notice">{notice}</p>}<details><summary>定义包格式与本批范围</summary><pre>{JSON.stringify({schema_version:1,app_type:appType,cases:[{name:'请替换为具体场景',input:{query:'请替换为具体输入'},required:false,expectation:{mode:'manual',description:'请填写可判断的人工标准'}}]},null,2)}</pre><p className="hint">格式示意不会自动加入。关键词/字段规则用文字列表，Schema用JSON原文；旧字符串关键词、对象Schema、文件/会话接续身份或编辑器无法完整保留的字段会明确拒绝，不悄悄转换。选中与保存不代表业务验证通过。</p></details></details>;
}
