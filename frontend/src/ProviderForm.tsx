import {useEffect,useRef,useState} from 'react';
import {ShieldCheck} from 'lucide-react';

type Pricing={input_per_million_usd:number;output_per_million_usd:number;cached_input_per_million_usd?:number};
type Choice={id:string;label:string;model:string;description:string;note:string;pricing:Pricing;request_profile:string};
type Vendor={id:string;name:string;mark:string;base_url:string;protocol:string;source_url:string;pricing_basis:string;models:Choice[]};
export type ProviderCatalog={verified_at:string;vendors:Vendor[];availability:string};
type Initial={id?:string;name?:string;provider?:string;base_url?:string;model?:string;role?:string;protocol?:string;has_api_key?:boolean;preset_id?:string;pricing?:Pricing|null;pricing_note?:string;configuration_revision?:number};
type Props={initial:Initial;busy:boolean;load:()=>Promise<ProviderCatalog>;save:(body:Record<string,unknown>)=>Promise<void>};
const sameOrigin=(a:string,b:string)=>{try{return new URL(a).origin===new URL(b).origin}catch{return false}};
const sameIdentity=(initial:Initial,v:Vendor,m:Choice)=>initial.provider===v.id&&initial.base_url?.replace(/\/$/,'')===v.base_url.replace(/\/$/,'')&&initial.model===m.model&&initial.protocol===v.protocol;
const asRates=(p?:Pricing|null)=>({input:p?.input_per_million_usd?.toString()??'',output:p?.output_per_million_usd?.toString()??'',cached:p?.cached_input_per_million_usd?.toString()??''});

