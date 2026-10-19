"""Explicit Workflow file authoring; no fabricated upload objects or runtime access."""
import copy
TYPES={'file':'file','file-list':'array[file]'}
RUNTIME_LIMIT='文件入口已支持DSL生成及配置保留；可选单文件须存在分支保护，当前仅生成和保留；Sierra已提供明确批准的单次上传方案；TXT／MD／CSV／JSON／YAML／YML的三节点提取、四节点单文件LLM处理或五节点明确拼接列表LLM处理可另备数据流方案、核对归属并明确批准单次试跑；其他文件流程的冻结运行绑定尚未接通，不能用JSON对象／URL冒充已授权文件试跑。可导入Dify后手动上传验证，或确认改用已有HTTP文件来源；不会自动替换方案。'
EXTENSIONS={'.pdf','.docx','.txt','.md','.markdown','.csv','.json','.yaml','.yml','.html','.htm','.xml','.eml','.msg','.properties','.xls','.xlsx','.doc','.ppt','.pptx','.epub','.odt','.vtt'}
FIELDS={'variable','label','type','required','description','hide','default','options','max_length','allowed_file_types','allowed_file_extensions','allowed_file_upload_methods'}
def validate(row):
 errors=[]
 if set(row)-FIELDS:errors.append('文件入口含未适配字段，不会删除后生成。')
 if type(row.get('required')) is not bool:errors.append('文件入口须明确required为布尔值，不猜必填或可选。')
 elif row.get('type')=='file-list' and row['required'] is not True:errors.append('可选文件列表的null与空数组语义尚待适配；当前列表须明确required=true，仍允许空数组。')
 if row.get('hide',False) is not False:errors.append('文件入口须可见，hide只能为false。')
 for key in ('label','description'):
  if key in row and not isinstance(row[key],str):errors.append(f'{key}须为文本。')
 if row.get('default') is not None:errors.append('文件入口不能预填文件ID、URL或默认对象。')
 if row.get('options',[])!=[]:errors.append('文件入口不接受options。')
 types=row.get('allowed_file_types');ext=row.get('allowed_file_extensions');methods=row.get('allowed_file_upload_methods')
 if types not in (['document'],['custom']):errors.append('文件类型须明确为document或custom单项；其他文件类别尚待适配。')
 if not isinstance(ext,list) or any(not isinstance(x,str) or x not in EXTENSIONS for x in ext) or len(set(x for x in ext if isinstance(x,str)))!=len(ext):errors.append('文件扩展名须为已适配的小写点前缀列表，不能重复、通配或忽略未知格式。')
 elif types==['custom'] and not ext:errors.append('custom须明确扩展名列表，不能默认为允许所有文件。')
 elif types==['document'] and ext:errors.append('document类别不会据此收窄到指定扩展名；精确后缀范围请明确使用custom。')
 if not isinstance(methods,list) or not methods or any(not isinstance(x,str) or x not in {'local_file','remote_url'} for x in methods) or len(set(x for x in methods if isinstance(x,str)))!=len(methods):errors.append('上传方式须明确为local_file／remote_url的非空无重复列表，不代选。')
 limit=row.get('max_length')
 if row.get('type')=='file-list':
  if type(limit) is not int or not 1<=limit<=20:errors.append('文件列表须明确max_length为1—20；这是Sierra本批配置范围，不是平台全局上限，required仍允许空数组。')
 elif limit is not None:errors.append('单文件max_length不表示大小限制，本批须省略或null。')
 return errors

def native(row):
 value=copy.deepcopy(row);value.setdefault('label',row['variable']);return value

def has_files(rows):return isinstance(rows,list) and any(isinstance(row,dict) and isinstance(row.get('type'),str) and row['type'] in TYPES for row in rows)

def root_source(node,selector,kind):
 if node.get('type')!='start' or not isinstance(selector,list) or len(selector)!=2:return False
 rows=node.get('config',{}).get('variables',[])
 matches=[r for r in rows if isinstance(r,dict) and r.get('variable')==selector[1]] if isinstance(rows,list) else []
 return len(matches)==1 and matches[0].get('type')==kind and not validate(matches[0])
