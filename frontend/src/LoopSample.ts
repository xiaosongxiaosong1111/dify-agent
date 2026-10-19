/** Explicit technical policy proposal; review before saving/confirming. */
export function loopSample(appType:string){
 return {schema_version:1,nodes:[
  {id:'start',type:'start',title:'开始技术示例',config:{variables:[]}},
  {id:'repeat',type:'loop',title:'明确停止与无进展保护的循环',config:{loop_count:3,loop_variables:[{label:'count',var_type:'number',value_type:'constant',value:0}],
   nodes:[{id:'increment',type:'code',title:'每轮计数加一',config:{code_language:'python3',code:'def main(count: float) -> dict:\n    return {"next_count": count + 1}\n',variables:[{variable:'count',value_selector:['repeat','count']}],outputs:{next_count:{type:'number',children:null}}}}],
   updates:[{variable:'count',value_selector:['increment','next_count']}],break_conditions:[{variable_selector:['repeat','count'],varType:'number',comparison_operator:'≥',value:'3'}],logical_operator:'and',failure_policy:'terminate',limit_policy:'fail_if_unmet',no_progress_limit:2,progress_variables:['count'],progress_reason:'计数每轮增加，代表固定三次技术处理进度；不是客户业务验收。'}},
  appType==='advanced-chat'?{id:'answer',type:'answer',title:'返回技术计数',config:{answer:'循环计数：{{#repeat.count#}}'}}:{id:'end',type:'end',title:'返回技术计数',config:{outputs:[{variable:'count',value_selector:['repeat','count']}]}}
 ],edges:[{source:'start',target:'repeat'},{source:'repeat',target:appType==='advanced-chat'?'answer':'end'}]};
}
