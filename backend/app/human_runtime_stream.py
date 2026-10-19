"""One-shot native workflow stream. Raw events/tokens never become public results."""
import asyncio,copy,json,re,time
import httpx
from .dify import DifyError
from .workflow_waiting import canonical
from .conversation_state import safe_text


class HumanStream:
    def __init__(self,workflow_id,review,rendered,forbidden=()):
        if not canonical(workflow_id):raise ValueError('发布Workflow标识无效。')
        self.workflow_id=workflow_id;self.review=copy.deepcopy(review);self.rendered=rendered
        self.forbidden=tuple(s for s in forbidden if s);self.run_id=None;self.form=None;self.token=None;self.done=False;self.count=0

    def failure(self):
        return DifyError('人工运行返回未适配、来源冲突或表单不可信，结果可能未知；不保存原文，不重跑或提交决定。',result={'workflow_run_id':self.run_id,'published_workflow_id':self.workflow_id,'business_verified':False,'form_available':False})

    def consume(self,payload):
        self.count+=1
        if self.done or self.count>500 or not isinstance(payload,str) or len(payload)>100000:raise self.failure()
        try:event=json.loads(payload)
        except (ValueError,TypeError,RecursionError):raise self.failure() from None
        if not isinstance(event,dict):raise self.failure()
        name=event.get('event');data=event.get('data')
        if name=='ping':return False
        rid=canonical(event.get('workflow_run_id'))
        if name=='workflow_started':
            if self.run_id or not isinstance(data,dict) or not rid or canonical(data.get('id'))!=rid or canonical(data.get('workflow_id'))!=self.workflow_id or data.get('reason') not in (None,'initial'):raise self.failure()
            self.run_id=rid;return False
        if not self.run_id or rid!=self.run_id:raise self.failure()
        if name=='human_input_required':
            if self.form or not isinstance(data,dict):raise self.failure()
            form_id=canonical(data.get('form_id'));token=data.get('form_token');content=data.get('form_content');expiry=data.get('expiration_time')
            if not form_id or data.get('node_id')!=self.review['node_id'] or data.get('inputs')!=[] or data.get('actions')!=self.review['actions'] or data.get('resolved_default_values')!={} or data.get('display_in_ui') is not True or data.get('approval_channels')!=[]:raise self.failure()
            if not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,512}',token) or not safe_text(content,16000) or content!=self.rendered or token in content or any(s in content for s in self.forbidden) or type(expiry)is not int or not time.time()<expiry<=time.time()+3*86400+300:raise self.failure()
            self.form={'form_id':form_id,'node_id':data['node_id'],'workflow_run_id':rid,'published_workflow_id':self.workflow_id,'content':content,'actions':copy.deepcopy(data['actions']),'expiration_time':expiry,'inputs':[],'source_verified':True,'business_verified':False}
            if any(s in json.dumps(self.form,ensure_ascii=False) for s in (token,*self.forbidden)):self.form=None;raise self.failure()
            self.token=token;return False
        if name=='workflow_paused':
            if not self.form or not isinstance(data,dict) or canonical(data.get('workflow_run_id'))!=rid or data.get('status')!='paused' or data.get('paused_nodes')!=[self.review['node_id']]:raise self.failure()
            self.done=True;return True
        if name in {'node_started','node_finished'}:
            if not isinstance(data,dict) or not isinstance(data.get('node_id'),str):raise self.failure()
            # Node raw inputs/outputs/metadata are deliberately not retained.
            return False
        # Unexpected completion/timeout/another form isn't success for this single review.
        raise self.failure()

    def receipt(self):
        if not self.done or not self.form or not self.token:raise self.failure()
        return copy.deepcopy(self.form),self.token


async def collect(client,inputs,user,parser,seconds=80):
    key=client.store.secret(client.env['id'],'service_api_key')
    if not key:raise DifyError('缺少本次新应用独立运行Key，未派发人工运行。')
    chars=0;buffer=[];size=0
    try:
        async with asyncio.timeout(seconds):
            async with httpx.AsyncClient(timeout=30,follow_redirects=False) as http:
                async with http.stream('POST',client.base+'/v1/workflows/run',headers={'Authorization':'Bearer '+key},json={'inputs':inputs,'response_mode':'streaming','user':user}) as response:
                    if response.is_error:raise DifyError(f'人工运行接口返回HTTP {response.status_code}；派发结果需核对，不重试。',http_status=response.status_code)
                    if 'text/event-stream' not in response.headers.get('content-type',''):raise parser.failure()
                    async for chunk in response.aiter_bytes():
                        chars+=len(chunk);size+=len(chunk)
                        if chars>2000000 or size>100000:raise parser.failure()
                        buffer.append(chunk)
                        raw=b''.join(buffer).replace(b'\r\n',b'\n')
                        while b'\n' in raw:
                            line,raw=raw.split(b'\n',1)
                            try:line=line.decode('utf-8')
                            except UnicodeError:raise parser.failure() from None
                            if not hasattr(parser,'_lines'):parser._lines=[]
                            if not line:
                                if parser._lines and parser.consume('\n'.join(parser._lines)):return parser.receipt()
                                parser._lines=[]
                            elif line.startswith('data:'):parser._lines.append(line[5:].lstrip(' '))
                        buffer=[raw];size=len(raw)
                    if buffer and buffer[0].strip():raise parser.failure()
                    if getattr(parser,'_lines',None) and parser.consume('\n'.join(parser._lines)):return parser.receipt()
                    raise parser.failure()
    except (TimeoutError,httpx.RequestError,asyncio.CancelledError):raise parser.failure() from None


def render(root,values):
    """Match only supported native two-part text references, without executing Jinja."""
    nodes=root['workflow']['graph']['nodes'];pool={}
    for node in nodes:
        data=node['data']
        if data['type']=='start':
            for field in data.get('variables',[]):
                value=values.get(field['variable'],field.get('default'))
                if not isinstance(value,str):raise ValueError('审核引用不能以空值或默认猜作文字。')
                pool[(node['id'],field['variable'])]=value
        elif data['type']=='template-transform':pool[(node['id'],'output')]=data['template']
    review=next(n for n in nodes if n['data']['type']=='human-input');text=review['data']['form_content']
    def replace(match):
        selector=tuple(match.group(1).split('.'))
        if selector not in pool:raise ValueError('实际审核对象的文字来源未适配，不猜测渲染。')
        return pool[selector]
    result=re.sub(r'\{\{#(.*?)#\}\}',replace,text)
    if not safe_text(result,16000):raise ValueError('渲染审核对象过长或含凭据。')
    return result
