"""Explicit per-topic operator review of already supplied user text; no model call."""
import copy,re
from typing import Literal
from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,ConfigDict,StrictStr,StrictBool,Field
from .saved_intake import CandidateRoute,Revision,fingerprint
from .plan_drafts import inspect_text
from .intake import BASE,topics,summary,validate_review,ReviewContractError,digest
from .discussion_mode import requirement_user

class ResolutionRoute(CandidateRoute):
    body_limit=200000
    label='需求逐项补充'

class Evidence(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message_id:StrictStr=Field(min_length=1,max_length=10)
    quote:StrictStr=Field(min_length=1,max_length=3000)

class Answer(Revision):
    topic:StrictStr=Field(min_length=1,max_length=64)
    answer:StrictStr=Field(min_length=1,max_length=3000)
    evidence:list[Evidence]=Field(min_length=1,max_length=6)
    actor:Literal['local_operator','agent_delegated']='local_operator'
    actor_note:StrictStr=Field(default='',max_length=1000)

class Save(Answer):
    review_token:StrictStr=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledge_source_review:StrictBool

def user_sources(task):
    rows=[];omitted=0;size=0
    for i,m in reversed(list(enumerate(task.get('messages',[])))):
        if not requirement_user(m):continue
        text=m.get('content')
        if not isinstance(text,str) or not text.strip() or len(text)>16000 or size+len(text)>64000 or len(rows)>=20:
            omitted+=1;continue
        try:inspect_text(text)
        except HTTPException:omitted+=1;continue
        rows.append({'id':str(i),'text':text});size+=len(text)
    return rows,omitted

class IntakeTopicResolution:
    def __init__(self,host):self.h=host

    def current(self,task):
        if any(task.get(k) for k in ('materials','workflow_plan','agent_plan','artifact','dify_app_id','dsl_reference','dsl_overlay','runs')):
            raise HTTPException(422,'此入口只补充初始需求的专项问题；材料或已有交付请使用正常复核/修改流程。')
        if task.get('status') not in {'requirements','error'}:raise HTTPException(409,'当前任务不在可补充的初始需求阶段。')
        state=summary(task)
        if not state['reviewed'] or state['stale']:raise HTTPException(409,'当前需求检查缺失或已过期，不能基于旧问题补充。')
        try:validate_review(task,task['intake_review']['review'])
        except ReviewContractError as exc:raise HTTPException(422,'当前逐项检查仍无效：'+str(exc)) from None
        return state

    def prepare(self,task,payload):
        self.current(task)
        if payload.topic in BASE:raise HTTPException(422,'基础说明缺口请编辑对应需求字段，不在此入口只改检查结论。')
        review=copy.deepcopy(task['intake_review']['review']);selected=[r for r in review['checks'] if r['topic']==payload.topic and r['status']=='needs_input']
        if len(selected)!=1:raise HTTPException(409,'该专项不是当前待答项，未重复补充或改写其它检查。')
        answer=payload.answer.strip();note=payload.actor_note.strip()
        if not answer or (payload.actor=='agent_delegated' and not note):raise HTTPException(422,'请填写明确补充；代理操作还须说明依据与非人类签收来源。')
        inspect_text(answer);inspect_text(note or '操作者本地补充')
        scenario=copy.deepcopy(task);scenario['requirements']['rules']+='\n'+answer
        if {r['id'] for r in topics(scenario)}!={r['id'] for r in topics(task)}:
            raise HTTPException(422,'补充引入新的专项场景，请先编辑需求并重新检查，不能只关闭原问题。')
        available,_=user_sources(task);sources={r['id']:r['text'] for r in available};seen=set();refs=[]
        for e in payload.evidence:
            if not re.fullmatch(r'0|[1-9][0-9]{0,9}',e.message_id) or e.message_id not in sources or not e.quote.strip() or e.quote not in sources[e.message_id]:
                raise HTTPException(422,'引用须逐字来自当前提供的原始用户说明，不能用模型建议、讨论或不存在的文字代替。')
            key=(e.message_id,e.quote)
            if key in seen:raise HTTPException(422,'来源引用重复，请明确保留一项，不静默合并。')
            seen.add(key);refs.append({'kind':'message','id':e.message_id,'quote':e.quote})
        selected[0].update(status='complete',detail=answer,evidence=refs)
        review['questions']=[q for q in review['questions'] if q['topic']!=payload.topic]
        remaining={r['topic'] for r in review['checks'] if r['status']=='needs_input'}
        if remaining and not review['questions']:
            review['questions']=[{'topic':r['id'],'question':r['question'],'recommendation':'请按实际用户说明补充，未明确时保留待答。','reason':'其它缺口未解决，不能因本项补充而默认通过。','experience':'补充后按当前修订继续复核。','cost':'本次仅本地编辑，不调用模型或外部服务。','manual_work':'操作者仍须逐项说明依据。'} for r in topics(task) if r['id'] in remaining][:3]
        try:validate_review(task,review)
        except ReviewContractError as exc:raise HTTPException(422,'补充后检查未通过：'+str(exc)) from None
        operation={'topic':payload.topic,'answer':answer,'evidence':refs,'actor':payload.actor,'actor_note':note}
        token=fingerprint({'task':task,'operation':operation,'review':review})
        return {'task_id':task['id'],'revision':task['revision'],'app_type':task['app_type'],'operation':operation,'review':review,'remaining_topics':sorted(remaining),'review_token':token,
                'requirements_changed':False,'requirements_confirmed':False,'configuration_confirmed':False,'network_requested':False,'model_called':False,'task_changed':False,'business_verified':False,
                'note':'只核对引用确实存在，回答与依据的语义关系由操作者显式负责，不是模型验证或人类签收。保存仅更新选定专项及其问题，新修订仍未确认；其它检查/需求/失败/费用保留。'}

    def register(self):
        h=self.h;router=APIRouter(route_class=ResolutionRoute)
        @router.post('/api/tasks/{item_id}/intake/topic-resolution/options')
        def options(item_id:str,payload:Revision):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task);state=self.current(task)
                pending={r['topic'] for r in task['intake_review']['review']['checks'] if r['status']=='needs_input' and r['topic'] not in BASE}
                source_rows,omitted=user_sources(task)
                return {'task_id':item_id,'revision':task['revision'],'topics':[{'id':r['id'],'label':r['label'],'question':next((q['question'] for q in state['questions'] if q['topic']==r['id']),r['question'])} for r in state['standard'] if r['id'] in pending],
                        'sources':source_rows,'omitted_sources':omitted,'network_requested':False,'task_changed':False}
        @router.post('/api/tasks/{item_id}/intake/topic-resolution/preview')
        def preview(item_id:str,payload:Answer):
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task)
                return self.prepare(task,payload)
        @router.post('/api/tasks/{item_id}/intake/topic-resolution/save')
        def save(item_id:str,payload:Save):
            if not payload.acknowledge_source_review:raise HTTPException(422,'请明确承担补充与引用的语义复核，不把它当自动验证或人类签收。')
            with h.store.lock:
                task=h.get_task(item_id);h.require_revision(task,payload.revision);h.require_idle(task);proposal=self.prepare(task,payload)
                if proposal['review_token']!=payload.review_token:raise HTTPException(409,'说明、来源或补充内容已改变，请重新预览，不覆盖旧结果。')
                prior=copy.deepcopy(task['intake_review']);h.invalidate(task,'按原用户说明逐项补充前保存')
                h.intake.save(task,proposal['review'],'source_backed_resolution')
                record=task['intake_review'];record['answers']={**prior.get('answers',{}),payload.topic:proposal['operation']['answer']}
                record['topic_resolutions']=copy.deepcopy(prior.get('topic_resolutions',[]))+[{**proposal['operation'],'source_revision':payload.revision,'draft_revision':task['revision'],'created_at':h.now()}]
                record['resolution_actor']=payload.actor;record['context_digest']=digest(task)
                task['messages'].append({'role':'assistant','source':'system','content':'已按原始用户说明显式补充一个待答专项；其他需求和检查保留，新修订仍未确认。来源为'+('代理委托复核，非人类业务签收。' if payload.actor=='agent_delegated' else '本地操作者声明，非模型验证或人类签收。')+' 未请求外部服务或改变旧失败/费用。','created_at':h.now()})
                return h.save_task(task)
        h.app.include_router(router)
