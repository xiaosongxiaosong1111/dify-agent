import {useEffect,useState} from 'react';
import {Bot} from 'lucide-react';
import MessageRevision from './MessageRevision';
import MessageOriginalPages from './MessageOriginalPages';

const PAGE=50,SHORT=4000,LONG=16000;
function prefix(text:string,limit:number){let end=Math.min(text.length,limit);if(end<text.length&&end>0&&/[\uD800-\uDBFF]/.test(text[end-1])&&/[\uDC00-\uDFFF]/.test(text[end]))end--;return text.slice(0,end)}
function when(value:unknown){if(typeof value!=='string'||!Number.isFinite(Date.parse(value)))return '时间未知';return new Date(value).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})}

/** Display window only: the task history and the model context are untouched. */
export default function TaskMessages({messages,currentRevision,taskId}:{messages:unknown[];currentRevision:number;taskId:string}){
 const [window,setWindow]=useState<{start:number;stop:number;baseCount:number}|null>(null),[expanded,setExpanded]=useState<{index:number;text:string}|null>(null),count=messages.length;
 const stable=window&&window.stop<=count?window:null,start=stable?.start??Math.max(0,count-PAGE),stop=stable?.stop??count;
 useEffect(()=>{if(window&&window.stop>count)setWindow(null)},[count,window]);
 useEffect(()=>setExpanded(null),[start,stop]);
 if(!count)return null;
 return <><div className="message-window"><b>对话记录 {start+1}—{stop} / {count}</b><p className="hint">每页最多50条，仅改变本页显示；更早原话保留，未改变需求、模型上下文或后台历史。长正文先显示开头。</p>{stable&&count>stable.baseCount&&<p role="status">有{count-stable.baseCount}条新记录；当前旧窗口保持，可主动回到最新。</p>}<div className="actions"><button className="secondary" disabled={start===0} onClick={()=>setWindow({start:Math.max(0,start-PAGE),stop:start,baseCount:stable?.baseCount??count})}>更早50条</button><button className="secondary" disabled={stop===count} onClick={()=>setWindow(stop+PAGE>=count?null:{start:stop,stop:Math.min(count,stop+PAGE),baseCount:stable?.baseCount??count})}>较新50条</button><button className="secondary" disabled={!stable} onClick={()=>setWindow(null)}>回到最新50条</button></div></div>
  {messages.slice(start,stop).map((raw,offset)=>{const index=start+offset,message=raw&&typeof raw==='object'&&!Array.isArray(raw)?raw as Record<string,unknown>:{},text=typeof message.content==='string'&&message.content?message.content:typeof message.text==='string'?message.text:'',full=expanded?.index===index&&expanded.text===text,limit=full?LONG:SHORT,body=prefix(text,limit),truncated=body.length<text.length,user=message.role==='user';return <article key={index} data-message-index={index} className={`message ${user?'user':''}`}><span className="msgavatar">{user?'我':<Bot size={16}/>}</span><div className="bubble"><small>{user?'你':message.role==='assistant'?'Sierra':'角色未记录'} · {when(message.created_at)} · 原记录 message:{index}</small><MessageRevision message={{role:typeof message.role==='string'?message.role:undefined,context_revision:typeof message.context_revision==='number'?message.context_revision:undefined,result_revision:typeof message.result_revision==='number'?message.result_revision:undefined}} currentRevision={currentRevision}/>{message.purpose==='discussion'&&<small>只读讨论 · 未修改需求或确认</small>}<p className="message-body">{text?body:'正文未记录为文字，未把对象改写成原话。'}</p>{truncated&&<p className="hint">{full?'已到本页单条预览上限，仍不是完整正文；原文保留在后台。历史查找可在其支持范围内核对原话。':'正文较长，当前仅显示开头，不能当作已读全文。'}</p>}{text.length>SHORT&&<button type="button" className="secondary" onClick={()=>setExpanded(full?null:{index,text})}>{full?'收起本条预览':'展开本条预览'}</button>}{text.length>SHORT&&<MessageOriginalPages taskId={taskId} revision={currentRevision} index={index} message={message} text={text}/>}</div></article>})}
 </>;
}
