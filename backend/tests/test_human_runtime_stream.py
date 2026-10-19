import asyncio,copy,json,time,uuid
import pytest,yaml,httpx
from test_human_review import plan,task
from app.human_runtime_stream import HumanStream,collect,render
from app.workflow_plan import compile_workflow_plan
from app.dify import DifyClient,DifyError

WORKFLOW=str(uuid.uuid4());RUN=str(uuid.uuid4());FORM=str(uuid.uuid4());TOKEN='private-form-token-0123456789';KEY='private-application-key'

def parser():return HumanStream(WORKFLOW,{'node_id':'review','actions':plan()['nodes'][1]['config']['user_actions']},'请审核：\n技术对象')
def events():return [
 {'event':'workflow_started','workflow_run_id':RUN,'data':{'id':RUN,'workflow_id':WORKFLOW,'reason':'initial'}},
 {'event':'human_input_required','workflow_run_id':RUN,'data':{'form_id':FORM,'node_id':'review','form_content':'请审核：\n技术对象','inputs':[],'actions':plan()['nodes'][1]['config']['user_actions'],'display_in_ui':True,'form_token':TOKEN,'approval_channels':[],'resolved_default_values':{},'expiration_time':int(time.time())+3000}},
 {'event':'workflow_paused','workflow_run_id':RUN,'data':{'workflow_run_id':RUN,'status':'paused','paused_nodes':['review'],'reasons':[{'form_token':TOKEN,'extra':'never-store'}],'outputs':{'private':'never-store'}}}]

def test_source_verified_receipt_separates_token_and_drops_raw_details():
 p=parser()
 for event in events():p.consume(json.dumps(event,ensure_ascii=False))
 public,secret=p.receipt();assert secret==TOKEN and public['form_id']==FORM and public['workflow_run_id']==RUN
 assert TOKEN not in json.dumps(public) and 'never-store' not in json.dumps(public) and public['source_verified'] and not public['business_verified']

@pytest.mark.parametrize('change',['run','workflow','node','form','actions','inputs','content','expiry','channels','display','token','paused_nodes','paused_id','missing_form','duplicate_form','finish'])
def test_untrusted_or_unadapted_events_never_make_usable_form(change):
 rows=events()
 if change=='run':rows[1]['workflow_run_id']=str(uuid.uuid4())
 elif change=='workflow':rows[0]['data']['workflow_id']=str(uuid.uuid4())
 elif change=='node':rows[1]['data']['node_id']='other'
 elif change=='form':rows[1]['data']['form_id']='not-id'
 elif change=='actions':rows[1]['data']['actions'][0]['title']='different'
 elif change=='inputs':rows[1]['data']['inputs']=[{'name':'extra'}]
 elif change=='content':rows[1]['data']['form_content']='different'
 elif change=='expiry':rows[1]['data']['expiration_time']=True
 elif change=='channels':rows[1]['data']['approval_channels']=['email']
 elif change=='display':rows[1]['data']['display_in_ui']=False
 elif change=='token':rows[1]['data']['form_token']='unsafe/token'
 elif change=='paused_nodes':rows[2]['data']['paused_nodes'].append('other')
 elif change=='paused_id':rows[2]['data']['workflow_run_id']=str(uuid.uuid4())
 elif change=='missing_form':rows.pop(1)
 elif change=='duplicate_form':rows.insert(2,copy.deepcopy(rows[1]))
 else:rows[2]['event']='workflow_finished'
 p=parser()
 with pytest.raises(DifyError) as exc:
  for row in rows:p.consume(json.dumps(row))
 assert TOKEN not in str(exc.value) and TOKEN not in json.dumps(exc.value.result)
 with pytest.raises(DifyError):p.receipt()

def test_render_is_text_substitution_only_not_template_execution():
 root=yaml.safe_load(compile_workflow_plan(task(plan()))[0]);assert render(root,{'query':'{{7*7}}'})=='请审核：\n{{7*7}}'
 root['workflow']['graph']['nodes'][1]['data']['form_content']='{{#result2.output#}}';assert render(root,{'query':'技术对象'})=='已批准'
 with pytest.raises(ValueError):render(root,{})

def test_deep_event_is_safe_unknown_not_raw_json_or_lost_known_run():
 p=parser();p.consume(json.dumps(events()[0]))
 with pytest.raises(DifyError) as exc:p.consume('['*2000+'0'+']'*2000)
 assert exc.value.result['workflow_run_id']==RUN and TOKEN not in str(exc.value)

class Bytes(httpx.AsyncByteStream):
 def __init__(self,chunks):self.chunks=chunks
 async def __aiter__(self):
  for chunk in self.chunks:yield chunk

@pytest.mark.parametrize('mode',['ok','broken','http','wrong_type','large','conflict'])
def test_one_post_bounded_stream_no_stop_retry_or_secret_error(monkeypatch,mode):
 calls=[];real=httpx.AsyncClient;p=parser();rows=events()
 if mode=='conflict':rows[1]['workflow_run_id']=str(uuid.uuid4())
 body=b''.join(('data: '+json.dumps(e,ensure_ascii=False)+'\r\n\r\n').encode() for e in rows)
 if mode=='broken':body=body[:body.find(b'data: {"event": "workflow_paused')]
 if mode=='large':body=b'x'*100001
 async def handle(req):
  calls.append(req);return httpx.Response(401 if mode=='http' else 200,headers={'content-type':'application/json' if mode=='wrong_type' else 'text/event-stream'},stream=Bytes([body[i:i+17] for i in range(0,len(body),17)]))
 monkeypatch.setattr(httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handle),**kw))
 store=type('Secrets',(),{'secret':lambda self,owner,key:KEY})();client=DifyClient({'id':'local','base_url':'http://127.0.0.1:8080'},store)
 if mode=='ok':assert (asyncio.run(collect(client,{'query':'技术对象'},'fixed-user',p)))[1]==TOKEN
 else:
  with pytest.raises(DifyError) as exc:asyncio.run(collect(client,{'query':'技术对象'},'fixed-user',p))
  assert TOKEN not in str(exc.value) and KEY not in str(exc.value)
 assert len(calls)==1 and calls[0].method=='POST' and calls[0].url.path=='/v1/workflows/run'
 assert json.loads(calls[0].content)['response_mode']=='streaming'
