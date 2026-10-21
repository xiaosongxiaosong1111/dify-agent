import {useEffect,useState} from 'react';
export type ConsoleConnection={automatic_login_enabled?:boolean;state:string;expires_at:string|null;seconds_remaining:number|null;message:string;verification:string};
const labels:Record<string,string>={missing:'未连接',expired:'已过期',incomplete:'凭据不完整',unknown:'到期时间未知',expiring:'即将过期',present:'已配置（仍需验证）'};
export default function ConsoleConnectionStatus({connection}:{connection?:ConsoleConnection}){
 const [elapsed,setElapsed]=useState(0);
 useEffect(()=>{const started=performance.now();setElapsed(0);const timer=setInterval(()=>setElapsed((performance.now()-started)/1000),15000);return()=>clearInterval(timer)},[connection]);
 if(!connection)return <div className="console-connection hint">管理连接未记录到期信息，请读取环境或真实测试；历史验证不代表当前可用。</div>;
 const remaining=connection.seconds_remaining==null?null:Math.max(0,connection.seconds_remaining-elapsed);
 const state=remaining===0?'expired':remaining!=null&&remaining<=300&&connection.state==='present'?'expiring':connection.state;
 const message=connection.automatic_login_enabled&&['expired','expiring'].includes(state)?'已授权本机加密保存，下次管理请求前会自动连接此原环境；失败暂停，不重放写入。':state==='expired'?'Sierra 保存的管理令牌已过期，请使用本列表的“邮箱密码连接”；在 Dify 页面登录不会更新 Sierra。':state==='expiring'?'管理令牌将在 5 分钟内到期；开始资源操作前建议重新连接。':connection.message;
 return <div className={`console-connection ${['expired','incomplete','expiring'].includes(state)?'callout amber':'hint'}`} role={['expired','incomplete'].includes(state)?'status':undefined}><b>管理连接：{labels[state]||'未知'}</b><p>{message}</p>{connection.expires_at&&<small>令牌记录到期时间：{new Date(connection.expires_at).toLocaleString()} · 仅本机时间提示，未验证签名或服务器权限。</small>}</div>;
}
