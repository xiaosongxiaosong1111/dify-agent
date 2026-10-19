"""One approved image call and explicitly reviewed adoption; never automatic retry."""
import copy,json,re,uuid
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictStr,StrictBool,Field
from .image_preview import model_messages,OUTPUT_LIMIT
from .material_sources import read_source
from .planning import PlanningStopped
from .providers import ProviderError


class ExecuteRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    plan_id:StrictStr
    preview_token:StrictStr
    acknowledge_outbound:StrictBool
    acknowledge_estimated_fee:StrictBool
    acknowledge_unverified_vision:StrictBool
    acknowledge_image_token_pricing:StrictBool


class AdoptRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt
    plan_id:StrictStr
    candidate_token:StrictStr
    text:StrictStr=Field(min_length=1,max_length=100000)
    coverage_note:StrictStr=Field(min_length=1,max_length=2000)
    acknowledge_review:StrictBool
    acknowledge_uncertainties:StrictBool


def candidate(text):
    if not isinstance(text,str) or len(text)>120000:raise ValueError('图像候选正文超出范围，未采用或截断。')
    value=text.strip()
    if value.startswith('```'):
        lines=value.splitlines()
        if lines[0] not in {'```','```json'} or lines[-1]!='```':raise ValueError('图像候选JSON包装不完整。')
        value='\n'.join(lines[1:-1])
    def unique(pairs):
        result={}
        for key,item in pairs:
            if key in result:raise ValueError('图像候选JSON字段重复，不用最后值覆盖原说法。')
            result[key]=item
        return result
    try:result=json.loads(value,object_pairs_hook=unique)
    except json.JSONDecodeError:raise ValueError('图像模型返回格式未满足约定，未自动修复或再次调用。') from None
    if not isinstance(result,dict) or set(result)!={'transcription','diagram_description','coverage_note','uncertainties'}:raise ValueError('图像候选字段不完整或包含未适配内容。')
    if any(not isinstance(result[k],str) or len(result[k])>100000 for k in ('transcription','diagram_description')):raise ValueError('图像文字／关系说明格式无效。')
    if not isinstance(result['coverage_note'],str) or not 0<len(result['coverage_note'].strip())<=2000:raise ValueError('图像候选缺少实际覆盖／缺失说明。')
    if not isinstance(result['uncertainties'],list) or len(result['uncertainties'])>20 or any(not isinstance(v,str) or not 0<len(v.strip())<=2000 for v in result['uncertainties']):raise ValueError('图像不确定点结构无效。')
    if re.search(r'\bsk-[A-Za-z0-9_-]{16,}|(?i:Bearer\s+[A-Za-z0-9_.-]{16,})',value):raise ValueError('图像返回内容含疑似凭据，未保存正文；请先处理敏感信息或提供文字替代。')
    try:value.encode('utf-8')
    except UnicodeError:raise ValueError('图像候选包含不可保存的文字编码。') from None
    return result


