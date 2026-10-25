import {useEffect,useRef,useState} from 'react';

type Material={id:string;name?:string;sha256?:string;size?:number};
type Proof={schema_version:number;task_id:string;material_id:string;revision:number;state:string;message:string;note:string;downloadable:boolean;source_sha256:string|null;observed_sha256:string|null;recorded_size:number|null;observed_size:number|null;sha256_matches:boolean|null;size_matches:boolean|null;download_name:string;checked_at:string};
const states=['verified','changed','unknown','unavailable','oversized'];
const hashOrNull=(value:unknown)=>value===null||typeof value==='string'&&/^[0-9a-f]{64}$/.test(value);
const sizeOrNull=(value:unknown)=>value===null||typeof value==='number'&&Number.isSafeInteger(value)&&value>=0;
function valid(value:Proof,taskId:string,revision:number,material:Material){
 return value&&value.schema_version===1&&value.task_id===taskId&&value.material_id===material.id&&value.revision===revision&&states.includes(value.state)&&typeof value.message==='string'&&typeof value.note==='string'&&typeof value.checked_at==='string'&&typeof value.download_name==='string'&&hashOrNull(value.source_sha256)&&hashOrNull(value.observed_sha256)&&sizeOrNull(value.recorded_size)&&sizeOrNull(value.observed_size)&&[true,false,null].includes(value.sha256_matches)&&[true,false,null].includes(value.size_matches)&&typeof value.downloadable==='boolean'&&(value.state!=='verified'?value.downloadable===false:value.downloadable===true&&value.sha256_matches===true&&value.source_sha256===material.sha256&&value.observed_sha256===material.sha256&&typeof value.observed_size==='number'&&value.observed_size<=20*1024*1024&&value.size_matches!==false);
}

export default function MaterialOriginalPanel({taskId,revision,material}:{taskId:string;revision:number;material:Material}){
 const [value,setValue]=useState<Proof|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 const generation=useRef(0),controller=useRef<AbortController|null>(null);
 useEffect(()=>{setValue(null);setError('');setNotice('');setBusy(false);return()=>{generation.current++;controller.current?.abort()}},[taskId,revision,material.id,material.sha256]);
 const base=`/api/tasks/${encodeURIComponent(taskId)}/materials/${encodeURIComponent(material.id)}/original`;
 async function request(download=false){
  const ticket=++generation.current,abort=new AbortController();controller.current=abort;setBusy(true);setError('');setNotice('');if(!download)setValue(null);
  const timer=setTimeout(()=>abort.abort(),20000);
  try{
   const response=await fetch(base+(download?'/download':'')+'?revision='+revision,{signal:abort.signal,cache:'no-store'});
   if(!response.ok){const data=await response.json().catch(()=>null);throw Error(typeof data?.detail==='string'?data.detail:`原文件读取失败（HTTP ${response.status}）。`)}
   if(download){
    if(!value?.downloadable||response.headers.get('content-type')!=='application/octet-stream'||response.headers.get('x-sierra-source-sha256')!==material.sha256)throw Error('下载的来源或类型与当前材料不匹配，未保存文件。');
    const bytes=await response.arrayBuffer();if(bytes.byteLength>20*1024*1024)throw Error('下载超过20MB上限，未保存文件。');
    const digest=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
    if(digest!==material.sha256)throw Error('收到的字节与保存摘要不一致，未保存文件。');
    if(generation.current!==ticket)return;
    const url=URL.createObjectURL(new Blob([bytes],{type:'application/octet-stream'})),link=document.createElement('a');link.href=url;link.download=value.download_name;link.click();setTimeout(()=>URL.revokeObjectURL(url),2000);setNotice('已交给浏览器下载；收到的字节已核对，浏览器是否保存请查看下载列表。');
   }else{
    const data=await response.json();if(!valid(data,taskId,revision,material))throw Error('原文件核对回包的任务、修订或来源不匹配，未采用该结果。');
    if(generation.current===ticket)setValue(data);
   }
  }catch(e){if(generation.current===ticket){setValue(null);setError(abort.signal.aborted?'原文件读取超时或已取消，请核对本机服务后重新检查。':e instanceof TypeError?'原文件读取失败，请核对本机服务。':e instanceof Error?e.message:'原文件读取失败，未下载或修改材料。')}}
  finally{clearTimeout(timer);if(generation.current===ticket)setBusy(false)}
 }
 return <details className="material-original"><summary>核对或下载本机原文件</summary><p className="hint">按材料ID读取原字节并比对保存摘要；同名文件分别核对，不重建丢失原件，不代表完整解析或内容正确。</p><button className="secondary" disabled={busy} onClick={()=>void request()}>核对当前原文件</button>{busy&&<p role="status">正在读取并核对原文件…</p>}{error&&<div className="callout amber" role="alert">{error}</div>}{value&&<div className={value.downloadable?'callout':'callout amber'} style={{display:'block'}}><b>{value.state==='verified'?'原文件字节已核对':value.state==='changed'?'原文件或记录已变化':value.state==='unknown'?'原文件身份未记录':value.state==='oversized'?'原文件超过读取上限':'原文件不可核对'}</b><p>{value.message}</p><p className="hint">核对时点：{value.checked_at} · 读取大小：{value.observed_size===null?'未知／未读取':`${value.observed_size}字节`} · 保存大小：{value.recorded_size===null?'未记录':`${value.recorded_size}字节`}</p><details><summary>材料标识与摘要</summary><p className="hint" style={{overflowWrap:'anywhere'}}>材料 {material.id}<br/>保存摘要 {value.source_sha256||'未记录'}<br/>本次原字节摘要 {value.observed_sha256||'未读取／未知'}</p></details><p className="hint">{value.note}</p><button className="secondary" disabled={busy||!value.downloadable} onClick={()=>void request(true)}>重新核对并下载原文件</button></div>}{notice&&<p role="status" className="hint">{notice}</p>}</details>;
}
