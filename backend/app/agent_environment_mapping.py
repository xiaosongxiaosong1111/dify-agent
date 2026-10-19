"""Stateless native Agent target-environment draft preview; never writes or calls Dify."""
import copy,json,re,uuid
import yaml
from fastapi import APIRouter,HTTPException,Path as ApiPath
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,ValidationError
from .dsl_roundtrip import parse,digest
from .agent_plan import compile_agent_plan
from .agent_preservation import validate as validate_agent
from .agent_knowledge_preservation import project as project_knowledge
from .model_parameters import validate_node_model
from .providers import checked_url,ProviderError
from .run_input_transport import validate as exact_json,AmbiguousInput

MARKER='Sierra：目标资源待验证映射草稿；模型、知识库和插件尚未核对，ID对应不证明资料等价，尚未导入或试跑。'
MODEL_MOCK='跨环境目标模型与插件待核对（映射预览不证明可用）'
DATASET_MOCK='跨环境目标知识库与资料覆盖待核对（ID对应不证明等价）'


def mapping_error(exc):return str(exc).replace('试跑请求','映射预览请求').replace('派发','生成映射草稿')


class MappingRoute(APIRoute):
    field_error='映射预览字段无效，请核对修订、来源摘要、目标环境和完整模型JSON；不回显输入，未生成草稿。'
    def transport_error(self,exc):return mapping_error(exc)
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            if request.method in {'POST','PUT','PATCH'}:
                try:exact_json(await request.body())
                except AmbiguousInput as exc:return JSONResponse(status_code=422,content={'detail':self.transport_error(exc)})
            try:return await original(request)
            except RequestValidationError:return JSONResponse(status_code=422,content={'detail':self.field_error})
        return guarded


def source_summary(root):
    """Only a statically supported native package; no resource lookup or identity guesses."""
    from .agent_model_comparison import model,configuration
    try:
        cfg=configuration(model(root))
        pkg=root['agent_packages'][root['agent']['package_ref']]
        ids=sorted({d['id'] for group in pkg['soul']['knowledge']['sets'] for d in group['datasets']})
        node={'provider':cfg['dify_model_provider'],'name':cfg['dify_model'],'mode':'chat',
              'completion_params':{'temperature':cfg['temperature'],'max_tokens':cfg['max_tokens'],**cfg['model_parameters']}}
        return {'available':True,'dataset_ids':ids,'model_template_json':json.dumps(node,ensure_ascii=False,indent=2),
                'note':'模板来自当前合并预览，仅供完整填写目标配置；不代表目标模型或资料已经核对。'}
    except (ValueError,KeyError,TypeError,AttributeError,OverflowError):
        return {'available':False,'reason':'当前模型或知识集不能完整整理为目标输入，原文件保留；请先解决来源配置。'}


class MappingRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(gt=0)
    reference_id:str=Field(min_length=1,max_length=100)
    merge_token:str=Field(pattern=r'^[0-9a-f]{64}$')
    document_token:str=Field(pattern=r'^[0-9a-f]{64}$')
    choices:dict[str,str]=Field(default_factory=dict,max_length=1000)
    target_environment_id:str=Field(min_length=1,max_length=100)
    target_model_json:str=Field(min_length=1,max_length=30000)
    dataset_mapping:dict[str,str]=Field(default_factory=dict,max_length=100)
    target_dependency:str|None=Field(default=None,max_length=1024)
    acknowledge_unverified_target:StrictBool=False


def target_model(text):
    try:value=exact_json(text.encode('utf-8'))
    except (AmbiguousInput,UnicodeError) as exc:raise ValueError('目标模型JSON无法完整核对：'+(mapping_error(exc) if isinstance(exc,AmbiguousInput) else '编码无效；不回显输入。')) from None
    params=value.get('completion_params')
    if isinstance(params,dict):
        for item in params.values():
            if type(item) in (int,float) and abs(item)>9007199254740991:raise ValueError('目标模型参数超出浏览器精确数值范围，不能舍入后预览。')
    try:validate_node_model(value)
    except OverflowError as exc:raise ValueError('目标模型参数数值范围无法完整核对。') from exc
    if not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+',value['provider']):raise ValueError('目标原生Agent模型须明确author/plugin/provider，不能猜测插件身份。')
    return value


def target_public(env):
    if not isinstance(env,dict) or any(not isinstance(env.get(k),str) or not env[k].strip() for k in ('id','base_url','version')):raise ValueError('目标环境记录不完整，请先配置目标连接。')
    try:checked_url(env['base_url'])
    except (ProviderError,ValueError):raise ValueError('目标环境基础地址无效或包含凭据／查询参数，请先修复连接；不回显地址。') from None
    if any(ord(c)<32 for c in env['base_url']):raise ValueError('目标环境地址含控制字符，请先修复连接；不回显地址。')
    return {'id':env['id'],'name':env.get('name') if isinstance(env.get('name'),str) else env['id'],
        'base_url':env['base_url'],'version':env['version']}


