import {loopSample} from './LoopSample';
export function loopBranchSample(mode:string){
 const plan=loopSample(mode);
 const cfg=plan.nodes.find(n=>n.type==='loop')!.config as Record<string,unknown>;
 cfg.nodes=[
 {id:'route_count',type:'if-else',title:'按当前状态分支',config:{cases:[{case_id:'early',logical_operator:'and',conditions:[{variable_selector:['repeat','count'],varType:'number',comparison_operator:'<',value:'1'}]}]}},
 ...[['small_step',1],['large_step',2]].map(([id,step])=>({id:String(id),type:'code',title:`增加 ${step}`,config:{code_language:'python3',code:`def main(count: float) -> dict:\n    return {"next_count": count + ${step}}\n`,variables:[{variable:'count',value_selector:['repeat','count']}],outputs:{next_count:{type:'number',children:null}}}})),
 {id:'merge_step',type:'variable-aggregator',title:'汇合本轮更新',config:{variables:[['small_step','next_count'],['large_step','next_count']],output_type:'number',selection_mode:'first_available'}}];
 cfg.entry_node_id='route_count';cfg.edges=[{source:'route_count',source_handle:'early',target:'small_step'},{source:'route_count',source_handle:'false',target:'large_step'},{source:'small_step',target:'merge_step'},{source:'large_step',target:'merge_step'}];
 cfg.updates=[{variable:'count',value_selector:['merge_step','output']}];cfg.progress_reason='技术样例：按当前计数选择增加1或2，聚合本轮数值更新；不是客户业务改善的证明。';
 return plan;
}
