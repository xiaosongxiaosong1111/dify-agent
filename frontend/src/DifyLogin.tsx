import { useState } from 'react';

type Props = { name: string; baseUrl: string; connect: (email: string, password: string) => Promise<void> };
export default function DifyLogin({name, baseUrl, connect}: Props) {
 const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const submit=async()=>{
  if(busy)return;
  const transient=password;setPassword('');setBusy(true);setError('');
  try{await connect(email,transient)}catch(e){setError(e instanceof Error?e.message:'连接失败，请检查环境。')}finally{setBusy(false)}
 };
 return <div className="modal-body">
  <div className="callout">连接 {name}：{baseUrl}。请先在 Dify 页面创建管理员。此操作只登录并读取应用列表，不会注册或初始化账号。</div>
  <label className="field"><span>Dify 登录邮箱</span><input type="email" autoComplete="off" value={email} disabled={busy} onChange={e=>setEmail(e.target.value)}/></label>
  <label className="field"><span>Dify 登录密码（仅用于本次连接）</span><input type="password" autoComplete="new-password" value={password} disabled={busy} onChange={e=>setPassword(e.target.value)}/></label>
  {error&&<div role="alert" className="callout amber">{error}</div>}
  <div className="callout amber">成功后仅加密保存管理 Token 和 CSRF Token。登录过期需重新连接；应用运行 Key 和知识库 Key 需分别配置。</div>
  <button className="primary full" disabled={busy||!email.trim()||!password} onClick={()=>void submit()}>{busy?'正在登录并验证应用列表…':'登录并验证连接'}</button>
 </div>;
}
