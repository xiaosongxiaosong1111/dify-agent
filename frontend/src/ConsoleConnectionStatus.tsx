import {useEffect,useState} from 'react';
type Failure={code:string;stage:string;message:string;next_action:string;http_status:number|null;occurred_at:string|null;mode:string;automatic_retry:false};
export type ConsoleConnection={failure?:Failure|null;automatic_login_enabled?:boolean;state:string;expires_at:string|null;seconds_remaining:number|null;message:string;verification:string};
const labels:Record<string,string>={missing:'未连接',expired:'已过期',incomplete:'凭据不完整',unknown:'到期时间未知',expiring:'即将过期',present:'已配置（仍需验证）'};
export default function ConsoleConnectionStatus({connection}:{connection?:ConsoleConnection}){
 const [elapsed,setElapsed]=useState(0);
 useEffect(()=>{const started=performance.now();setElapsed(0);const timer=setInterval(()=>setElapsed((performance.now()-started)/1000),15000);return()=>clearInterval(timer)},[connection]);
 if(!connection)return <div className="console-connection hint">管理连接未记录到期信息，请读取环境或真实测试；历史验证不代表当前可用。</div>;
 const raw=connection.failure;const failure=raw&&typeof raw.code==='string'&&/^[a-z_]{1,60}$/.test(raw.code)&&typeof raw.stage==='string'&&raw.stage.length<=100&&typeof raw.message==='string'&&raw.message.length<=500&&typeof raw.next_action==='string'&&raw.next_action.length<=500&&raw.automatic_retry===false?raw:null;
 const remaining=connection.seconds_remaining==null?null:Math.max(0,connection.seconds_remaining-elapsed);
 const state=remaining===0?'expired':remaining!=null&&remaining<=300&&connection.state==='present'?'expiring':connection.state;
 const message=connection.automatic_login_enabled&&['expired','expiring'].includes(state)?'已授权本机加密保存，下次管理请求前会自动连接此原环境；失败暂停，不重放写入。':state==='expired'?'Sierra 保存的管理令牌已过期，请使用本列表的“邮箱密码连接”；在 Dify 页面登录不会更新 Sierra。':state==='expiring'?'管理令牌将在 5 分钟内到期；开始资源操作前建议重新连接。':connection.message;
 return <div className={`console-connection ${['expired','incomplete','expiring'].includes(state)?'callout amber':'hint'}`} style={{display:'block'}} role={['expired','incomplete'].includes(state)?'status':undefined}><b>管理连接：{labels[state]||'未知'}</b><p>{message}</p>{connection.expires_at&&<small>令牌记录到期时间：{new Date(connection.expires_at).toLocaleString()} · 仅本机时间提示，未验证签名或服务器权限。</small>}{failure&&<div className="console-failure" role="status"><b>最近连接失败诊断</b><p>{failure.message}</p><small>阶段：{failure.stage} · 代码：{failure.code}{typeof failure.http_status==='number'&&Number.isInteger(failure.http_status)&&failure.http_status>=100&&failure.http_status<=599?` · HTTP ${failure.http_status}`:''}</small><p className="hint">{failure.next_action}</p><small>{failure.occurred_at&&Number.isFinite(Date.parse(failure.occurred_at))?`失败记录时间：${new Date(failure.occurred_at).toLocaleString()}`:'该次失败时间未记录'} · 未自动重试或重放原操作。</small></div>}</div>;
}
