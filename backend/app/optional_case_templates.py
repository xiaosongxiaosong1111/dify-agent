"""Read-only explicit optional-file scenarios; drafts never imply business truth."""
import hashlib,json
from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import JSONResponse
from .plan_drafts import DraftRoute
from .node_policy_audit import read_bytes
from .dsl_roundtrip import parse,validate_preserved
from .optional_file_run_flow import describe
from .file_formats import FORMATS

NOTE='仅从当前最终DSL准备未保存样例建议，不读文件正文／实际输入／运行输出，不解密凭据或请求模型／Dify。缺失说明规则来自配置，不证明客户业务正确；须主动填入、保存样例并另准备和确认一次试跑。不会覆盖原样例、造文件引用或授权运行。'

def templates(root):
 checked=validate_preserved(root)
 if not checked['valid']:raise ValueError('成果未完整适配')
 flow=describe(root);o=flow['optional_file'];file=flow['file_variable'];default=o['missing_message_default']
 start=next(n for n in root['workflow']['graph']['nodes'] if n['id']==o['start_node_id'])
 declaration=next(v for v in start['data']['variables'] if v['variable']==file)
 extensions=declaration.get('allowed_file_extensions')
 if not isinstance(extensions,list) or not extensions or any(e not in FORMATS for e in extensions):raise ValueError('声明含未适配试跑后缀，不能省略后生成样例')
 expectation={'mode':'equals','target':o['output_variable'],'expected':default}
 rows=[{'scenario':'missing_omitted','name':'未提供文件：省略字段','input':{},'expectation':expectation,'input_ready':True,'reason':'文件字段省略；说明参数省略，按最终DSL明确默认值返回，不能用空对象冒充。'},
       {'scenario':'missing_null','name':'未提供文件：明确null','input':{file:None},'expectation':expectation,'input_ready':True,'reason':'明确传入null，与省略分别保留为独立样例；不是文件ID或空串。'},
       {'scenario':'file_present','name':'提供文件：提取原文','input':None,'expectation':None,'input_ready':False,'reason':'先按当前任务／成果／目标明确上传并选用可信文件引用，再由用户定义提取内容或人工规则；不猜文件字节、提取文字或业务通过条件。'}]
 return {'schema_version':1,'rows':rows,'file_variable':file,'allowed_file_extensions':extensions,'guard_node_id':o['guard_node_id'],'comparison_operator':o['comparison_operator'],'missing_message_variable':o['missing_message_variable'],'missing_message_default':default,'output_variable':o['output_variable'],'verification':'declared_optional_branch_drafts_only','network_requested':False,'credentials_decrypted':False,'task_changed':False,'catalog_changed':False,'file_uploaded':False,'workflow_runs':0,'business_verified':False,'note':NOTE}

class OptionalCaseTemplates:
 def __init__(self,h):self.h=h
 def register(self):
  h=self.h;router=APIRouter(route_class=DraftRoute)
  @router.get('/api/tasks/{item_id}/optional-file-case-templates')
  def read(item_id:str,revision:int=Query(ge=1)):
   with h.store.lock:
    task=h.get_task(item_id);h.require_revision(task,revision)
    if task['app_type']!='workflow':raise HTTPException(422,'可选文件分支样例仅适配Workflow，不改变应用类型。')
    path=h.artifact_path(task)
    try:
     raw=read_bytes(path);result=templates(parse(raw.decode('utf-8'),'workflow'))
    except (ValueError,UnicodeError,KeyError,TypeError,AttributeError,RecursionError):raise HTTPException(422,'当前最终成果不能完整准备可选文件样例；仅适配已支持的五根节点纯提取／明确缺失说明图及六种后缀。不删除其他行为或返回部分成功。') from None
    except OSError:raise HTTPException(503,'最终成果暂不可读，没有采用旧计划或调用外部服务。') from None
    latest=h.get_task(item_id);h.require_revision(latest,revision)
    try:
     if h.artifact_path(latest)!=path or read_bytes(path)!=raw:raise HTTPException(409,'读取期间成果改变，请重新准备当前样例建议。')
    except (ValueError,OSError):raise HTTPException(409,'读取期间成果无法固定，未采用旧来源。') from None
    return JSONResponse({**result,'task_id':item_id,'revision':revision,'artifact_sha256':hashlib.sha256(raw).hexdigest()},headers={'Cache-Control':'no-store'})
  h.app.include_router(router)
