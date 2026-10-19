"""Bounded selected-library metadata diagnostics; never retrieves or indexes text."""
import copy,hashlib,json,uuid
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictInt,field_validator
from .agent_environment_mapping import MappingRoute
from .resources import datasets_metadata

LABELS={'counts_consistent':'已知目录计数一致，检索仍未验证','not_listed':'目录中未提供该ID','outside_window':'超出本次核对窗口，尚未明确','empty':'未提供文档','not_indexed':'尚无可用文档索引','partial':'仅部分文档索引可用','unknown_metadata':'目录字段不足或不一致','embedding_unresolved':'Embedding标识尚未明确'}


def guidance(status):
    if status=='counts_consistent':return []
    if status=='empty':
        first={'option':'补齐资料后核对索引','experience':'资料覆盖尚不能验收，补齐后仍须验证代表性问题。','cost':'上传或重新索引可能发生Embedding与存储费用，须另行确认资源方案。','manual_work':'准备资料并核对目标库权限、索引方式与处理结果。'}
    elif status in {'not_indexed','partial'}:
        first={'option':'检查并处理未就绪文档','experience':'不把未索引部分当已覆盖，也不默认缩小问答范围。','cost':'修复或重建索引可能调用Embedding；先核对费用及具体资源方案。','manual_work':'在Dify检查队列与失败原因，处理后重新核对索引和代表性问题。'}
    elif status=='embedding_unresolved':
        first={'option':'核对Dify中的Embedding配置','experience':'明确供应商及型号后仍须核对当前可用性；助手Key不代表Dify已配置。','cost':'模型配置及重新索引的费用尚未评估，不假定免费。','manual_work':'由用户核对Dify模型服务、插件与该库关联，资源修改另行确认。'}
    elif status=='outside_window':
        first={'option':'人工查看后续目录与目标ID','experience':'本次最多3页，窗口外未找到不证明不存在，不自动换库。','cost':'目录核对不调用模型；后续索引与检索费用仍需另行核对。','manual_work':'在目录面板手动翻页或到Dify核对指定ID、工作空间与可见性。'}
    else:
        first={'option':'补齐目录依据与权限信息','experience':'保留当前映射，不将缺字段、不可见或计数矛盾当作库已删除。','cost':'当前步骤仅核对目录，不包含后续索引、检索或问答费用。','manual_work':'核对目标工作空间和连接权限；如要换认证来源，由用户明确选择，不自动扩大权限。'}
    return [first,{'option':'明确选择另一个目标库','experience':'需重新核对资料覆盖和预期答案，不能按同名或ID相似推断等价。','cost':'可避免直接重建资料，但后续检索与模型费用仍待确认。','manual_work':'由用户明确新ID并核对对应关系；不会自动替换或少选一个库。'},
            {'option':'保留为待验证草稿','experience':'可继续准备DSL，但不能算知识问答或客户业务已经交付。','cost':'这一步不触发模型调用；后续执行成本仍需核对。','manual_work':'交付前补齐上述条件并完成实际检索及关键样例验收。'}]


class DatasetRoute(MappingRoute):
    field_error='知识库配置核对字段无效，请明确知识库ID、目录连接方式及连接修订；不回显输入，不运行检索。'
    def transport_error(self,exc):return str(exc).replace('试跑请求','知识库配置核对请求').replace('派发','读取目录')


class DatasetRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    dataset_ids:list[str]=Field(min_length=1,max_length=100)
    source:Literal['console','service']='console'
    max_pages:StrictInt=Field(default=3,ge=1,le=3)
    expected_connection_revision:str|None=Field(default=None,max_length=100)

    @field_validator('dataset_ids')
    @classmethod
    def explicit_ids(cls,values):
        if len(set(values))!=len(values):raise ValueError('知识库ID重复，不能自动去重后核对。')
        for value in values:
            try:valid=str(uuid.UUID(value))==value
            except (ValueError,TypeError,AttributeError):valid=False
            if not valid:raise ValueError('须明确小写连字符UUID，不接受库名或占位词。')
        return values


