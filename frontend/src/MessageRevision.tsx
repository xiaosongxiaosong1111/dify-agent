type Message={role?:string;context_revision?:number;result_revision?:number};
const revision=(value:unknown):value is number=>typeof value==='number'&&Number.isSafeInteger(value)&&value>0;
export default function MessageRevision({message,currentRevision}:{message:Message;currentRevision?:number}){
 if(!revision(message.context_revision))return <small className="message-revision">修订未记录 · 不作为当前确认</small>;
 const result=message.role==='assistant'&&revision(message.result_revision)?message.result_revision:undefined;
 const effective=result??message.context_revision;
 return <small className="message-revision">{effective===currentRevision?'当前修订相关':'历史修订'} · 输入v{message.context_revision}{result!==undefined?` → 结果v${result}`:''} · 对话记录，不代表当前确认</small>;
}