class ImageExecution:
    def __init__(self,host,previews):self.h=host;self.previews=previews

    def record(self,item_id,material_id,plan_id):
        record=self.h.store.get('image_preview',plan_id)
        if not record or record['task_id']!=item_id or record['material_id']!=material_id:raise HTTPException(404,'图像预览不属于当前任务／材料。')
        return record

    def recover(self):
        h=self.h
        with h.store.lock:
            for record in h.store.list('image_preview'):
                if record.get('status')!='dispatched':continue
                record.update(status='interrupted',error='服务重启时图像调用结果未确认，保留费用预留，不自动重发。')
                task=h.get_task(record['task_id'])
                if task.get('active_image_operation_id')==record['id']:
                    task.pop('active_image_operation_id',None);task['status']='paused'
                h.store.put_many([('image_preview',record['id'],record),('task',task['id'],task)])

    def register(self):
        h=self.h;previews=self.previews;previews.executions_enabled=True
        @h.app.post('/api/tasks/{item_id}/materials/{material_id}/image-interpretation/execute')
        async def execute(item_id:str,material_id:str,payload:ExecuteRequest):
            if not all((payload.acknowledge_outbound,payload.acknowledge_estimated_fee,payload.acknowledge_unverified_vision,payload.acknowledge_image_token_pricing)):
                raise HTTPException(422,'须明确图像数据出站、费用预留估算、识图能力尚未验证，以及实际服务图像用量适用已登记token计价；未确认不派发。')
            with h.store.lock:
                task,material=previews.owned(item_id,material_id);h.require_idle(task);h.require_revision(task,payload.revision)
                record=self.record(item_id,material_id,payload.plan_id)
                if record['preview_token']!=payload.preview_token:raise HTTPException(409,'图像预览确认标识不匹配，未派发。')
                blocker=previews.blocker(task,material,record)
                if blocker:raise HTTPException(409,blocker)
                if h.budgets.state(h.budgets.get(item_id))['unknown_count']:raise HTTPException(422,'有未核对的模型费用，先核对账本，不继续图像派发。')
                h.budgets.ready(item_id)
                provider,key=previews.provider(record['provider']['id']);raw=read_source(h,item_id,material)
                messages=model_messages(raw,record['instruction']);previous=task['status']
                record.update(status='dispatched',started_at=h.now(),acknowledgements={'outbound':True,'estimated_fee':True,'unverified_vision':True,'image_token_pricing_user_declared':True})
                task['status']='planning';task['active_image_operation_id']=record['id']
                h.store.put_many([('image_preview',record['id'],record),('task',item_id,task)])
            failure=None
            try:
                text,usage=await h.budgets.call(item_id,payload.revision,'material-image',provider,key,messages,operation_id=record['id'],max_tokens=record['output_limit'],timeout=record['timeout_seconds'],json_mode=provider.get('protocol')!='anthropic',allow_images=True,image_reserve_usd=record['image_reserve_usd'])
                if key in text:raise ValueError('图像返回内容包含模型凭据，未保存正文，请核对来源。')
                record.update(candidate=candidate(text),candidate_token=uuid.uuid4().hex,usage=usage,status='candidate_ready',completed_at=h.now())
                state=h.budgets.state(h.budgets.get(item_id))
                if state['unknown_count'] or state['blocker']:
                    record.update(status='paused_candidate',error='图像候选已保留，调用费用或预算需核对；未自动采用或重发。')
            except (ValueError,ProviderError,PlanningStopped,HTTPException) as exc:
                failure=exc;record.update(status='failed',error=str(exc.detail) if isinstance(exc,HTTPException) else str(exc),completed_at=h.now())
            except BaseException:
                record.update(status='interrupted',error='图像请求中断，结果或费用可能未知，未自动重发。',completed_at=h.now())
                with h.store.lock:
                    current=h.get_task(item_id)
                    if current.get('active_image_operation_id')==record['id']:current.pop('active_image_operation_id',None);current['status']='paused'
                    h.store.put_many([('image_preview',record['id'],record),('task',item_id,current)])
                raise
            with h.store.lock:
                current=h.get_task(item_id);owned=current.get('active_image_operation_id')==record['id']
                if owned:current.pop('active_image_operation_id',None)
                stopped=current['status']=='paused' or current['revision']!=payload.revision or not owned
                if stopped and record.get('candidate'):record.update(status='paused_candidate',error='任务暂停或修订变化，迟到候选仅供核对，未自动采用。')
                if owned:current['status']='paused' if stopped or record['status'] in {'failed','paused_candidate'} else previous
                h.store.put_many([('image_preview',record['id'],record),('task',item_id,current)])
                result=previews.public(current,next(m for m in current['materials'] if m['id']==material_id),record)
            if failure:raise HTTPException(422,record['error']) from None
            return result

        @h.app.post('/api/tasks/{item_id}/materials/{material_id}/image-interpretation/adopt')
        def adopt(item_id:str,material_id:str,payload:AdoptRequest):
            if not payload.acknowledge_review or not payload.acknowledge_uncertainties or not payload.text.strip() or not payload.coverage_note.strip():raise HTTPException(422,'请人工核对文字、关系、缺失／不确定点和覆盖范围，并明确采用；JSON格式不证明OCR或全部图像已理解。')
            with h.store.lock:
                task,material=previews.owned(item_id,material_id);h.require_idle(task);h.require_revision(task,payload.revision)
                record=self.record(item_id,material_id,payload.plan_id)
                if record.get('status') not in {'candidate_ready','paused_candidate'} or record.get('candidate_token')!=payload.candidate_token:raise HTTPException(409,'图像候选已变化、未返回或已采用，不复用旧确认。')
                if record['revision']!=task['revision'] or record['source']['sha256']!=material.get('sha256') or material.get('status')!='needs_input':raise HTTPException(409,'当前任务修订或原材料已变化，未采用旧候选。')
                read_source(h,item_id,material)
                h.invalidate(task,'采用人工核对的图像模型候选前保存')
                material.update(status='parsed',text=payload.text,error='',source_kind='reviewed_model_image_text',source_file_parsed=False,source_coverage_note=payload.coverage_note,original_parse_error=material.get('error',''),image_model_response_received=True,image_candidate_id=record['id'],image_uncertainties=copy.deepcopy(record['candidate']['uncertainties']),text_reviewed_at=h.now())
                record.update(status='adopted',adopted_at=h.now(),applied_revision=task['revision'],adoption={'human_reviewed':True,'uncertainties_acknowledged':True})
                h.store.put_many([('image_preview',record['id'],record),('task',item_id,task)])
                return h.save_task(task)
