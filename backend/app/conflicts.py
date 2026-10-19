"""Evidence-backed conflict proposals and explicit requirement replacement decisions."""
from .contract_loading import load_contract
import copy,re
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,StrictInt,StrictBool
from .coverage import digest,SOURCE_FIELDS


class Revision(BaseModel):
    model_config=ConfigDict(extra='forbid')
    revision:StrictInt


class ReviewRequest(Revision):
    review:dict


class ConfirmRequest(Revision):
    review_token:str
    acknowledge_review:StrictBool


class DecisionRequest(ConfirmRequest):
    conflict_id:str
    option_id:str
    acknowledge_replacement:StrictBool


def context(task):
    return {'app_type':task['app_type'],'requirements':task['requirements'],'materials':task.get('materials',[])}


def sources(task):
    result={('requirement',key):value for key,value in task['requirements'].items() if value.strip()}
    for m in task.get('materials',[]):
        if m.get('status')=='parsed' and isinstance(m.get('text'),str) and m['text'].strip():result[('material',m['id'])]=m['text']
    confirmed={c.get('revision') for c in task.get('confirmations',[]) if c.get('kind')=='requirements'}
    # Old confirmed facts remain available as evidence; only this task's history.
    for version in task.get('versions',[]):
        if version.get('revision') in confirmed:
            for key,value in version.get('requirements',{}).items():
                if isinstance(value,str) and value.strip():result[('version',version['id']+':'+key)]=value
    return result


