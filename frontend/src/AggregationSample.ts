/** Technical proposal: two exclusive branches, then first-available result. */
export function aggregationSample(appType:string){
 const query=appType==='advanced-chat'?['sys','query']:['start','query'];
 return {schema_version:1,nodes:[
  {id:'start',type:'start',title:'文字输入',config:{variables:appType==='advanced-chat'?[]:[{variable:'query',type:'paragraph',required:false,default:''}]}},
  {id:'route',type:'if-else',title:'判断输入是否为空',config:{cases:[{case_id:'missing',logical_operator:'and',conditions:[{variable_selector:query,varType:'string',comparison_operator:'empty',value:''}]}]}},
  {id:'ask',type:'template-transform',title:'提示补充输入',config:{template:'请补充输入内容。',variables:[]}},
  {id:'respond',type:'template-transform',title:'返回已收到的文字',config:{template:'已收到：{{ query }}',variables:[{variable:'query',value_selector:query,value_type:'string'}]}},
  {id:'merge',type:'variable-aggregator',title:'汇合分支结果',config:{variables:[['ask','output'],['respond','output']],output_type:'string',selection_mode:'first_available'}},
  appType==='advanced-chat'?{id:'answer',type:'answer',title:'共同回答出口',config:{answer:'{{#merge.output#}}'}}:{id:'end',type:'end',title:'共同结果出口',config:{outputs:[{variable:'result',value_selector:['merge','output']}]}}
 ],edges:[{source:'start',target:'route'},{source:'route',target:'ask',source_handle:'missing'},{source:'route',target:'respond',source_handle:'false'},{source:'ask',target:'merge'},{source:'respond',target:'merge'},{source:'merge',target:appType==='advanced-chat'?'answer':'end'}]};
}
