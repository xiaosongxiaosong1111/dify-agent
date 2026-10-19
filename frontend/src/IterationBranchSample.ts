import {iterationSample} from './IterationSample';
/** A draft proposal; empty-item behavior must be accepted for the user's task. */
export function iterationBranchSample(appType:string){
 const sample=iterationSample(appType),original=sample.nodes[2],cfg=original.config as unknown as Record<string,unknown>&{nodes:{id:string;type:string;title?:string;config:Record<string,unknown>}[]};
 const nodes=[
  {id:'route_item',type:'if-else',title:'判断每项是否为空',config:{cases:[{case_id:'present',logical_operator:'and',conditions:[{variable_selector:['batch','item'],varType:'string',comparison_operator:'not empty',value:''}]}]}},
  cfg.nodes[0],
  {id:'empty_item',type:'template-transform',title:'空项保留索引',config:{template:'空项：{{ index }}',variables:[{variable:'index',value_selector:['batch','index'],value_type:'number'}]}},
  {id:'merged_item',type:'variable-aggregator',title:'汇合每项结果',config:{variables:[['clean_item','result'],['empty_item','output']],output_type:'string',selection_mode:'first_available'}}
 ];
 return {...sample,nodes:sample.nodes.map(n=>n.id==='batch'?{...n,title:'逐项条件处理与汇合',config:{...cfg,entry_node_id:'route_item',output_selector:['merged_item','output'],nodes,edges:[{source:'route_item',target:'clean_item',source_handle:'present'},{source:'route_item',target:'empty_item',source_handle:'false'},{source:'clean_item',target:'merged_item'},{source:'empty_item',target:'merged_item'}]}}:n)};
}
