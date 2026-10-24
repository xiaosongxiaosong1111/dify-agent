export type MockBinding={dependency:string;node_id:string;replacement_todo:string};
type Node={id:string;title?:string};
type Props={dependencies:string[];bindings:MockBinding[];nodes:Node[];disabled:boolean;onChange:(value:MockBinding[])=>void};

export default function MockDependencyHandoffs({dependencies,bindings,nodes,disabled,onChange}:Props){
 const declarations=[...new Set(dependencies.filter(value=>value.trim()))];
 if(!declarations.length&&!bindings.length)return null;
 const update=(dependency:string,patch:Partial<MockBinding>)=>onChange(bindings.map(item=>item.dependency===dependency?{...item,...patch}:item));
 return <section className="subpanel" aria-label="模拟依赖逐项接入待办">
  <h4>模拟依赖逐项接入待办</h4>
  <p className="hint">每项可关联一个位置并填写真实接口接入待办。构建只核对节点存在，不证明模拟行为或真实接入；保存后须重新确认配置。</p>
  {declarations.map(dependency=>{const item=bindings.find(row=>row.dependency===dependency);return <div key={dependency} className="callout" style={{display:'block'}}>
   <b>{dependency}</b>
   {!item?<button type="button" className="secondary" disabled={disabled||!nodes.length} onClick={()=>onChange([...bindings,{dependency,node_id:'',replacement_todo:''}])}>填写接入待办</button>:<>
    <label className="field"><span>声明位置 · {dependency}</span><select aria-label={`声明位置 · ${dependency}`} disabled={disabled} value={item.node_id} onChange={e=>update(dependency,{node_id:e.target.value})}>
     <option value="">请明确选择位置</option>
     {item.node_id&&!nodes.some(node=>node.id===item.node_id)&&<option value={item.node_id}>{item.node_id} · 当前不存在，请重选</option>}
     {nodes.map(node=><option key={node.id} value={node.id}>{node.title||node.id} · {node.id}</option>)}
    </select></label>
    <label className="field"><span>真实接入待办 · {dependency}</span><textarea aria-label={`真实接入待办 · ${dependency}`} disabled={disabled} maxLength={4000} value={item.replacement_todo} placeholder="填写替换接口、鉴权配置及需要重新验证的样例，不要填写密钥。" onChange={e=>update(dependency,{replacement_todo:e.target.value})}/></label>
    <button type="button" className="secondary" disabled={disabled} onClick={()=>onChange(bindings.filter(row=>row.dependency!==dependency))}>移除此项待办</button>
   </>}
  </div>})}
  {!nodes.length&&<p className="hint">请先保存显式流程计划后选择节点；原依赖声明仍可保留。</p>}
  {bindings.filter(item=>!declarations.includes(item.dependency)).map(item=><div className="callout amber" style={{display:'block'}} key={item.dependency}>
   原待办“{item.dependency}”已不对应当前依赖声明，构建会拒绝；请恢复声明或明确移除此待办。
   <button type="button" className="secondary" disabled={disabled} onClick={()=>onChange(bindings.filter(row=>row.dependency!==item.dependency))}>移除旧待办</button>
  </div>)}
 </section>;
}
