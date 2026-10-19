"""Explicit local-only scalar input check; no defaults copied or platform calls."""
import hashlib,json
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictInt
from .run_input_transport import RunInputRoute
from .start_inputs import check_values


class Check(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)
    source_sha256:str=Field(pattern=r'^[0-9a-f]{64}$')
    input:dict


class RunInputCheck:
    def __init__(self,host):self.h=host
    def register(self):
        h=self.h;router=APIRouter(route_class=RunInputRoute)
        @router.post('/api/tasks/{item_id}/run-input-check')
        def check(item_id:str,payload:Check):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision);schema=h.read_run_input_schema(item_id)
                if schema['source_sha256']!=payload.source_sha256:raise HTTPException(409,'最终成果入口已改变，请只读刷新入口后核对本次输入。')
                try:
                    text=json.dumps(payload.input,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode('utf-8')
                    if len(text)>2000000:raise ValueError('本机检查最多2MB输入，不截断。')
                    check_values(schema['fields'],payload.input)
                    if schema.get('app_mode')=='advanced-chat' and not payload.input['query'].strip():
                        raise ValueError('Chatflow 试跑需要非空 query 文本。')
                except (ValueError,TypeError,RecursionError) as exc:raise HTTPException(422,'本次输入未通过本机检查：'+('输入结构或编码无效，不显示原文。' if isinstance(exc,(TypeError,RecursionError,UnicodeError)) else str(exc))) from None
                latest=h.read_run_input_schema(item_id)
                if latest['source_sha256']!=schema['source_sha256']:raise HTTPException(409,'检查期间成果入口改变，未将旧检查当作当前结果。')
                return {'task_id':item_id,'revision':payload.revision,'source_sha256':schema['source_sha256'],'input_sha256':hashlib.sha256(text).hexdigest(),'valid':True,'verification':'local_input_shape_only','platform_checked':False,'business_verified':False,'defaults_copied':False,'checked_at':h.now(),'note':'仅核对最终成果的必填、类型、选项、长度与声明字段，不改原输入／填默认、不请求Dify或模型。不是已发布入口一致、可运行、业务通过或后续输入的永久许可；修改输入／入口后须重新检查。'}
        h.app.include_router(router)
