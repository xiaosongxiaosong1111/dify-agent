"""Portable case definitions only; previews never save, run or adopt anything."""
import copy,hashlib,json,re,uuid
from pathlib import Path
from fastapi import APIRouter,File,Form,HTTPException,Request,UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse,Response
from fastapi.routing import APIRoute
from .plan_text_codec import parse
from .plan_drafts import inspect_text
from .evaluation import validate_test_cases

LIMIT=512_000
MAX_CASES=20
NOTE='仅样例定义，不含运行成绩、旧样例ID、确认或资源身份。预览后明确选择只追加到未保存草稿；原样例保持，仍需保存为新修订并复核，不运行、不调用模型/Dify。文件来源请保留原件，文件摘要不证明业务事实或来源作者。'

class CaseSetRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def guarded(request):
            try:response=await original(request)
            except RequestValidationError:return JSONResponse(status_code=422,content={'detail':'请明确选择样例JSON文件、当前修订和本次请求标识，未回显输入。'},headers={'Cache-Control':'no-store'})
            response.headers['Cache-Control']='no-store';return response
        return guarded

def revision_number(value):
    if not isinstance(value,str) or not re.fullmatch(r'[1-9][0-9]{0,15}',value) or int(value)>9007199254740991:raise HTTPException(422,'样例定义读取须有明确正整数修订，不接受布尔、指数或未知值。')
    return int(value)

def safe_values(value):
    stack=[(value,0)];count=0
    while stack:
        item,depth=stack.pop();count+=1
        if count>100000 or depth>64:raise HTTPException(422,'样例定义超过结构/深度范围，未读取部分结果。')
        if type(item)is int and abs(item)>9007199254740991:raise HTTPException(422,'定义含浏览器不能无损编辑的整数，请先明确文本或其它方案，未舍入。')
        if isinstance(item,dict):stack.extend((v,depth+1) for v in item.values())
        elif isinstance(item,list):stack.extend((v,depth+1) for v in item)

def definitions(rows,app_type,*,exporting=False):
    if not isinstance(rows,list) or not 1<=len(rows)<=MAX_CASES:raise HTTPException(422,'本批须有1—20个完整样例，不截断或导出空定义包。')
    safe_values(rows)
    result=[]
    for case in rows:
        if not isinstance(case,dict):raise HTTPException(422,'每个样例须为明确的定义对象。')
        value=copy.deepcopy(case)
        if exporting:
            value.pop('id',None);value.setdefault('required',True)
        allowed={'name','input','expectation','required','followups'}
        if set(value)-allowed or not {'name','input','expectation','required'}<=set(value):raise HTTPException(422,'样例包仅接受名称、输入、预期、必选及可选追问；不接收旧ID、成绩、确认、资源或未知字段。')
        if not isinstance(value['name'],str) or not value['name'] or value['name'].strip()!=value['name'] or len(value['name'])>200 or type(value['required'])is not bool:raise HTTPException(422,'名称须为1—200码点且无首尾空格，required须明确布尔值；未替用户规范化。')
        turns=[value]+(value.get('followups') if isinstance(value.get('followups'),list) else [])
        for turn in turns:
            if not isinstance(turn,dict) or not isinstance(turn.get('input'),dict) or not isinstance(turn.get('expectation'),dict):raise HTTPException(422,'每轮须有明确JSON输入对象和预期对象。')
            if 'conversation_id' in turn['input']:raise HTTPException(422,'定义包不复用会话身份；请用现有新会话样例/续聊入口。')
            pending=[turn['input']]
            while pending:
                node=pending.pop()
                if isinstance(node,dict):
                    if 'upload_file_id' in node or 'transfer_method' in node:raise HTTPException(422,'定义包首批不迁移上传文件身份或文件传输对象，请使用专用文件样例入口。')
                    pending.extend(node.values())
                elif isinstance(node,list):pending.extend(node)
            expectation=turn['expectation'];mode=expectation.get('mode')
            if mode=='manual':
                if set(expectation)!={'mode','description'} or not isinstance(expectation['description'],str) or not expectation['description'].strip() or expectation['description'].strip()!=expectation['description'] or len(expectation['description'])>2000:raise HTTPException(422,'人工规则须只有mode和1—2000码点完整判断标准，不接受会被编辑器丢弃的额外字段或首尾空格。')
            else:
                if set(expectation)!={'mode','target','expected'} or not isinstance(expectation.get('target'),str) or expectation['target'].strip()!=expectation['target'] or len(expectation['target'])>200:raise HTTPException(422,'自动规则须有明确mode/target/expected，不省略未知字段或裁剪路径。')
                expected=expectation['expected']
                if mode in {'contains','json_keys'} and (not isinstance(expected,list) or not expected or len(expected)>200 or any(not isinstance(x,str) or not x or x.strip()!=x or '\n' in x or '\r' in x or len(x)>300 for x in expected)):raise HTTPException(422,'关键词/字段须为明确非空文字列表，各项不含首尾空格或换行；本批不悄悄转换旧字符串规则。')
                if mode=='json_schema':
                    if not isinstance(expected,str):raise HTTPException(422,'Schema规则须为明确JSON原文；本批不转换旧对象表示，请先在原编辑器核对。')
                    try:parse(expected)
                    except ValueError:raise HTTPException(422,'Schema原文含不明确JSON或数值损失，未修改约束后导入。') from None
        result.append(value)
    checked=validate_test_cases(result,app_type)
    if not checked['valid']:raise HTTPException(422,'样例定义不满足当前类型/轮次/预期规则；请核对完整定义，不回显可能私有的原值。')
    try:inspect_text(json.dumps(result,ensure_ascii=False,allow_nan=False))
    except HTTPException:raise HTTPException(422,'样例定义的结构/编码未能完整检查或疑似含明文凭据；未导出、保存或回显原值，请保留原文件核对。') from None
    return result

