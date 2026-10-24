import {useEffect,useRef,useState} from 'react';
type Row={scenario:string;name:string;input:{query:string};expectation:{mode:'equals';target:'answer';expected:string};required:true};
type Preview={schema_version:1;task_id:string;revision:number;request_nonce:string;dependency:string;artifact_sha256:string;plan_sha256:string;rows:Row[];note:string;verification:string;task_changed:false;network_requested:false;model_called:false;code_executed:false;business_verified:false};
export default function AfterSalesCaseDrafts({taskId,revision,scope,dependencies,disabled,onAppend}:{taskId:string;revision:number;scope:string;dependencies:string[];disabled:boolean;onAppend:(rows:Row[])=>boolean}){
 const [dependency,setDependency]=useState(''),[preview,setPreview]=useState<(Preview&{scope:string})|null>(null),[selected,setSelected]=useState<string[]>([]),[working,setWorking]=useState(false),[error,setError]=useState('');
 const epoch=useRef(0),controller=useRef<AbortController|null>(null),depScope=JSON.stringify(dependencies);
 useEffect(()=>{epoch.current++;controller.current?.abort();setPreview(null);setSelected([]);setWorking(false);setError('');return()=>{epoch.current++;controller.current?.abort()}},[taskId,revision,scope,dependency,disabled,depScope]);
 async function read(){
  if(disabled||working||!dependencies.includes(dependency))return;const ticket=++epoch.current,nonce=crypto.randomUUID(),abort=new AbortController();controller.current=abort;setWorking(true);setError('');setPreview(null);setSelected([]);const timer=setTimeout(()=>abort.abort(),15000);
  try{
   const r=await fetch(`/api/tasks/${encodeURIComponent(taskId)}/after-sales-cases-preview`,{method:'POST',headers:{'Content-Type':'application/json'},signal:abort.signal,body:JSON.stringify({revision,dependency,request_nonce:nonce})});if(ticket!==epoch.current)return;const v=await r.json();
   if(!r.ok)throw Error(typeof v.detail==='string'?v.detail:'无法准备订单样例草稿，原样例保持。');
   let expectedSha:unknown=null;try{expectedSha=JSON.parse(scope)?.sha256}catch{}
   if(typeof expectedSha==='string'&&v.artifact_sha256!==expectedSha)throw Error('样例来源与当前成果摘要不符，未采用。');
   if(v.schema_version!==1||v.task_id!==taskId||v.revision!==revision||v.request_nonce!==nonce||v.dependency!==dependency||v.verification!=='declared_mock_order_case_drafts_only'||!['artifact_sha256','plan_sha256'].every(k=>/^[a-f0-9]{64}$/.test(v[k]))||['task_changed','network_requested','model_called','code_executed','business_verified'].some(k=>v[k]!==false)||typeof v.note!=='string'||!Array.isArray(v.rows)||v.rows.length<3||v.rows.length>12||new Set(v.rows.map((x:Row)=>x.scenario)).size!==v.rows.length||v.rows.some((x:Row)=>typeof x.scenario!=='string'||typeof x.name!=='string'||!x.name||typeof x.input?.query!=='string'||Object.keys(x.input).join(',')!=='query'||x.expectation?.mode!=='equals'||x.expectation?.target!=='answer'||typeof x.expectation?.expected!=='string'||x.required!==true))throw Error('样例草稿归属或规则不匹配，未采用。');
   if(ticket===epoch.current)setPreview({...v,scope});
  }catch(e){if(ticket===epoch.current)setError(e instanceof Error?e.message:'样例草稿读取失败。')}
  finally{clearTimeout(timer);if(ticket===epoch.current)setWorking(false)}
 }
 const value=preview?.task_id===taskId&&preview.revision===revision&&preview.scope===scope&&!disabled?preview:null;
 return <details className="after-sales-case-drafts configuration-proposal"><summary><b>从售后模拟订单图准备样例草稿</b></summary><p className="hint">仅当前已构建且完整匹配的售后模板。准备每个合成订单命中、一个未知编号和缺订单号预期，不推断FAQ覆盖。选择后只追加未保存样例，不试跑或提高次数上限；已有样例保留。</p><label className="field"><span>所用订单模拟依赖</span><select aria-label="订单样例模拟依赖" value={dependency} disabled={disabled||working} onChange={e=>setDependency(e.target.value)}><option value="">请明确选择</option>{dependencies.map((s,i)=><option key={i} value={s}>{s}</option>)}</select></label><button className="secondary" disabled={disabled||working||!dependencies.includes(dependency)} onClick={()=>void read()}>读取合成订单样例草稿（不运行）</button>{working&&<p role="status">读取本机当前成果…</p>}{error&&<p role="alert">{error}</p>}
 {value&&<><p className="hint">{value.note}</p>{value.rows.map(row=><div className="case-card" key={row.scenario}><label><input type="checkbox" aria-label={`选择订单样例 ${row.scenario}`} checked={selected.includes(row.scenario)} onChange={e=>setSelected(xs=>e.target.checked?[...xs,row.scenario]:xs.filter(x=>x!==row.scenario))}/>{row.name} · 拟必选</label><pre>{JSON.stringify({input:row.input,expectation:row.expectation},null,2)}</pre></div>)}<button className="secondary" disabled={!selected.length||working} onClick={()=>{if(onAppend(value.rows.filter(r=>selected.includes(r.scenario)))){setPreview(null);setSelected([])}else setError('当前草稿变化或已有同输入同预期样例，未重复追加；请核对已有编辑。')}}>追加所选到未保存样例（不运行）</button></>}
 </details>;
}
