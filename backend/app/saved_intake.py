"""Explicit local recovery of complete rejected initial intake drafts, no model call."""
import copy,hashlib,json
from datetime import datetime
from fastapi import APIRouter,HTTPException
from fastapi.routing import APIRoute
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel,ConfigDict,StrictInt,StrictBool,StrictStr,Field
from .run_input_transport import validate,AmbiguousInput
from .plan_drafts import inspect_text
from .intake import validate_review,ReviewContractError


class CandidateRoute(APIRoute):
    body_limit=4096
    label='访谈候选'
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:
                raw=await request.body()
                if len(raw)>self.body_limit:raise AmbiguousInput()
                validate(raw)
                response=await original(request)
            except (AmbiguousInput,RequestValidationError):
                response=JSONResponse(status_code=422,content={'detail':self.label+'请求须为明确的有限JSON对象及合法修订/来源标记；未处理，不回显输入。'})
            response.headers['Cache-Control']='no-store'
            return response
        return guarded

class Revision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt=Field(ge=1)

class Adopt(Revision):
    review_token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_unconfirmed:StrictBool

def stamp(value):
    try:
        result=datetime.fromisoformat(value.replace('Z','+00:00'))
        if result.tzinfo is None:raise ValueError()
        return result
    except (ValueError,TypeError,AttributeError):
        raise HTTPException(422,'候选或来源时间无法核对，不能恢复；请使用正常需求编辑与复核。') from None

def fingerprint(value):
    try:
        raw=json.dumps(value,ensure_ascii=True,sort_keys=True,allow_nan=False,separators=(',',':')).encode()
        if len(raw)>8_000_000:raise ValueError()
        return hashlib.sha256(raw).hexdigest()
    except (ValueError,TypeError,RecursionError,OverflowError):
        raise HTTPException(422,'候选来源超过8MB或不是有限JSON，不能核对；未恢复。') from None

def parse_reply(text):
    if not isinstance(text,str) or len(text)>16000:raise HTTPException(422,'仅支持完整保存且不超过16000字的失败候选。')
    inspect_text(text)
    def unique(pairs):
        out={}
        for k,v in pairs:
            if k in out:raise ValueError()
            out[k]=v
        return out
    try:
        raw=text.strip()
        if raw.startswith('```json') and raw.endswith('```'):raw=raw[7:-3].strip()
        elif raw.startswith('```') and raw.endswith('```'):raw=raw[3:-3].strip()
        value=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if not isinstance(value,dict) or set(value)!={'message','requirements_patch','intake_review'}:raise ValueError()
        if not isinstance(value['message'],str) or not value['message'].strip():raise ValueError()
        return value
    except (ValueError,TypeError,RecursionError):
        raise HTTPException(422,'保存候选不是完整且无歧义的需求检查契约，不能修补或自动恢复。') from None