def register(h):
    router=APIRouter(route_class=CaseSetRoute)
    def task_at(item_id,revision):
        task=h.get_task(item_id)
        if type(task.get('revision'))is not int or not 1<=task['revision']<=9007199254740991:raise HTTPException(409,'任务修订不能完整核对，未导出或预览定义。')
        h.require_revision(task,revision)
        if task['app_type'] not in {'workflow','advanced-chat','agent'}:raise HTTPException(422,'本批定义包仅支持已有Workflow/Chatflow/原生Agent，不更换类型。')
        return task
    @router.get('/api/tasks/{item_id}/test-cases/export')
    def export(item_id:str,revision:str|None=None):
        number=revision_number(revision)
        with h.store.lock:
            task=task_at(item_id,number);rows=definitions(task.get('test_cases'),task['app_type'],exporting=True)
            try:raw=json.dumps({'schema_version':1,'app_type':task['app_type'],'cases':rows},ensure_ascii=False,allow_nan=False,indent=2).encode('utf-8')
            except (ValueError,TypeError,UnicodeError,RecursionError):raise HTTPException(422,'定义编码无法完整输出，未替换文字。') from None
            if len(raw)>LIMIT:raise HTTPException(413,'完整定义包超过512000字节，未截断或只导出部分。')
            return Response(raw,media_type='application/json',headers={'Content-Disposition':f'attachment; filename="sierra-cases-r{number}.json"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','X-Sierra-Task-ID':task['id'],'X-Sierra-Revision':str(number),'X-Sierra-Definitions-SHA256':hashlib.sha256(raw).hexdigest()})
    @router.post('/api/tasks/{item_id}/test-cases/import-preview')
    async def read(item_id:str,request:Request,file:UploadFile=File(...),revision:str=Form(...),request_nonce:str=Form(...)):
        fields=await request.form()
        if set(fields)!={'file','revision','request_nonce'} or any(len(fields.getlist(k))!=1 for k in fields):raise HTTPException(422,'只接受一份文件、修订和本次标识，不接受重复或额外表单字段。')
        number=revision_number(revision)
        if not re.fullmatch(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}',request_nonce):raise HTTPException(422,'本次预览标识无法核对。')
        with h.store.lock:app_type=task_at(item_id,number)['app_type']
        raw=await file.read(LIMIT+1)
        if len(raw)>LIMIT:raise HTTPException(413,'样例文件最多512000字节，未截断或导入部分。')
        name=Path((file.filename or '').replace('\\','/')).name
        if not name or len(name)>200 or not name.isprintable():raise HTTPException(422,'文件名无法完整显示来源，请使用明确的短文件名。')
        try:
            value=parse(raw.decode('utf-8-sig'))
            if set(value)!={'schema_version','app_type','cases'} or type(value['schema_version'])is not int or value['schema_version']!=1:raise ValueError()
        except (ValueError,UnicodeError,TypeError):raise HTTPException(422,'文件须为UTF8定义包1版，明确schema_version/app_type/cases；不接收重复键、非有限数、数值损失、旧成绩或未知字段。') from None
        if value['app_type']!=app_type:raise HTTPException(422,'文件应用类型与当前任务不同，未更换类型或转换样例。')
        rows=definitions(value['cases'],app_type)
        with h.store.lock:task_at(item_id,number)
        return {'schema_version':1,'task_id':item_id,'revision':number,'app_type':app_type,'request_nonce':request_nonce,
                'source':{'name':name,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'encoding':'utf-8'},
                'cases':[{**row,'id':str(uuid.uuid4())} for row in rows],'verification':'case_definitions_only',
                'task_changed':False,'network_requested':False,'model_called':False,'run_started':False,'business_verified':False,'note':NOTE}
    h.app.include_router(router)
