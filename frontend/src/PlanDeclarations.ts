type Node={id:string;type:string;config?:Record<string,unknown>};
const object=(v:unknown):v is Record<string,unknown>=>v!==null&&typeof v==='object'&&!Array.isArray(v);
/** Display candidates only; the backend remains the authority for types and paths. */
export function declared(node:Node){
 const cfg=object(node.config)?node.config:{},rows:{field:string;type:string}[]=[];
 const add=(field:string,type:unknown)=>{if(typeof type==='string')rows.push({field,type})};
 if(node.type==='code'&&object(cfg.outputs))for(const [field,schema] of Object.entries(cfg.outputs))if(object(schema))add(field,schema.type);
 if(node.type==='start'&&Array.isArray(cfg.variables))for(const row of cfg.variables)if(object(row)&&typeof row.variable==='string'){if(row.type==='number')add(row.variable,'number');else if(row.type==='checkbox')add(row.variable,'boolean');else if(row.type==='json_object')add(row.variable,'object');else if(row.type==='file')add(row.variable,'file');else if(row.type==='file-list')add(row.variable,'array[file]');else if(['text-input','paragraph','select'].includes(String(row.type)))add(row.variable,'string')}
 if(node.type==='loop'&&Array.isArray(cfg.loop_variables))for(const row of cfg.loop_variables)if(object(row)&&typeof row.label==='string')add(row.label,row.var_type);
 if(node.type==='iteration'||node.type==='variable-aggregator')add('output',cfg.output_type);
 if(node.type==='list-operator')add('result',cfg.input_type);
 if(node.type==='document-extractor'){if(cfg.input_type==='file')add('text','string');else if(cfg.input_type==='array[file]')add('text','array[string]')}
 if(node.type==='template-transform')add('output','string');
 if(node.type==='llm')add('text','string');
 if(node.type==='question-classifier'){for(const field of ['class_id','class_name','class_label'])add(field,'string');add('usage','object')}
 if(node.type==='http-request'){add('body','string');add('status_code','number');add('headers','object');add('files','array[file]')}
 if(node.type==='parameter-extractor'){add('__is_success','number');add('__usage','object');if(Array.isArray(cfg.parameters))for(const row of cfg.parameters)if(object(row)&&typeof row.name==='string')add(row.name,row.type)}
 return rows;
}
