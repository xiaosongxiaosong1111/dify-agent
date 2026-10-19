import {useEffect,useState} from 'react';
import type {FileChoice} from './RuntimeFilePanel';
// Insert a new field into the original JSON text. Never reserialize other values:
// doing so could round numbers, collapse duplicate keys or turn Infinity into null.
function appendField(input:string,name:string,ids:string[]){
 if(new TextEncoder().encode(input).length>64000)throw Error('原输入超过64000字节，未截断或改写。');
 let value:unknown;try{value=JSON.parse(input)}catch{throw Error('当前输入不是完整JSON对象，原文保持；请先明确修正。')}
 if(!value||typeof value!=='object'||Array.isArray(value))throw Error('当前输入须为JSON对象，未转换原值。');
 if(Object.hasOwn(value,name))throw Error('当前输入已含这个文件变量，未覆盖。请在完整输入中明确移除原文件字段，或保留当前输入继续编辑。');
 const end=input.lastIndexOf('}'),addition=`${Object.keys(value).length?',':''}\n${JSON.stringify(name)}: ${JSON.stringify(ids.map(id=>({sierra_file_id:id})),null,2)}\n`;
 const next=input.slice(0,end)+addition+input.slice(end);
 if(new TextEncoder().encode(next).length>64000)throw Error('填入后超过64000字节，原输入保持，不截断。');
 return next;
}
export default function FileReferenceList({taskId,revision,scope,choice,input,disabled,onChange}:{taskId:string;revision:number;scope:string;choice?:FileChoice|null;input:string;disabled:boolean;onChange:(text:string)=>void}){
 const [rows,setRows]=useState<FileChoice[]>([]),[error,setError]=useState('');
 useEffect(()=>{setRows([]);setError('')},[taskId,revision,scope]);
 const selected=choice?.task_id===taskId&&choice.revision===revision&&choice.input_kind==='file-list'?choice:null;
 if(!selected&&!rows.length)return null;
 const add=()=>{if(!selected||disabled)return;setError('');if(rows.length>=20){setError('列表草稿最多20项，不截断；最终入口可能有更小上限，准备方案时还会核对。');return}if(rows.length&&rows[0].variable!==selected.variable){setError('当前列表属于另一个文件变量，未混入或替换；可先明确清空此列表。');return}setRows([...rows,{...selected}])};
 const move=(index:number,offset:number)=>{if(disabled||index+offset<0||index+offset>=rows.length)return;const next=[...rows];[next[index],next[index+offset]]=[next[index+offset],next[index]];setRows(next);setError('')};
 return <div className="file-reference-list"><b>有序文件列表草稿 · 尚未填入输入</b><p className="hint">从上方已上传文件中选择，再主动追加。顺序和重复项按这里保留，文件名仅作提示。最多20项，真实入口数量、当前成果／目标／凭据及文件归属仍由后台准备方案逐项核对；这里不证明远端有效或已经试跑。</p>{selected&&<p>当前选择：{selected.filename} · {selected.variable}</p>}<button className="secondary" disabled={disabled||!selected} onClick={add}>将所选文件追加到列表草稿</button>{rows.map((row,i)=><div className="case-result" key={`${row.id}:${i}`}><b>{i+1}. {row.filename}</b><small>变量 {row.variable} · 上传记录 {row.id.slice(0,8)}</small><div className="actions"><button className="secondary" aria-label={`文件列表第${i+1}项上移`} disabled={disabled||i===0} onClick={()=>move(i,-1)}>上移</button><button className="secondary" aria-label={`文件列表第${i+1}项下移`} disabled={disabled||i===rows.length-1} onClick={()=>move(i,1)}>下移</button><button className="secondary" aria-label={`移除文件列表第${i+1}项`} disabled={disabled} onClick={()=>{setRows(rows.filter((_,n)=>n!==i));setError('')}}>移除</button></div></div>)}{rows.length>0&&<><button className="secondary" disabled={disabled} onClick={()=>{try{const next=appendField(input,rows[0].variable,rows.map(r=>r.id));onChange(next);setError('')}catch(e){setError(e instanceof Error?e.message:'输入保持，未填入列表。')}}}>将有序列表填入输入（保留其他参数）</button><button className="secondary" disabled={disabled} onClick={()=>{setRows([]);setError('')}}>清空文件列表草稿</button></>}<p className="hint">填入仅新增尚不存在的文件变量，其他JSON文字原样保留；不会覆盖已有文件字段，不自动上传、准备方案或运行。重复键、数值与完整入口约束由后台准备方案严格检查，这里不把语法检查当作通过。</p>{error&&<p className="error" role="alert">{error}</p>}</div>
}
