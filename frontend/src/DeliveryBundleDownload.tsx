import {useEffect,useRef,useState} from 'react';

export default function DeliveryBundleDownload({taskId,revision,appType,artifactStamp,disabled}:{
 taskId:string;revision:number;appType:string;artifactStamp:string;disabled:boolean;
}){
 const epoch=useRef(0),controller=useRef<AbortController|null>(null);
 const [working,setWorking]=useState(false),[error,setError]=useState('');
 useEffect(()=>{epoch.current++;controller.current?.abort();setWorking(false);setError('');return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,appType,artifactStamp,disabled]);
 async function download(){
  if(disabled||working)return;
  const ticket=++epoch.current,abort=new AbortController();controller.current=abort;setWorking(true);setError('');
  const timer=setTimeout(()=>abort.abort(),20000);
  try{
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/delivery-bundle?revision=${revision}`,{signal:abort.signal,cache:'no-store'});
   if(ticket!==epoch.current)return;
   if(!response.ok){const value=await response.json();throw Error(typeof value.detail==='string'?value.detail:'交付包准备失败，请核对已保存修订。')}
   if(response.headers.get('X-Sierra-Revision')!==String(revision)||response.headers.get('content-type')?.split(';')[0]!=='application/zip')throw Error('交付包响应与当前修订不符，未下载。');
   const blob=await response.blob();if(ticket!==epoch.current)return;
   if(!blob.size||blob.size>18_000_000)throw Error('交付包大小无效，未下载。');
   const url=URL.createObjectURL(blob),anchor=document.createElement('a');
   try{anchor.href=url;anchor.download=`sierra-${appType}-r${revision}-delivery.zip`;anchor.click()}finally{URL.revokeObjectURL(url)}
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'交付包准备失败，未重试。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 return <section className="delivery-bundle-download"><button className="secondary" disabled={disabled||working} onClick={()=>void download()}>{working?'正在打包已保存修订…':'下载当前交付包（ZIP）'}</button><p className="hint">一次下载同一保存修订的DSL、现有交付说明和SHA256文件清单；含模拟依赖与未验证待办，不含材料原件或运行Key。下载不发布、不试跑，摘要不证明业务通过。</p>{error&&<p role="alert">{error}</p>}</section>;
}
