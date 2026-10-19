export function humanReviewSample(){
 const nodes:{id:string;type:string;title?:string;config:Record<string,unknown>}[]=[{id:'start',type:'start',title:'提交审核对象',config:{variables:[{variable:'query',type:'paragraph',required:true,max_length:10000}]}},{id:'review',type:'human-input',title:'人工审核',config:{form_content:'请审核以下内容：\n{{#start.query#}}',inputs:[],user_actions:[{id:'approve',title:'批准',button_style:'primary'},{id:'reject',title:'拒绝',button_style:'default'}],timeout:1,timeout_unit:'hour',delivery_methods:[{id:crypto.randomUUID(),type:'webapp',enabled:true,config:{}}]}}];
 const edges:{source:string;target:string;source_handle?:string}[]=[{source:'start',target:'review'}];
 for(const [handle,content] of [['approve','已批准'],['reject','已拒绝'],['__timeout','节点等待超时']]){const id=handle==='__timeout'?'timed_out':handle;nodes.push({id,type:'template-transform',config:{template:content,variables:[]}},{id:id+'_end',type:'end',config:{outputs:[{variable:'result',value_selector:[id,'output']}]}});edges.push({source:'review',target:id,source_handle:handle},{source:id,target:id+'_end'})}
 return {schema_version:1,nodes,edges};
}
