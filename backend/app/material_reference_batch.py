"""Explicit per-material reference intentions, previewed before one revision write."""
import hashlib,hmac,json,re
from fastapi import APIRouter,HTTPException
from fastapi.responses import JSONResponse
from .plan_drafts import DraftRoute
from .provider_tool_probe import strict_json
NOTE='只调整逐份明确选择的引用意图，不代表材料已解析、完整读取或业务事实正确；保存为一次新修订，使相关需求/配置确认和验证失效，须重新复核。不改原件或自动采用内容，不调用模型/Dify。'

def digest(value):
    try:return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,separators=(',',':')).encode('ascii')).hexdigest()
    except (ValueError,TypeError,UnicodeError,RecursionError,OverflowError):raise HTTPException(422,'材料来源结构无法完整核对，未忽略部分来源。') from None

class ReferenceRoute(DraftRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:
                raw=await request.body()
                if len(raw)>16384 or not isinstance(strict_json(raw),dict):raise ValueError()
            except (ValueError,TypeError,UnicodeError,RecursionError):return JSONResponse(status_code=422,content={'detail':'引用方式请求须为16KB内的有限、无重复键JSON对象，未读取或回显原输入。'},headers={'Cache-Control':'no-store'})
            response=await original(request);response.headers['Cache-Control']='no-store';return response
        return guarded

def preview(task,payload,*,applying=False):
    keys={'revision','items'}|({'review_token','acknowledge'} if applying else set())
    if set(payload)!=keys or type(payload.get('revision'))is not int or payload['revision']<1:raise HTTPException(422,'请明确当前修订与逐份引用方案，不接受额外字段。')
    if payload['revision']!=task['revision']:raise HTTPException(409,'任务修订已变化，未沿用旧引用方案。')
    items=payload['items'];materials=task.get('materials')
    if not isinstance(items,list) or not 1<=len(items)<=10 or not isinstance(materials,list):raise HTTPException(422,'每次须明确选择1—10份已保存材料，未猜测或截断。')
    rows=[];seen=set()
    for item in items:
        if not isinstance(item,dict) or set(item)!={'id','source_sha256','reference_mode','preserve_items'}:raise HTTPException(422,'每份须完整提供材料ID、保存摘要、引用方式和保留说明。')
        mid=item['id'];sha=item['source_sha256'];mode=item['reference_mode'];note=item['preserve_items']
        if not isinstance(mid,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',mid) or mid in seen or not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):raise HTTPException(422,'材料ID须可唯一定位且保存摘要明确，不接受重复或未知来源。')
        seen.add(mid)
        if not isinstance(mode,str) or mode not in {'borrow','preserve','replicate'} or not isinstance(note,str) or len(note)>300 or (mode=='preserve' and not note.strip()) or (mode!='preserve' and note!=''):raise HTTPException(422,'每份必须主动选择引用方式；保留指定部分须有1—300码点说明，其它方式保留说明须为空，更长说明请用原单份入口。')
        matches=[m for m in materials if isinstance(m,dict) and m.get('id')==mid]
        if len(matches)!=1:raise HTTPException(409,'所选材料不在本任务或ID重复，未猜测归属。')
        material=matches[0]
        if material.get('sha256')!=sha:raise HTTPException(409,'材料保存摘要已变化，未沿用旧方案。')
        name=material.get('name',material.get('filename',mid));old_mode=material.get('reference_mode');old_note=material.get('preserve_items','');status=material.get('status')
        if not isinstance(name,str) or len(name)>300 or old_mode is not None and old_mode not in ('borrow','preserve','replicate') or not isinstance(old_note,str) or len(old_note)>2000 or not isinstance(status,str) or len(status)>100:raise HTTPException(422,'原引用记录或显示范围无法完整核对，未省略旧设置后保存。')
        try:name.encode('utf-8');note.encode('utf-8');old_note.encode('utf-8');status.encode('utf-8')
        except UnicodeError:raise HTTPException(422,'引用文字编码无法完整核对，未替换字符。') from None
        before={'reference_mode':old_mode,'preserve_items':old_note};after={'reference_mode':mode,'preserve_items':note.strip()}
        rows.append({'id':mid,'source_sha256':sha,'name':name,'status':status,'source_token':digest(material),'before':before,'after':after,'changed':before!=after})
    result={'schema_version':1,'task_id':task['id'],'revision':task['revision'],'items':rows,'changed_count':sum(row['changed'] for row in rows),'task_modified':False,'original_files_changed':False,'model_called':False,'external_network_requested':False,'business_verified':False,'note':NOTE}
    result['review_token']=digest(result);return result

def register(h):
    router=APIRouter(route_class=ReferenceRoute)
    @router.post('/api/tasks/{item_id}/materials/reference-batch/preview')
    def read(item_id:str,payload:dict):
        with h.store.lock:return preview(h.get_task(item_id),payload)
    @router.post('/api/tasks/{item_id}/materials/reference-batch/apply')
    def apply(item_id:str,payload:dict):
        with h.store.lock:
            task=h.get_task(item_id);h.require_idle(task);value=preview(task,payload,applying=True)
            token=payload['review_token']
            if payload['acknowledge'] is not True or not isinstance(token,str) or not re.fullmatch('[a-f0-9]{64}',token):raise HTTPException(422,'须明确复核逐份旧新设置和新修订失效范围。')
            if not hmac.compare_digest(token,value['review_token']):raise HTTPException(409,'材料、原引用设置或预览方案已变化，未保存旧方案。')
            if not value['changed_count']:raise HTTPException(422,'所选引用设置均未变化，未生成空修订或使确认失效。')
            h.invalidate(task,'批量变更材料引用方式前保存')
            updates={row['id']:row['after'] for row in value['items']}
            for material in task['materials']:
                if isinstance(material,dict) and material.get('id') in updates:material.update(updates[material['id']])
            return h.save_task(task)
    h.app.include_router(router)