class SavedIntake:
    def __init__(self,host):self.h=host

    def prepare(self,task,index):
        h=self.h
        if task.get('materials') or any(task.get(k) for k in ('workflow_plan','agent_plan','artifact','dify_app_id','dsl_reference','dsl_overlay','runs')):
            raise HTTPException(422,'仅支持无材料、正式计划、成果、App或运行的初始需求草稿；已有交付请用正常修改流程。')
        if task.get('status') not in {'requirements','error'}:
            raise HTTPException(409,'当前不是空闲的初始需求草稿，不能恢复失败候选。')
        attempts=task.get('interview_attempts',[])
        if not isinstance(attempts,list) or not 0<=index<len(attempts):raise HTTPException(404,'保存的访谈候选不存在。')
        attempt=attempts[index]
        if not isinstance(attempt,dict) or attempt.get('applied') is not False or attempt.get('response_truncated') is not False or not str(attempt.get('reason','')).startswith('模型需求检查未通过：'):
            raise HTTPException(422,'仅支持已完整返回、因需求契约拒绝而未应用的候选；讨论、暂停、中断或截断记录不恢复。')
        if type(attempt.get('revision')) is not int or attempt['revision']!=task['revision']:
            raise HTTPException(409,'候选属于旧修订，不能覆盖当前需求；请按当前说明正常复核。')
        cutoff=stamp(attempt.get('created_at'));users=[]
        messages=task.get('messages',[])
        if not isinstance(messages,list) or any(not isinstance(m,dict) for m in messages):raise HTTPException(422,'来源消息格式无法核对，不能恢复。')
        for message in messages:
            if message.get('role')=='user':
                if stamp(message.get('created_at'))>cutoff:raise HTTPException(409,'候选之后已有新的用户说明，不能用旧候选覆盖；请继续正常需求复核。')
                users.append(message)
        if not users or users[-1].get('purpose') not in {None,'review'}:
            raise HTTPException(422,'候选来源不是需求检查，不能把只读讨论改作需求。')
        value=parse_reply(attempt.get('response_excerpt'));patch=value['requirements_patch']
        if not isinstance(patch,dict) or set(patch)-set(h.REQ_KEYS) or any(not isinstance(v,str) or len(v)>16000 for v in patch.values()):
            raise HTTPException(422,'保存候选的需求字段无效，不能恢复。')
        proposed=copy.deepcopy(task)
        proposed['requirements'].update({k:v.strip() for k,v in patch.items() if v.strip()})
        try:review=validate_review(proposed,value['intake_review'],evidence_task=task)
        except ReviewContractError as exc:raise HTTPException(422,'保存候选按当前规则仍未通过：'+str(exc)) from None
        # Inspect the combined result too, including unchanged existing fields.
        inspect_text(json.dumps({'requirements':proposed['requirements'],'review':review,'message':value['message']},ensure_ascii=False))
        candidate_sha=fingerprint(attempt);token=fingerprint({'task':task,'attempt_index':index,'candidate_sha256':candidate_sha,'requirements':proposed['requirements'],'review':review})
        return {'task_id':task['id'],'revision':task['revision'],'app_type':task['app_type'],'attempt_index':index,'candidate_sha256':candidate_sha,'review_token':token,
                'requirements':proposed['requirements'],'review':review,'message':value['message'],
                'needs_input_topics':[r['topic'] for r in review['checks'] if r['status']=='needs_input'],
                'network_requested':False,'model_called':False,'task_changed':False,'requirements_confirmed':False,'business_verified':False,
                'note':'仅本地重新核对保存候选。主动恢复会生成新未确认修订；原失败、候选和费用不改判、不重发。追问仍需处理，不恢复旧真实批或替代资源批准。'}

    def register(self):
        h=self.h;router=APIRouter(route_class=CandidateRoute)
        @router.post('/api/tasks/{item_id}/saved-intake-candidates/list')
        def listing(item_id:str,payload:Revision):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision)
                attempts=task.get('interview_attempts',[])
                if not isinstance(attempts,list):raise HTTPException(422,'保存候选列表无效。')
                return {'task_id':item_id,'revision':payload.revision,'candidates':[{'index':i,'complete':a.get('response_truncated') is False,'same_revision':a.get('revision')==payload.revision} for i,a in reversed(list(enumerate(attempts))[-20:]) if isinstance(a,dict) and a.get('applied') is False],
                        'network_requested':False,'task_changed':False}
        @router.post('/api/tasks/{item_id}/saved-intake-candidates/{index}/preview')
        def preview(item_id:str,index:int,payload:Revision):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task)
                return self.prepare(task,index)
        @router.post('/api/tasks/{item_id}/saved-intake-candidates/{index}/adopt')
        def adopt(item_id:str,index:int,payload:Adopt):
            if not payload.acknowledge_unconfirmed:raise HTTPException(422,'请明确确认只恢复未确认草稿，原失败和费用保持，不派发外部请求。')
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task)
                proposal=self.prepare(task,index)
                if proposal['review_token']!=payload.review_token:raise HTTPException(409,'候选或当前说明已改变，请重新预览；未采用旧结果。')
                h.invalidate(task,'主动恢复保存的访谈候选前保存')
                task['requirements']=copy.deepcopy(proposal['requirements'])
                h.intake.save(task,copy.deepcopy(proposal['review']),'saved_model_candidate')
                task['intake_review']['saved_candidate']={'attempt_index':index,'source_revision':payload.revision,'candidate_sha256':proposal['candidate_sha256']}
                task.setdefault('saved_intake_adoptions',[]).append({'attempt_index':index,'candidate_sha256':proposal['candidate_sha256'],'source_revision':payload.revision,'draft_revision':task['revision'],'created_at':h.now()})
                task['messages'].append({'role':'assistant','source':'system','content':'已主动恢复保存的访谈候选为新未确认草稿；原失败、候选和费用保持，未重新调用模型。请处理原追问并按当前修订确认需求和配置，不续跑旧真实批。','created_at':h.now()})
                return h.save_task(task)
        h.app.include_router(router)
