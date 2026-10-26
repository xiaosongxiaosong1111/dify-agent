import {validateTaskWindow} from './messageWindowTransport';
import {validateTextIndex,type TextMaterial} from './materialStoredTextTransport';
export type VersionSummary={schema_version:1;task_id:string;revision:number;state_sequence:number;state:'ready'|'unavailable';total_versions:number|null;returned_versions:number;body_omitted:true;unknown_revision_count:number;task_modified:false;model_called:false;external_network_requested:false;reason:string|null;note:string};
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const count=(v:unknown,max=Number.MAX_SAFE_INTEGER)=>Number.isSafeInteger(v)&&Number(v)>=0&&Number(v)<=max;
const short=(v:unknown,limit:number):v is string=>typeof v==='string'&&v.length<=limit*2&&Array.from(v).length<=limit;
const error=()=>Error('工作区版本索引、来源或读取范围无法核对；未把完整快照当作索引或静默回退。');
export function validateWorkspaceView(value:unknown,expectedMode:'compact'|'compact-v2'='compact'){
 validateTaskWindow(value);if(!object(value))throw error();
 const view=value.workspace_view,index=value.version_summary;
 if(!object(view)||view.schema_version!==(expectedMode==='compact'?1:2)||view.mode!==expectedMode||view.task_id!==value.id||view.revision!==value.revision||view.state_sequence!==(value.state_sequence??0)||view.messages_view!=='recent'||view.versions_view!=='index'||['task_modified','model_called','external_network_requested','business_verified'].some(k=>view[k]!==false))throw error();
 if(expectedMode==='compact-v2'){
  if(view.materials_view!=='stored_text_index'||!Array.isArray(value.materials))throw error();const ids=new Set<string>();
  for(const material of value.materials){if(!object(material)||typeof material.id!=='string'||!material.id||ids.has(material.id)||Object.hasOwn(material,'text')||Object.hasOwn(material,'partial_text'))throw error();ids.add(material.id);validateTextIndex(material.text_view,String(value.id),Number(value.revision),material as TextMaterial)}
 }
 if(!object(index)||index.schema_version!==1||index.task_id!==value.id||index.revision!==value.revision||index.state_sequence!==(value.state_sequence??0)||!['ready','unavailable'].includes(String(index.state))||index.body_omitted!==true||!count(index.returned_versions,5000)||!count(index.unknown_revision_count,5000)||!(index.total_versions===null||count(index.total_versions))||typeof index.note!=='string'||['task_modified','model_called','external_network_requested'].some(k=>index[k]!==false)||!Array.isArray(value.versions))throw error();
 if(index.state==='unavailable'){if(index.returned_versions!==0||index.unknown_revision_count!==0||value.versions.length!==0||!['invalid_history','version_count_limit','version_id_invalid','version_id_ambiguous','metadata_invalid','metadata_limit','metadata_encoding','index_bytes_limit'].includes(String(index.reason)))throw error();return}
 if(index.reason!==null)throw error();
 if(!count(index.total_versions,5000)||index.total_versions!==index.returned_versions||index.returned_versions!==value.versions.length||Number(index.unknown_revision_count)>Number(index.total_versions))throw error();
 const seen=new Set<string>();let unknown=0;
 for(const row of value.versions){
  if(!object(row)||!short(row.id,200)||!row.id.trim()||/[\u0000-\u001f\u007f]/.test(row.id)||seen.has(row.id)||Object.keys(row).some(k=>!['id','revision','label','kind','created_at'].includes(k)))throw error();
  seen.add(row.id);
  if(Object.hasOwn(row,'revision')){if(!count(row.revision)||Number(row.revision)<1)throw error()}else unknown++;
  if(Object.hasOwn(row,'label')&&!short(row.label,2000)||Object.hasOwn(row,'kind')&&!short(row.kind,100)||Object.hasOwn(row,'created_at')&&!short(row.created_at,100))throw error();
 }
 if(unknown!==index.unknown_revision_count||new TextEncoder().encode(JSON.stringify(value.versions)).length>2_000_000)throw error();
}
