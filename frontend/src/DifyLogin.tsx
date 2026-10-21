import { useState } from 'react';

type Props = { name: string; baseUrl: string; connect: (email: string, password: string, rememberLogin: boolean) => Promise<void> };
export default function DifyLogin({name, baseUrl, connect}: Props) {
 const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[rememberLogin,setRememberLogin]=useState(false);
 const submit=async()=>{
  if(busy)return;
  const transient=password;setPassword('');setBusy(true);setError('');
  try{await connect(email,transient,rememberLogin)}catch(e){setError(e instanceof Error?e.message:'连接失败，请检查环境。')}finally{setBusy(false)}
 };
 return <div className="modal-body">
  <div className="callout">连接 {name}：{baseUrl}。请先在 Dify 页面创建管理员。此操作只登录并读取应用列表，不会注册或初始化账号。</div>
  <label className="field"><span>Dify 登录邮箱</span><input type="email" autoComplete="off" value={email} disabled={busy} onChange={e=>setEmail(e.target.value)}/></label>
  <label className="field"><span>Dify 登录密码</span><input type="password" autoComplete="new-password" value={password} disabled={busy} onChange={e=>setPassword(e.target.value)}/></label>
  <label className="repair-ack"><input type="checkbox" checked={rememberLogin} disabled={busy} onChange={e=>setRememberLogin(e.target.checked)}/><span>在本机加密保存登录资料，令牌过期时自动连接原环境</span></label>
  {error&&<div role="alert" className="callout amber">{error}</div>}
  <div className="callout amber">默认仅保存管理 Token 和 CSRF Token。勾选后会加密保存邮箱密码，仅用于此环境；登录失败即暂停，不自动重放写入，可在环境列表忘记登录资料。应用运行和知识库仍需独立 Key。</div>
  <button className="primary full" disabled={busy||!email.trim()||!password} onClick={()=>void submit()}>{busy?'正在登录并验证应用列表…':'登录并验证连接'}</button>
 </div>;
}