def selection_token(payload):
    return hashlib.sha256(json.dumps({'dataset_ids':payload.dataset_ids,'source':payload.source,'max_pages':payload.max_pages},ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def describe(ident,row,*,complete):
    if row is None:
        status='not_listed' if complete else 'outside_window'
        return {'id':ident,'status':status,'status_label':LABELS[status],'metadata':{},'unavailable_fields':[],
                'issues':['当前可访问目录没有提供此ID；可能不存在或不可见，不推断已删除。' if complete else '仅核对本次有限目录窗口，不能把未找到当作不存在。'],
                'counts_consistent':False,'retrieval_tested':False,'guidance':guidance(status)}
    metadata={k:row[k] for k in ('name','indexing_technique','embedding_model','embedding_model_provider') if isinstance(row.get(k),str)}
    unavailable=[];issues=[]
    for key in ('document_count','available_document_count'):
        value=row.get(key)
        if type(value) is int and 0<=value<=9007199254740991:metadata[key]=value
        else:unavailable.append(key)
    count=metadata.get('document_count');available=metadata.get('available_document_count')
    counts_consistent=count is not None and count>0 and available==count
    if unavailable:
        status='unknown_metadata';issues.append('目录未提供可精确核对的非负整数文档计数，不猜测零或索引就绪。')
    elif available>count:
        status='unknown_metadata';issues.append('可用文档数大于总文档数，目录计数不一致。')
    elif count==0:
        status='empty';issues.append('目录声明没有文档，不能据此交付有资料覆盖的知识问答。')
    elif available==0:
        status='not_indexed';issues.append('已有文档但目录声明没有可用文档索引；需核对索引状态和失败原因。')
    elif available<count:
        status='partial';issues.append('只有部分文档可用，未就绪资料不能算已覆盖。')
    else:status='counts_consistent'
    technique=metadata.get('indexing_technique')
    if technique not in {'economy','high_quality'}:
        unavailable.append('indexing_technique');issues.append('索引方式未明确或尚未适配，不推断外部知识库的就绪状态。')
        if status=='counts_consistent':status='unknown_metadata'
    elif technique=='high_quality':
        missing=[k for k in ('embedding_model','embedding_model_provider') if not metadata.get(k)]
        if missing:
            unavailable+=missing;issues.append('高质量索引未明确Embedding型号或供应商；不推断当前可用或补默认模型。')
            if status=='counts_consistent':status='embedding_unresolved'
    return {'id':ident,'status':status,'status_label':LABELS[status],'metadata':metadata,'unavailable_fields':unavailable,
            'issues':issues,'counts_consistent':counts_consistent,'retrieval_tested':False,'guidance':guidance(status)}


class DatasetConfigurationCheck:
    def __init__(self,h):self.h=h

    def register(self):
        h=self.h;router=APIRouter(route_class=DatasetRoute)
        @router.post('/api/environments/{item_id}/dataset-configuration-check')
        async def check(item_id:str,payload:DatasetRequest):
            with h.store.lock:
                env=copy.deepcopy(h.resource_environment(item_id))
                if env.get('connection_revision')!=payload.expected_connection_revision:raise HTTPException(409,'目标连接修订已变化，请刷新环境后重新核对知识库。')
            found={};seen=set();records=0;has_more=False;pages=0
            try:
                adapter=h.DifyClient(env,h.store)
                for page in range(1,payload.max_pages+1):
                    raw=await (adapter.console_datasets(page,100) if payload.source=='console' else adapter.datasets(page,100))
                    data=datasets_metadata(raw)
                    if len(data['data'])>100:raise HTTPException(502,'目标目录单页超出声明上限，未截断后算完整。')
                    with h.store.lock:h.require_resource_connection(env)
                    pages=page;records+=len(data['data']);ids={r['id'] for r in data['data']};fresh=ids-seen;seen|=ids
                    for row in data['data']:
                        ident=row['id']
                        if ident not in payload.dataset_ids:continue
                        if ident in found and found[ident]!=row:raise HTTPException(409,'翻页期间相同知识库ID的目录信息冲突，请重新读取；不混合旧新状态。')
                        found[ident]=row
                    has_more=data['has_more']
                    if len(found)==len(payload.dataset_ids) or not has_more:break
                    if not fresh:raise HTTPException(502,'目录翻页没有新增ID，已停止；未将其当作指定知识库缺失，也不自动重试。')
            except h.DifyError as exc:
                message='目标目录读取超时，未执行检索、索引或写资源；请核对后主动重读。' if 'Dify 请求超时' in str(exc) else str(exc)
                if payload.source=='service' and getattr(exc,'http_status',None)==403:message='知识库Key无权列举当前目录；可明确切换管理连接或保留已知ID待核对，不自动扩大权限或换凭据。'
                raise HTTPException(502,message) from exc
            except OverflowError:raise HTTPException(502,'目标目录计数数值异常，未舍入或采用部分结果。') from None
            with h.store.lock:h.require_resource_connection(env)
            rows=[describe(ident,found.get(ident),complete=not has_more) for ident in payload.dataset_ids]
            known=all(row['status']=='counts_consistent' for row in rows)
            return {'status':'known_metadata_consistent' if known else 'needs_review','status_label':'指定库已知目录条件一致，资源仍未验证' if known else '指定知识库仍有待核对条件',
                    'environment_id':item_id,'connection_revision':env.get('connection_revision'),'selection_token':selection_token(payload),
                    'observed_at':h.now(),'source':payload.source,'pages_read':pages,'records_read':records,'catalog_complete':not has_more,
                    'search_complete_for_selected':len(found)==len(payload.dataset_ids) or not has_more,'rows':rows,
                    'warnings':['仅观察读取时目录元数据，不是跨页事务快照；名称或ID相同不证明源与目标资料等价。',
                                '未读取文档全文、运行检索或调用模型；Embedding当前可用性、查询费用、权限和业务覆盖仍须核对。',
                                '经济索引不要求Embedding标识；高质量索引有型号标识也不证明供应商或插件仍可调用。'],
                    'note':f'最多核对{payload.max_pages}页、每页100条，只返回明确指定的ID；不会删库、换库或补默认索引。计数一致不等于代表性问题检索或客户业务通过。',
                    'verification':'dataset_directory_metadata_only','retrieval_tested':False,'model_calls':0,'task_modified':False,
                    'target_resources_verified':False,'platform_verified':False,'business_verified':False}
        h.app.include_router(router)