def validate_review(task,review):
    errors=[]
    if not isinstance(review,dict) or set(review)!={'schema_version','conflicts','notes'} or type(review.get('schema_version')) is not int or review['schema_version']!=1:
        return {'valid':False,'errors':['冲突检查须包含 schema_version=1、conflicts 和 notes。']}
    rows=review['conflicts'];notes=review['notes']
    if not isinstance(rows,list) or len(rows)>20 or not isinstance(notes,str) or not notes.strip() or len(notes)>3000:
        return {'valid':False,'errors':['冲突最多 20 项；检查说明须非空且最多 3000 字。']}
    available=sources(task);seen=set()
    text_fields=('title','question','recommendation_reason')
    for i,row in enumerate(rows,1):
        prefix=f'冲突 {i}'
        if not isinstance(row,dict) or set(row)!={'id','title','sources','question','options','recommended_option_id','recommendation_reason'}:errors.append(prefix+' 字段不完整或有未知字段。');continue
        cid=row['id']
        if not isinstance(cid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',cid) or cid in seen:errors.append(prefix+' ID 须唯一、非空，且只含字母／数字／下划线／连字符。')
        else:seen.add(cid)
        for field in text_fields:
            if not isinstance(row[field],str) or not row[field].strip() or len(row[field])>3000:errors.append(prefix+' 的标题、问题和推荐理由须非空且最多 3000 字。')
        refs=row['sources'];quoted=set()
        if not isinstance(refs,list) or not 2<=len(refs)<=6:errors.append(prefix+' 须有 2—6 条可核对的来源。')
        else:
            for ref in refs:
                if not isinstance(ref,dict) or set(ref)!={'kind','id','quote'} or not all(isinstance(ref[k],str) for k in ('kind','id','quote')):errors.append(prefix+' 来源须包含 kind、id、quote 三个文本字段。');continue
                text=available.get((ref['kind'],ref['id']))
                if not isinstance(text,str) or not ref['quote'].strip() or len(ref['quote'])>3000 or ref['quote'] not in text:errors.append(prefix+' 引文不是本任务当前资料或已确认历史中的原文。')
                quoted.add((ref['kind'],ref['id'],ref['quote']))
            if len(quoted)<2:errors.append(prefix+' 不能重复同一引文来伪装两个冲突来源。')
        options=row['options'];option_ids=set()
        if not isinstance(options,list) or not 2<=len(options)<=4:errors.append(prefix+' 须列出 2—4 个可供选择的处理方案。');continue
        for option in options:
            if not isinstance(option,dict) or set(option)!={'id','label','requirements_patch','experience','cost','manual_work'}:errors.append(prefix+' 选项字段不完整。');continue
            oid=option['id']
            if not isinstance(oid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',oid) or oid in option_ids:errors.append(prefix+' 选项 ID 须唯一且为有效标识。')
            else:option_ids.add(oid)
            for field in ('label','experience','cost','manual_work'):
                if not isinstance(option[field],str) or not option[field].strip() or len(option[field])>3000:errors.append(prefix+' 每种方案均需说明体验、费用与人工影响；无影响可明确填写无。')
            patch=option['requirements_patch']
            if not isinstance(patch,dict) or not patch or set(patch)-SOURCE_FIELDS or any(not isinstance(v,str) or not v.strip() or len(v)>8000 for v in patch.values()):errors.append(prefix+' 方案须给出允许的八类需求字段的完整替换文本，不能修改类型／配置／状态。')
        if not isinstance(row['recommended_option_id'],str) or row['recommended_option_id'] not in option_ids:errors.append(prefix+' 推荐项须是已列出的真实选项。')
    old=(task.get('conflict_review') or {}).get('review',{}).get('conflicts',[])
    if {c['id'] for c in old}-seen:errors.append('已有未决冲突不能静默删除；须明确选择方案或保留并重新核对来源。')
    return {'valid':not errors,'errors':list(dict.fromkeys(errors))}


def summary(task):
    record=task.get('conflict_review');enabled=bool(task.get('conflict_enabled') or record)
    review=(record or {}).get('review');stale=bool(record and record.get('context_digest')!=digest(context(task)))
    token=digest({'context':context(task),'review':review})
    errors=validate_review(task,review)['errors'] if review else []
    blockers=[]
    if enabled and not record:blockers.append('已启用冲突检查，请重新检查并保存。')
    if stale:blockers.append('需求或资料已变化，旧冲突检查／裁定不可直接沿用，请重新复核。')
    if review and review['conflicts']:blockers.append(f"仍有 {len(review['conflicts'])} 项待裁定冲突，不能确认需求或搭建。")
    blockers.extend(errors)
    confirmed=bool(enabled and record and not blockers and record.get('confirmation',{}).get('token')==token)
    if enabled and not confirmed and not blockers:blockers.append('尚未明确确认当前已列分歧的处理结果。')
    return {'enabled':enabled,'record':record,'stale':stale,'confirmed':confirmed,'revision':task['revision'],'review_token':token,'blockers':blockers,'decisions':task.get('conflict_decisions',[]),'verification':'source_quote_and_user_decision_only'}


def require_ready(task):
    state=summary(task)
    if state['enabled'] and not state['confirmed']:raise HTTPException(422,'需求冲突尚未处理：'+'；'.join(state['blockers']))


class ConflictManager:
    def __init__(self,host):self.h=host

    def save(self,task,review,origin):
        h=self.h;checked=validate_review(task,review)
        if not checked['valid']:raise HTTPException(422,'冲突检查失败：'+'；'.join(checked['errors']))
        h.invalidate(task,'冲突清单保存前记录')
        task['conflict_enabled']=True
        task['conflict_review']={'review':copy.deepcopy(review),'source':origin,'origin_revision':task['revision'],'context_digest':digest(context(task)),'created_at':h.now(),'confirmation':{}}
        return h.save_task(task)

    def register(self):
        h=self.h
        @h.app.get('/api/tasks/{item_id}/conflicts')
        def get_conflicts(item_id:str):return summary(h.get_task(item_id))

        @h.app.post('/api/tasks/{item_id}/conflicts')
        def save_conflicts(item_id:str,payload:ReviewRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision)
                return self.save(task,payload.review,'manual')

        @h.app.post('/api/tasks/{item_id}/conflicts/confirm')
        def confirm_conflicts(item_id:str,payload:ConfirmRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);state=summary(task)
                if payload.acknowledge_review is not True:raise HTTPException(422,'请明确确认已复核当前冲突处理结果。')
                if not state['record'] or state['stale'] or state['review_token']!=payload.review_token:raise HTTPException(409,'来源或清单已变化，请重新检查。')
                if state['record']['review']['conflicts'] or validate_review(task,state['record']['review'])['errors']:raise HTTPException(422,'未决冲突或无效来源尚未处理。')
                task['conflict_review']['confirmation']={'token':state['review_token'],'revision':task['revision'],'created_at':h.now()}
                task.setdefault('confirmations',[]).append({'kind':'conflicts',**task['conflict_review']['confirmation']})
                return h.save_task(task)

        @h.app.post('/api/tasks/{item_id}/conflicts/decide')
        def decide(item_id:str,payload:DecisionRequest):
            with h.store.lock:
                task=h.get_task(item_id);h.require_idle(task);h.require_revision(task,payload.revision);state=summary(task)
                if not payload.acknowledge_review or not payload.acknowledge_replacement:raise HTTPException(422,'请核对所选方案及所有字段的完整替换前后内容，明确接受影响。')
                if not state['record'] or state['stale'] or state['review_token']!=payload.review_token:raise HTTPException(409,'来源或选项已变化，决定未应用。')
                checked=validate_review(task,state['record']['review'])
                if not checked['valid']:raise HTTPException(422,'来源或选项不再有效，请重新检查。')
                row=next((r for r in state['record']['review']['conflicts'] if r['id']==payload.conflict_id),None)
                option=next((o for o in (row or {}).get('options',[]) if o['id']==payload.option_id),None)
                if not row or not option:raise HTTPException(422,'请选本任务当前列出的具体方案，不会自动采用推荐项。')
                before={k:task['requirements'][k] for k in option['requirements_patch']};original_revision=task['revision']
                h.invalidate(task,'冲突裁定应用前保存')
                task['requirements'].update({k:v.strip() for k,v in option['requirements_patch'].items()})
                task.setdefault('conflict_decisions',[]).append({'conflict':copy.deepcopy(row),'selected_option':copy.deepcopy(option),'before':before,'after':{k:task['requirements'][k] for k in option['requirements_patch']},'source_revision':original_revision,'result_revision':task['revision'],'created_at':h.now()})
                remaining=[r for r in state['record']['review']['conflicts'] if r['id']!=row['id']]
                task['conflict_review']={'review':{'schema_version':1,'conflicts':copy.deepcopy(remaining),'notes':'已将明确选择写回需求；剩余分歧须重新核对，未声明已全面消除冲突。'},'source':'user_decision','origin_revision':task['revision'],'context_digest':state['record']['context_digest'] if remaining else digest(context(task)),'created_at':h.now(),'confirmation':{}}
                return h.save_task(task)

        @h.app.post('/api/tasks/{item_id}/conflicts/generate')
        async def generate(item_id:str,payload:Revision):
            from .bounded_suggestions import suggest
            import json
            def messages(task):
                available=sources(task);ordered=sorted(available,key=lambda k:k[0]=='version');snippets=[];remaining=24000
                for kind,sid in ordered:
                    text=available[(kind,sid)];excerpt=text[:min(6000,remaining)];remaining-=len(excerpt)
                    if excerpt:snippets.append({'kind':kind,'id':sid,'text':excerpt,'excerpt_truncated':len(excerpt)<len(text)})
                if not snippets:raise HTTPException(422,'请先提供需求或可解析资料，不能对空内容声称已检查。')
                prompt=load_contract(h.PROJECT_ROOT,'conflict-contract.md')
                known=[{'id':r['id'],'title':r['title'],'source_refs':[{'kind':s['kind'],'id':s['id']} for s in r['sources']]} for r in (task.get('conflict_review') or {}).get('review',{}).get('conflicts',[])]
                decisions=[{'conflict_id':d['conflict']['id'],'title':d['conflict']['title'],'option_id':d['selected_option']['id'],'label':d['selected_option']['label'],'result_revision':d['result_revision']} for d in task.get('conflict_decisions',[])[-10:]]
                return [{'role':'system','content':prompt},{'role':'user','content':json.dumps({'app_type':task['app_type'],'requirements':task['requirements'],'sources':snippets,'known_conflicts':known,'prior_decisions':decisions},ensure_ascii=False)}]
            return await suggest(h,item_id,payload.revision,'conflicts',messages,validate_review,lambda t,r:self.save(t,r,'model'))
