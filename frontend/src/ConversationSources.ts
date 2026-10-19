type Node={id:string;type:string;config?:Record<string,unknown>};type Plan={nodes:Node[];conversation_variables?:unknown};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
/** Only declaration candidates, never running conversation values or readiness claims. */
export function conversationSources(plan:Plan,kind?:string){
 const rows=plan.conversation_variables;if(!Array.isArray(rows))return [];
 if(plan.nodes.some(n=>n.id==='conversation'||Array.isArray(n.config?.nodes)&&(n.config.nodes as Node[]).some(c=>c?.id==='conversation')))return [];
 return rows.filter(object).filter(r=>typeof r.name==='string'&&/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(r.name)&&['string','number','boolean'].includes(String(r.var_type))&&(!kind||r.var_type===kind)&&rows.filter(other=>object(other)&&other.name===r.name).length===1).map(r=>({selector:['conversation',String(r.name)],type:String(r.var_type),label:`当前会话只读状态 · conversation.${r.name}（${r.var_type}）`}));
}