def build(task,source,target,model_text,mapping,dependency=None):
    if task.get('app_type')!='agent':raise ValueError('首批环境映射仅预览原生Agent，不转换Workflow或Chatflow类型。')
    if source.get('unresolved') or source.get('validation',{}).get('valid') is not True:raise ValueError('请先在原环境处理全部冲突和静态阻止项，再准备映射；不删除功能后迁移。')
    public=target_public(target)
    if public['id']==task.get('environment_id'):raise ValueError('请另选不同的目标环境连接；同环境修改请使用现有保留流程。')
    root=parse(source['content'],'agent');ref=root['agent']['package_ref'];pkg=root['agent_packages'][ref];soul=pkg['soul']
    rows=project_knowledge(soul['knowledge'],soul['knowledge'],soul['prompt']['system_prompt'])
    ids={i for row in rows for i in row['dataset_ids']}
    if not isinstance(mapping,dict) or set(mapping)!=ids:raise ValueError('必须逐一明确当前预览的全部知识库ID对应，不能漏库、添库或按同名推测。')
    for value in mapping.values():
        try:valid=isinstance(value,str) and str(uuid.UUID(value))==value
        except (ValueError,AttributeError):valid=False
        if not valid:raise ValueError('目标知识库ID须为明确的小写连字符UUID，不接受名称、占位词或连接密钥。')
    if len(set(mapping.values()))!=len(mapping):raise ValueError('首批映射须一一对应，不将不同源知识库合并后假定资料范围未变。')
    chosen=target_model(model_text);params=copy.deepcopy(chosen['completion_params'])
    cfg=copy.deepcopy(task['configuration'])
    cfg.update(dify_model_provider=chosen['provider'],dify_model=chosen['name'],temperature=params.pop('temperature'),max_tokens=params.pop('max_tokens'),model_parameters=params)
    mocks=cfg.get('mock_dependencies',[])
    if not isinstance(mocks,list) or any(not isinstance(v,str) for v in mocks):raise ValueError('原模拟依赖清单不明确，请先复核，不能静默清除旧条件。')
    cfg['mock_dependencies']=[*mocks]
    for label in [MODEL_MOCK,*([DATASET_MOCK] if ids else [])]:
        if label not in cfg['mock_dependencies']:cfg['mock_dependencies'].append(label)
    mapped_rows=copy.deepcopy(rows)
    for row in mapped_rows:row['dataset_ids']=[mapping[i] for i in row['dataset_ids']]
    cfg['dataset_ids']=list(dict.fromkeys(i for row in mapped_rows for i in row['dataset_ids']))
    plan={'schema_version':1,'scope':'knowledge' if rows else 'text','system_prompt':soul['prompt']['system_prompt']}
    if rows:plan['knowledge_sets']=mapped_rows
    proposed=copy.deepcopy(task);proposed.update(environment_id=public['id'],configuration=cfg,agent_plan=plan)
    generated,checked=compile_agent_plan(proposed)
    if not checked['valid']:raise ValueError('目标原生Agent生成建议无法静态检查。')
    generated_root=parse(generated,'agent');new_model=copy.deepcopy(generated_root['agent_packages']['agent_1']['soul']['model'])
    output=copy.deepcopy(root);out_soul=output['agent_packages'][ref]['soul'];out_soul['model']=new_model
    labels=[]
    for knowledge in out_soul['knowledge']['sets']:
        for dataset in knowledge['datasets']:
            original=copy.deepcopy(dataset);dataset['id']=mapping[dataset['id']]
            # Source display labels are not evidence for target dataset identity.
            for key in ('name','description'):
                if key in dataset:dataset[key]=None
            if original!=dataset:labels.append({'source':original,'target':copy.deepcopy(dataset)})
    deps=copy.deepcopy(root.get('dependencies',[]))
    if dependency is not None:
        plugin=new_model['plugin_id']
        if not dependency.startswith(plugin+':') or len(dependency)<=len(plugin)+1 or any(c.isspace() or ord(c)<32 for c in dependency):raise ValueError('目标市场依赖须明确属于所选模型插件，不猜测版本或安装来源。')
        output['dependencies']=[{'type':'marketplace','value':{'marketplace_plugin_unique_identifier':dependency,'version':None},'current_identifier':None}]
    elif deps and soul['model']['plugin_id']!=new_model['plugin_id']:
        raise ValueError('更换插件且源文件有固定依赖，请补充目标市场插件完整标识；不会清空旧依赖后算迁移完成。')
    description=output['app'].get('description') or ''
    if not description.splitlines() or description.splitlines()[-1]!=MARKER:description+=((chr(10)*2 if description else '')+MARKER)
    if len(description)>10000:raise ValueError('源应用说明过长，无法完整附加待验证标记；不截断原说明。')
    output['app']['description']=description
    validation=validate_agent(output,generated_root)
    if not validation['valid']:raise ValueError('目标映射仍有未适配条件：'+'；'.join(validation['errors']))
    content=yaml.safe_dump(output,allow_unicode=True,sort_keys=False)
    parse(content,'agent')
    target_context=digest({'environment':public,'connection_revision':target.get('connection_revision')})
    changes={'model':{'source':copy.deepcopy(soul['model']),'target':new_model},
        'datasets':labels,'dataset_id_mapping':[{'source_id':i,'target_id':mapping[i]} for i in sorted(ids)],'dependencies':{'source':deps,'target':copy.deepcopy(output.get('dependencies',[]))},
        'description':{'source':root['app'].get('description'),'target':description}}
    token=digest({'source_revision':task['revision'],'reference_id':source['reference_id'],'source_merge_token':source['merge_token'],
        'source_document_token':source['document_token'],'target_context_token':target_context,'target_document':digest(output),'configuration':cfg,'agent_plan':plan})
    return {'revision':task['revision'],'reference_id':source['reference_id'],'source_document_token':source['document_token'],
        'source_environment_id':task.get('environment_id'),'source_reference_kind':source.get('source'),'source_captured_at':source.get('captured_at'),
        'target_environment':public,'target_context_token':target_context,'preview_token':token,'document_token':digest(output),
        'content':content,'configuration':cfg,'agent_plan':plan,'changes':changes,'validation':validation,
        'verification':'static_mapping_preview','platform_verified':False,'business_verified':False,'target_resources_verified':False,
        'warnings':['源知识库的显示名／描述不会冒充目标标签，原值和清空变化已列出；知识集用途、分组与检索数量保持。',
            '目标资料覆盖、权限、模型／插件可用性、价格与延迟仍需核对；这次只准备待验证文件，不执行调用。',
            '固定插件依赖即使保留或明确替换，也没有证明目标已安装该版本；原模拟条件不会自动清除。'],
        'task_modified':False,'can_apply':False,'note':'这是基于Sierra当前已保存合并预览的待验证目标草稿，不证明源应用此刻最新、目标模型/资料/插件可用或资料语义等价；未请求Dify、复制凭据或更新任务。目标环境版本来自本机声明，未在线核对。原环境与历史保持，当前尚无直接采用映射的入口。'}


