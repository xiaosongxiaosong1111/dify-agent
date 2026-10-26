import {useEffect,useRef,useState} from 'react';
import {validWindow,windowCursor,type MessageWindow} from './messageWindowTransport';
import {Bot} from 'lucide-react';
import MessageRevision from './MessageRevision';
import MessageOriginalPages from './MessageOriginalPages';

const PAGE=50,SHORT=4000,LONG=16000;
function prefix(text:string,limit:number){let end=Math.min(text.length,limit);if(end<text.length&&end>0&&/[\uD800-\uDBFF]/.test(text[end-1])&&/[\uDC00-\uDFFF]/.test(text[end]))end--;return text.slice(0,end)}
function when(value:unknown){if(typeof value!=='string'||!Number.isFinite(Date.parse(value)))return '时间未知';return new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}

/** Display window only: the task history and the model context are untouched. */
function LocalTaskMessages({messages,currentRevision,taskId}:{messages:unknown[];currentRevision:number;taskId:string}){
 const [window,setWindow]=useState<{start:number;stop:number;baseCount:number}|null>(null),count=messages.length;
 const stable=window&&window.stop<=count?window:null,start=stable?.start??Math.max(0,count-PAGE),stop=stable?.stop??count;
 useEffect(()=>{if(window&&window.stop>count)setWindow(null)},[count,window]);
 if(!count)return null;
 return <><div className="message-window"><b>对话记录 {start+1}—{stop} / {count}</b><p className="hint">每页最多50条，仅改变本页显示；更早原话保留，未改变需求、模型上下文或后台历史。长正文先显示开头。</p>{stable&&count>stable.baseCount&&<p role="status">有{count-stable.baseCount}条新记录；当前旧窗口保持，可主动回到最新。</p>}<div className="actions"><button className="secondary" disabled={start===0} onClick={()=>setWindow({start:Math.max(0,start-PAGE),stop:start,baseCount:stable?.baseCount??count})}>更早50条</button><button className="secondary" disabled={stop===count} onClick={()=>setWindow(stop+PAGE>=count?null:{start:stop,stop:Math.min(count,stop+PAGE),baseCount:stable?.baseCount??count})}>较新50条</button><button className="secondary" disabled={!stable} onClick={()=>setWindow(null)}>回到最新50条</button></div></div>
  <MessageRows key={`${start}:${stop}`} messages={messages.slice(start,stop)} start={start} currentRevision={currentRevision} taskId={taskId}/>
 </>;
}

function MessageRows({messages,start,currentRevision,taskId}:{messages:unknown[];start:number;currentRevision:number;taskId:string}){
 const [expanded,setExpanded]=useState<{index:number;text:string}|null>(null);
 return <>{messages.map((raw,offset)=>{const index=start+offset,message=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw as Record<string,unknown>:{},text=typeof message.content==='string'&&message.content?message.content:typeof message.text==='string'?message.text:'',full=expanded?.index===index&&expanded.text===text,limit=full?LONG:SHORT,body=prefix(text,limit),truncated=body.length<text.length,user=message.role==='user';return <article key={index} data-message-index={index} className={`message ${user?'user':''}`}><span className="msgavatar">{user?'我':<Bot size={16}/>}</span><div className="bubble"><small>{user?'你':message.role==='assistant'?'Sierra':'角色未记录'} · {when(message.created_at)} · 原记录 message:{index}</small><MessageRevision message={{role:typeof message.role==='string'?message.role:undefined,context_revision:typeof message.context_revision==='number'?message.context_revision:undefined,result_revision:typeof message.result_revision==='number'?message.result_revision:undefined}} currentRevision={currentRevision}/>{message.purpose==='discussion'&&<small>只读讨论 · 未修改需求或确认</small>}<p className="message-body">{text?body:'正文未记录为文字，未把对象改写成原话。'}</p>{truncated&&<p className="hint">{full?'已到本页单条预览上限，仍不是完整正文；原文保留在后台。历史查找可在其支持范围内核对原话。':'正文较长，当前仅显示开头，不能当作已读全文。'}</p>}{text.length>SHORT&&<button type="button" className="secondary" onClick={()=>setExpanded(full?null:{index,text})}>{full?'收起本条预览':'展开本条预览'}</button>}{text.length>SHORT&&<MessageOriginalPages taskId={taskId} revision={currentRevision} index={index} message={message} text={text}/>}</div></article>})}</>;
}

