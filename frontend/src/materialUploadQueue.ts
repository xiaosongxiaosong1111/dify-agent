export type UploadItem={name:string;size:number;state:'waiting'|'uploading'|'parsed'|'needs_input'|'unknown';materialId?:string;revision?:number};
export type UploadProgress={taskId:string;running:boolean;stopping:boolean;items:UploadItem[];note:string};
type Task={id:string;revision:number;materials:{id:string;name?:string;status?:string}[]};
export function validateUploads(files:File[]){
 if(!files.length||files.length>10)throw Error('本页一次请选择1—10份材料；未开始上传。');
 if(files.some(f=>f.size>20*1024*1024))throw Error('有文件超过单份20MB，整批未开始；请拆分后重新选择。');
 if(files.reduce((total,f)=>total+f.size,0)>50*1024*1024)throw Error('本页一次合计最多50MB，整批未开始；请分批选择。');
}
export async function uploadMaterials<T extends Task>({files,task,stopRequested,canContinue,request,onSaved,publish}:{files:File[];task:T;stopRequested:()=>boolean;canContinue:(revision:number)=>boolean;request:(body:FormData)=>Promise<T>;onSaved:(value:T)=>boolean;publish:(value:UploadProgress)=>void}){
 const items:UploadItem[]=files.map(f=>({name:f.name,size:f.size,state:'waiting'}));let revision=task.revision;const known=new Set(task.materials.map(m=>m.id));
 const report=(running:boolean,note:string)=>publish({taskId:task.id,running,stopping:stopRequested(),items:items.map(item=>({...item})),note});
 report(true,'逐份本机上传；保存和解析状态分别显示。');
 for(let i=0;i<files.length;i++){
  if(stopRequested()||!canContinue(revision)){report(false,'已停止后续上传；已保存文件保留，其余未派发。');return}
  items[i].state='uploading';report(true,`正在上传第${i+1}/${files.length}份；停止仅阻止后续文件。`);
  try{
   const body=new FormData();body.append('file',files[i]);body.append('expected_revision',String(revision));const value=await request(body);
   if(value.id!==task.id||value.revision!==revision+1||!Array.isArray(value.materials))throw Error('上传回执归属或修订无法核对，请读取原任务，不自动重传。');
   const added=value.materials.filter(m=>!known.has(m.id));
   if(added.length!==1||!added[0].id||!['parsed','needs_input'].includes(added[0].status||'')||added[0].name!==files[i].name)throw Error('上传已返回，但材料记录无法唯一核对，请读取原任务，不自动重传。');
   const material=added[0];items[i]={...items[i],state:material.status as 'parsed'|'needs_input',materialId:material.id,revision:value.revision};known.add(material.id);revision=value.revision;
   if(!onSaved(value)){report(false,'原任务已返回上传结果；当前工作区已变化，未覆盖或继续后续上传。');return}
   report(true,`第${i+1}/${files.length}份已保存${material.status==='parsed'?'并提取文字':'，仍须补充可读文字'}。`);
  }catch(e){items[i].state='unknown';report(false,`本批停止：${e instanceof Error?e.message:'上传未完成'}。失败或响应中断不能推断文件未保存；请先核对原任务，未自动重传。`);throw e}
 }
 report(false,'所选文件均已保存；待补充文字仍是未解析，引用方式、需求和配置须按新修订核对。');
}