class MappingSaveRequest(MappingRequest):
    preview_token:str=Field(pattern=r'^[0-9a-f]{64}$')
    draft_revision:StrictInt=Field(ge=0)


DRAFT_KIND='environment_mapping_draft'
HISTORY_KIND='environment_mapping_draft_history'


class AgentEnvironmentMapping:
    def __init__(self,h):self.h=h

    def prepare(self,task,payload,*,require_idle=True):
        h=self.h
        if require_idle:h.require_idle(task)
        h.require_revision(task,payload.revision)
        if task['app_type']!='agent':raise HTTPException(422,'首批环境映射只适配原生Agent草稿；Workflow/Chatflow不转换后通过。')
        if payload.acknowledge_unverified_target is not True:raise HTTPException(422,'请明确知悉目标资源仍待验证；ID映射不证明资料等价，也不批准导入或运行。')
        source=h.dsl_preview(task,payload.choices)
        if source['reference_id']!=payload.reference_id or source['merge_token']!=payload.merge_token or source['document_token']!=payload.document_token:raise HTTPException(409,'来源或合并预览已变化，请重新分析后准备目标映射。')
        target=h.store.get('environment',payload.target_environment_id)
        if not target:raise HTTPException(404,'目标环境不存在，请先配置独立目标连接。')
        if target.get('id')!=payload.target_environment_id:raise HTTPException(422,'目标环境标识与保存记录不一致，请先修复连接记录。')
        if target.get('version')!=h.TARGET_DIFY_VERSION:raise HTTPException(422,'目标环境声明版本与当前适配基线不符，不能跨版本映射。')
        try:return build(task,source,target,payload.target_model_json,payload.dataset_mapping,payload.target_dependency)
        except ValueError as exc:raise HTTPException(422,str(exc)) from exc
        except (KeyError,TypeError,AttributeError,OverflowError):raise HTTPException(422,'映射结构无法完整核对，原任务及文件保持；不回显输入。') from None

    def counter(self,record,task_id=None):
        if record is None:return 0
        if not isinstance(record,dict) or type(record.get('draft_revision')) is not int or record['draft_revision']<1:
            raise HTTPException(409,'已存映射进度版本异常，请先核对原记录，不自动覆盖。')
        if task_id is not None and record.get('task_id')!=task_id:raise HTTPException(409,'已存映射进度归属异常，不读取或覆盖未知任务记录。')
        return record['draft_revision']

    def state(self,task,record=None):
        current=self.h.store.get(DRAFT_KIND,task['id']);current_revision=self.counter(current,task['id'])
        chosen=current if record is None else record
        if chosen is None:return {'record':None,'draft_revision':0,'stale':False,'blocker':None,'restorable':False,'restore_payload':None,'confirmed':False,'can_apply':False}
        if not isinstance(chosen,dict) or chosen.get('task_id')!=task['id']:raise HTTPException(409,'映射进度归属异常，不读取未知任务内容。')
        blocker=None;payload=None
        try:
            if chosen.get('task_id')!=task['id'] or chosen.get('verification')!='unconfirmed_local_mapping_draft':raise ValueError('映射进度归属或状态异常，不沿用旧确认。')
            payload=MappingRequest.model_validate(chosen['payload'])
            preview=self.prepare(task,payload,require_idle=False)
            if preview['preview_token']!=chosen.get('preview_token'):raise ValueError('来源或目标连接上下文已变化，旧映射只可参考；请重新预览。')
        except HTTPException as exc:blocker=str(exc.detail)
        except (ValidationError,KeyError,TypeError,AttributeError):blocker='已存映射进度结构不完整，仅保留原文供核对，不自动恢复或覆盖。'
        except ValueError as exc:blocker=str(exc)
        restore=payload.model_dump() if payload is not None and not blocker else None
        if restore is not None:restore['acknowledge_unverified_target']=False
        return {'record':copy.deepcopy(chosen),'draft_revision':current_revision,'stale':bool(blocker),'blocker':blocker,
            'restorable':restore is not None,'restore_payload':restore,'confirmed':False,'can_apply':False,
            'note':'这里只恢复未确认输入；旧勾选不沿用，后续预览和保存仍须任务空闲并重新核对。'}

    def register(self):
        h=self.h;router=APIRouter(route_class=MappingRoute)
        @router.post('/api/tasks/{item_id}/environment-mapping/preview')
        def preview(item_id:str,payload:MappingRequest):
            with h.store.lock:return self.prepare(h.get_task(item_id),payload)

        @router.get('/api/tasks/{item_id}/environment-mapping/draft')
        def read(item_id:str):
            with h.store.lock:return self.state(h.get_task(item_id))

        @router.put('/api/tasks/{item_id}/environment-mapping/draft')
        def save(item_id:str,payload:MappingSaveRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
                old=h.store.get(DRAFT_KIND,item_id);revision=self.counter(old,item_id)
                if revision!=payload.draft_revision:raise HTTPException(409,'映射草稿已被其他操作更新，请先读取核对，不覆盖已存进度。')
                prepared=self.prepare(task,payload)
                if prepared['preview_token']!=payload.preview_token:raise HTTPException(409,'本次完整映射预览已变化，请重新核对后保存；不采纳过期结果。')
                inputs=payload.model_dump(include=set(MappingRequest.model_fields))
                if old and old.get('preview_token')==payload.preview_token and digest(old.get('payload'))==digest(inputs):return self.state(task)
                stamp=h.now()
                record={'id':item_id,'task_id':item_id,'draft_revision':revision+1,'source_revision':task['revision'],
                    'reference_id':payload.reference_id,'preview_token':payload.preview_token,'payload':inputs,'preview':prepared,
                    'created_at':stamp,'verification':'unconfirmed_local_mapping_draft'}
                rows=[]
                if old:
                    key=item_id+':'+str(revision);existing=h.store.get(HISTORY_KIND,key)
                    if existing is not None and digest(existing)!=digest(old):raise HTTPException(409,'旧映射历史记录冲突，请先核对，不覆盖历史。')
                    if existing is None:rows.append((HISTORY_KIND,key,copy.deepcopy(old)))
                rows.append((DRAFT_KIND,item_id,record));h.store.put_many(rows)
                return self.state(task)

        @router.get('/api/tasks/{item_id}/environment-mapping/draft/history/{draft_revision}')
        def history(item_id:str,draft_revision:int=ApiPath(gt=0)):
            with h.store.lock:
                task=h.get_task(item_id);record=h.store.get(HISTORY_KIND,item_id+':'+str(draft_revision))
                if not isinstance(record,dict) or record.get('task_id')!=item_id or record.get('draft_revision')!=draft_revision:raise HTTPException(404,'没有属于当前任务的该映射历史版本。')
                result=self.state(task,record);result['historical']=True
                return result
        h.app.include_router(router)
