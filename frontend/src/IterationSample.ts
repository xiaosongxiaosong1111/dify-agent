/** A local editable proposal, not an approved business workflow. */
export function iterationSample(appType:string,parallel=false){
 const query=appType==='advanced-chat'?['sys','query']:['start','items_json'];
 return {schema_version:1,nodes:[
  {id:'start',type:'start',title:'批量输入',config:{variables:appType==='advanced-chat'?[]:[{variable:'items_json',label:'JSON 字符串数组，如 ["alpha","beta"]',type:'paragraph',required:true}]}},
  {id:'parse_items',type:'code',title:'校验并解析输入数组',config:{code_language:'python3',variables:[{variable:'items_json',value_selector:query}],code:'import json\n\ndef main(items_json: str) -> dict:\n    items = json.loads(items_json)\n    if not isinstance(items, list) or len(items) > 100 or any(not isinstance(item, str) for item in items):\n        raise ValueError("输入须为最多 100 项的 JSON 字符串数组")\n    return {"items": items}\n',outputs:{items:{type:'array[string]',children:null}}}},
  {id:'batch',type:'iteration',title:parallel?'独立文本并行处理':'按原顺序逐项处理',config:{iterator_selector:['parse_items','items'],iterator_input_type:'array[string]',output_selector:['clean_item','result'],output_type:'array[string]',is_parallel:parallel,...(parallel?{parallel_nums:3,parallel_safe:true,parallel_reason:'每项仅去空白并转大写，不读写共享数据，不访问外部接口，不依赖其他项的执行顺序。请按实际业务复核后确认。'}:{}),error_handle_mode:'terminated',flatten_output:false,nodes:[{id:'clean_item',type:'code',title:'去空白并转大写',config:{code_language:'python3',variables:[{variable:'item',value_selector:['batch','item']}],code:'def main(item: str) -> dict:\n    return {"result": item.strip().upper()}\n',outputs:{result:{type:'string',children:null}}}}]}},
  appType==='advanced-chat'?{id:'answer',type:'answer',title:'返回汇总结果',config:{answer:'{{#batch.output#}}'}}:{id:'end',type:'end',title:'返回汇总结果',config:{outputs:[{variable:'results',value_selector:['batch','output']}]}}
 ],edges:[{source:'start',target:'parse_items'},{source:'parse_items',target:'batch'},{source:'batch',target:appType==='advanced-chat'?'answer':'end'}]};
}
