import type {DslSummary} from './ReferenceDslPanel';
const NODE_TYPES=new Set(['code','template-transform']),APP_TYPES=new Set(['workflow','advanced-chat']);
export function isSelectableReferenceNode(node:DslSummary['nodes'][number],summary:DslSummary){
 return !node.parent_id&&NODE_TYPES.has(node.type)&&APP_TYPES.has(summary.source.app_type)&&summary.source.app_type===summary.target_type;
}
export default function ReferenceNodeChoices({summary,selected,onChange,disabled=false}:{summary:DslSummary;selected:string[];onChange:(ids:string[])=>void;disabled?:boolean}){
 const compatible=APP_TYPES.has(summary.source.app_type)&&summary.source.app_type===summary.target_type;
 const selectable=new Set(summary.nodes.filter(n=>isSelectableReferenceNode(n,summary)).map(n=>n.id));
 const chosen=selected.filter(id=>selectable.has(id));
 const toggle=(id:string,checked:boolean)=>{const next=new Set(chosen);if(checked)next.add(id);else next.delete(id);onChange(summary.nodes.filter(n=>next.has(n.id)&&selectable.has(n.id)).map(n=>n.id))};
 return <fieldset className="reference-node-choices" disabled={disabled}><legend>保留节点选择（可选）</legend><p className="hint">仅核对选中根节点的完整配置，不锁定连线；其他规则、资源、变量和运行仍须核对。未选择节点时可保存讨论，但不能自动规划／构建。</p>{!compatible&&<p className="callout amber">参考应用类型与当前任务不同（{summary.source.app_type} → {summary.target_type}），不能选择保留节点；可按借鉴方式讨论迁移范围。</p>}{compatible&&!selectable.size&&<p className="callout amber">此参考没有根 code / template-transform 节点，无法选择；仍可保存讨论，但不能自动规划／构建。</p>}{compatible&&summary.nodes.map(n=>{const ok=selectable.has(n.id),checked=chosen.includes(n.id);return <label className="configuration-ack" key={n.id} title={ok?'':n.parent_id?'容器内节点不可选择；仅可选择根节点。':'仅支持根 code / template-transform 节点。'}><input type="checkbox" checked={checked} disabled={!ok||disabled} aria-label={`选择参考节点 ${n.title}（${n.id}）`} onChange={e=>toggle(n.id,e.target.checked)}/><span>{n.title} · {n.label}（{n.id}）{!ok&&<small> · {n.parent_id?'容器内节点不可选择':NODE_TYPES.has(n.type)?'参考类型与当前任务不同':'仅支持根 code / template-transform'}</small>}</span></label>})}<p className="hint">已选 {chosen.length} 个节点；选择不等于构建、运行或平台成功，最终须精确比较成功。</p></fieldset>;
}