export default function TaskMessages(props:{messages:unknown[];currentRevision:number;taskId:string;historyWindow?:MessageWindow}){
 return props.historyWindow?<RemoteTaskMessages {...props} historyWindow={props.historyWindow}/>:<LocalTaskMessages {...props}/>;
}

function RemoteTaskMessages({messages,currentRevision,taskId,historyWindow}:{messages:unknown[];currentRevision:number;taskId:string;historyWindow:MessageWindow}){
 const [saved,setSaved]=useState<{meta:MessageWindow;messages:unknown[];latest:boolean}|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),current=useRef(historyWindow);current.current=historyWindow;
 useEffect(()=>()=>{epoch.current++;controller.current?.abort()},[taskId,currentRevision]);
 useEffect(()=>setError(''),[historyWindow.state_sequence,historyWindow.source_token]);
 useEffect(()=>{if(saved&&historyWindow.state_sequence>=saved.meta.state_sequence&&(saved.latest||historyWindow.total_messages<saved.meta.anchor_count))setSaved(null)},[historyWindow,saved]);
 const value=saved??{meta:historyWindow,messages,latest:true},meta=value.meta,count=Math.max(meta.total_messages,historyWindow.total_messages);
 const read=async(start:number,end:number,latest=false)=>{
  const ticket=++epoch.current,source=meta,active=new AbortController();controller.current?.abort();controller.current=active;setBusy(true);setError('');const timer=setTimeout(()=>active.abort(),12000);
  try{
   const response=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/history/window`,{method:'POST',headers:{'Content-Type':'application/json'},cache:'no-store',signal:active.signal,body:JSON.stringify({revision:currentRevision,cursor:windowCursor(source),...(latest?{latest:true}:{start,end})})});
   const data=await response.json().catch(()=>null);if(ticket!==epoch.current)return;
   if(!response.ok){if(response.status===409)setSaved(null);throw Error(typeof data?.detail==='string'?data.detail:`消息窗口读取失败（HTTP ${response.status}），未读取完整历史作为替代。`)}
   const items=data?.messages;
   if(!data||!Array.isArray(items)||!validWindow(data,taskId,currentRevision,items)||data.state_sequence<current.current.state_sequence||latest&&(data.anchor_count!==data.total_messages||data.start!==Math.max(0,data.total_messages-50)||data.end!==data.total_messages)||!latest&&(data.start!==start||data.end!==end||data.anchor_count!==source.anchor_count))throw Error('消息窗口返回的范围、来源或提交顺序无法核对，未替换当前页。');
   setSaved({meta:data,messages:items,latest:data.end===data.total_messages&&data.start===Math.max(0,data.total_messages-50)});
  }catch(e){if(ticket===epoch.current)setError(active.signal.aborted?'本机消息窗口读取超时或取消，原页保持；未自动重发。':e instanceof TypeError?'本机消息窗口读取失败，原页保持。':e instanceof Error?e.message:'消息窗口未取得。')}finally{clearTimeout(timer);if(ticket===epoch.current)setBusy(false)}
 };
 if(!count)return null;
 return <><div className="message-window" data-transport="server" data-source-sequence={historyWindow.state_sequence}><b>对话记录 {meta.start+1}—{meta.end} / {count}</b><p className="hint">每页最多50条，打开和刷新任务只读取最近窗口，翻页才读取其它原话；原索引、后台历史及模型上下文保持。每页按读取时的记录核对，不代表全部历史同一快照。</p>{!value.latest&&count>meta.anchor_count&&<p role="status">有{count-meta.anchor_count}条新记录；当前旧窗口保持，可主动回到最新。</p>}<div className="actions"><button className="secondary" disabled={busy||meta.start===0} onClick={()=>void read(Math.max(0,meta.start-50),meta.start)}>更早50条</button><button className="secondary" disabled={busy||meta.end===meta.anchor_count} onClick={()=>void read(meta.end,Math.min(meta.anchor_count,meta.end+50))}>较新50条</button><button className="secondary" disabled={busy||value.latest} onClick={()=>void read(0,0,true)}>回到最新50条</button></div>{busy&&<p role="status">正在只读核对消息窗口…</p>}{error&&<p role="alert">{error}</p>}</div><MessageRows key={`${meta.start}:${meta.end}:${meta.source_token}`} messages={value.messages} start={meta.start} currentRevision={currentRevision} taskId={taskId}/></>;
}
