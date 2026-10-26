import {useEffect, useState} from 'react';
import {CheckCircle2, CircleAlert, LoaderCircle} from 'lucide-react';

export type ProbeResult = {state:'running'|'success'|'error'|'historical'; started:number; configuration_revision?:number; message:string; latency_ms?:number; total_tokens?:number};
export type ProbeResults = Record<string, Partial<Record<'text'|'json', ProbeResult>>>;

export default function ModelProbeFeedback({results,configurationRevision}: {configurationRevision?:number;results?: Partial<Record<'text'|'json', ProbeResult>>}) {
 const [,tick]=useState(0);
 const running=Object.values(results||{}).some(r=>r?.state==='running');
 useEffect(()=>{if(!running)return;const timer=setInterval(()=>tick(n=>n+1),1000);return()=>clearInterval(timer)},[running]);
 if(!results)return null;
 return <div className="model-probe-results" aria-live="polite" aria-atomic="true">
  {(['text','json'] as const).map(kind=>{const result=results[kind];if(!result)return null;const waiting=result.state==='running',historical=result.state==='historical'||configurationRevision!==undefined&&result.configuration_revision!==undefined&&configurationRevision!==result.configuration_revision;return <div key={kind} className={`model-probe-result ${historical?'historical':result.state}`} role={result.state==='error'?'alert':'status'}>
   {waiting?<LoaderCircle size={15} className="spin"/>:result.state==='success'&&!historical?<CheckCircle2 size={15}/>:<CircleAlert size={15}/>}
   <div><b>{kind==='text'?'连接测试':'JSON 输出测试'} · {waiting?(historical?'等待旧配置结果':'等待模型返回'):historical?'旧配置结果，未确认当前能力':result.state==='success'?'通过':'未通过'}</b>
    <p>{result.message}{historical&&' 此卡片属于原配置，请核对当前设置；不会自动重测。'}</p>
    <small>{waiting?`已等待 ${Math.max(0,Math.floor((Date.now()-result.started)/1000))} 秒；可以关闭窗口，重新打开查看结果。`:[result.latency_ms!==undefined?`耗时 ${result.latency_ms} ms`:'',result.total_tokens!==undefined?`用量 ${result.total_tokens} tokens`:'',`测试时间 ${new Date(result.started).toLocaleTimeString('zh-CN')}`].filter(Boolean).join(' · ')}</small>
   </div>
  </div>})}
 </div>
}