export default function ProviderForm({initial,busy,load,save}:Props){
 const [catalog,setCatalog]=useState<ProviderCatalog|null>(null),[loading,setLoading]=useState(true),[loadError,setLoadError]=useState(''),[error,setError]=useState('');
 const [vendorId,setVendorId]=useState(''),[modelId,setModelId]=useState(''),[key,setKey]=useState(''),[name,setName]=useState(initial.name||''),[role,setRole]=useState(initial.role||'main');
 const [custom,setCustom]=useState({provider:initial.provider||'custom',base_url:initial.base_url||'',model:initial.model||'',protocol:initial.protocol||'openai-compatible'});
 const [rates,setRates]=useState(asRates(initial.pricing)),[priceEdited,setPriceEdited]=useState(false),[retry,setRetry]=useState(0);const chosen=useRef(false);
 useEffect(()=>{let live=true;setLoading(true);setLoadError('');load().then(data=>{if(!live)return;setCatalog(data);if(chosen.current)return;
  if(initial.id){const match=data.vendors.flatMap(v=>v.models.map(m=>({v,m}))).find(({v,m})=>sameIdentity(initial,v,m));if(match){setVendorId(match.v.id);setModelId(match.m.id);setRates(asRates(initial.pricing||match.m.pricing));}else setVendorId('custom');}
 }).catch(e=>{if(live)setLoadError(e instanceof Error?e.message:'预设列表读取失败。')}).finally(()=>{if(live)setLoading(false)});return()=>{live=false}},[retry]);
 const vendor=catalog?.vendors.find(v=>v.id===vendorId),choice=vendor?.models.find(m=>m.id===modelId),isCustom=vendorId==='custom';
 const baseUrl=isCustom?custom.base_url:vendor?.base_url||'';
 const canRetain=!!initial.has_api_key&&sameOrigin(initial.base_url||'',baseUrl);
 const chooseVendor=(id:string)=>{chosen.current=true;setError('');setPriceEdited(false);const v=catalog?.vendors.find(x=>x.id===id),m=v?.models[0];
  const nextUrl=id==='custom'?baseUrl:v?.base_url||'';if(!sameOrigin(baseUrl,nextUrl))setKey('');
  if(id==='custom'&&vendor&&choice){setCustom({provider:vendor.id,base_url:vendor.base_url,model:choice.model,protocol:vendor.protocol});}
  setVendorId(id);setModelId(m?.id||'');if(v&&m)setRates(asRates(sameIdentity(initial,v,m)?initial.pricing||m.pricing:m.pricing));
 };
 const chooseModel=(id:string)=>{setModelId(id);setError('');setPriceEdited(false);const m=vendor?.models.find(x=>x.id===id);if(vendor&&m)setRates(asRates(sameIdentity(initial,vendor,m)?initial.pricing||m.pricing:m.pricing));};
 const submit=async(e:React.FormEvent)=>{e.preventDefault();setError('');if(busy)return;try{
  if(!vendorId||(!isCustom&&!choice))throw Error('请先选择服务商和型号。');
  if(!key.trim()&&!canRetain)throw Error('请填写当前服务商的 API Key。');
  let body:Record<string,unknown>={...(name.trim()?{name:name.trim()}:{}),role:role==='assistant'?'main':role,...(key.trim()?{api_key:key.trim()}:{})};
  if(isCustom){if(!custom.base_url.trim()||!custom.model.trim())throw Error('自定义接入需要服务地址和模型名称。');body={...body,...custom,name:name.trim()||`自定义 · ${custom.model.trim()}`,preset_id:null};}
  else body.preset_id=modelId;
  if(priceEdited||(isCustom&&!initial.id)){
   if(rates.input===''&&rates.output===''&&rates.cached==='')body.pricing=null;
   else {if(rates.input===''||rates.output==='')throw Error('输入与输出单价需同时填写。');const p={input_per_million_usd:Number(rates.input),output_per_million_usd:Number(rates.output),...(rates.cached!==''?{cached_input_per_million_usd:Number(rates.cached)}:{})};if(Object.values(p).some(x=>!Number.isFinite(x)||x<0))throw Error('参考单价须为非负有限数字。');body.pricing=p;}
   body.pricing_note='用户填写或调整的估算单价；单位 USD／百万 tokens，不是供应商账单。';
  }
  await save(body);setKey('');
 }catch(e){setError(e instanceof Error?e.message:'保存失败，请检查配置。')}};
 return <form id="provider-form" className="modal-body provider-form" onSubmit={submit}><fieldset disabled={busy} style={{border:0,padding:0,margin:0,minWidth:0}}>
  <p className="provider-intro">选服务商、选型号，填入 API Key 即可。用于本工作台的需求访谈与 DSL 规划。</p>
  {initial.id&&<p className="hint">编辑来源版本 {initial.configuration_revision??0}；保存前会核对来源。其它页面改过配置时会拒绝旧页，当前输入保留；请另存文字后关闭编辑，在模型列表重新读取再打开核对，不自动重读或测试。</p>}
  <div className="provider-step"><span>1</span><b>选择服务商</b></div>
  {loading&&<p className="hint">正在读取常用模型...</p>}
  {loadError&&<div className="callout amber">无法读取预设列表：{loadError}<button type="button" className="secondary" onClick={()=>setRetry(x=>x+1)}>重新读取</button></div>}
  <div className="provider-vendors" role="radiogroup" aria-label="模型服务商">
   {catalog?.vendors.map(v=><button type="button" role="radio" aria-checked={vendorId===v.id} className={`vendor-choice ${vendorId===v.id?'selected':''}`} key={v.id} onClick={()=>chooseVendor(v.id)} disabled={busy}><span className={`vendor-mark ${v.id}`}>{v.mark}</span><span><b>{v.name}</b><small>官方 API</small></span>{vendorId===v.id&&<span className="vendor-tick">✓</span>}</button>)}
   <button type="button" role="radio" aria-checked={isCustom} className={`vendor-choice custom-choice ${isCustom?'selected':''}`} onClick={()=>chooseVendor('custom')} disabled={busy}><span className="vendor-mark">＋</span><span><b>自定义 / 兼容服务</b><small>代理地址、其他模型或现有自定义接入</small></span></button>
  </div>
  <div className="provider-step"><span>2</span><b>{isCustom?'填写自定义接入':'选择型号'}</b></div>
  {isCustom?<><label className="field"><span>服务地址</span><input aria-label="自定义服务地址" value={custom.base_url} onChange={e=>{if(!sameOrigin(custom.base_url,e.target.value))setKey('');setCustom({...custom,base_url:e.target.value});setRates(asRates());setPriceEdited(true)}} placeholder="https://你的服务地址/v1" required/></label><div className="field-grid"><label className="field"><span>模型名称</span><input aria-label="自定义模型名称" value={custom.model} onChange={e=>{setCustom({...custom,model:e.target.value});setRates(asRates());setPriceEdited(true)}} required/></label><label className="field"><span>接口协议</span><select value={custom.protocol} onChange={e=>setCustom({...custom,protocol:e.target.value})}><option value="openai-compatible">OpenAI 兼容</option><option value="anthropic">Anthropic</option></select></label></div><p className="hint">自定义服务请在高级设置填写参考单价，才能进行自动规划的费用预检。</p></>:<><label className="field"><span>模型型号</span><select aria-label="模型型号" value={modelId} onChange={e=>chooseModel(e.target.value)} disabled={!vendor||busy} required><option value="">{vendor?'请选择型号':'先选择服务商'}</option>{vendor?.models.map(m=><option key={m.id} value={m.id}>{m.label}</option>)}</select></label>{choice&&<div className="preset-summary"><b>{choice.label}</b><p>{choice.description}</p>{choice.note&&<p className="preset-note">{choice.note}</p>}<small>接口与参考单价已自动配置，保存后可测试连接。</small></div>}</>}
  <div className="provider-step"><span>3</span><b>填写 API Key</b></div>
  <label className="field"><span>API Key{canRetain?' · 已保存，留空继续使用':''}</span><input aria-label="模型 API Key" type="password" autoComplete="new-password" value={key} onChange={e=>setKey(e.target.value)} placeholder={canRetain?'无需重复填写已保存的密钥':'粘贴该服务商的 API Key'} required={!canRetain} disabled={busy}/></label>
  {initial.has_api_key&&!canRetain&&vendorId&&<p className="hint">已切换服务地址，请填写新服务的 Key。</p>}
  <details className="provider-advanced"><summary>高级设置（可选）</summary><label className="field"><span>显示名称</span><input value={name} onChange={e=>setName(e.target.value)} placeholder={choice&&vendor?`${vendor.name} · ${choice.label}`:'保存时自动命名'}/></label><label className="field"><span>用途</span><select aria-label="模型用途" value={role==='assistant'?'main':role} onChange={e=>setRole(e.target.value)}><option value="main">助手（需求访谈与规划）</option><option value="light">轻量模型</option><option value="vision">识图模型</option></select></label>
   {isCustom?<label className="field"><span>服务商标识</span><input value={custom.provider} onChange={e=>setCustom({...custom,provider:e.target.value})}/></label>:vendor&&<div className="preset-technical"><span>服务地址：{vendor.base_url}</span><span>接口协议：{vendor.protocol}</span><span>API 模型名称：{choice?.model||'未选择'}</span><p>需使用代理或其他地址时，选择“自定义 / 兼容服务”。</p></div>}
   <p className="hint">参考价单位为 USD／百万 tokens，用于规划费用预检，不是实际账单。{vendor?.pricing_basis} 核对日期：{catalog?.verified_at||'未读取'}。</p>
   <div className="field-grid">{([['input','输入单价'],['output','输出单价'],['cached','缓存命中输入单价（可选）']] as const).map(([id,label])=><label className="field" key={id}><span>{label}</span><input aria-label={label} type="number" min="0" step="any" value={rates[id]} onChange={e=>{setRates({...rates,[id]:e.target.value});setPriceEdited(true)}}/></label>)}</div>
   {vendor&&<a href={vendor.source_url} target="_blank" rel="noreferrer">查看官方模型与价格说明</a>}
  </details>
  <p className="provider-key-note"><ShieldCheck size={15}/>Key 在本机后台加密保存，不写入浏览器存储。保存不会自动发起付费模型调用。</p>
  {error&&<div className="callout amber" role="alert">{error}</div>}
 </fieldset></form>;
}
