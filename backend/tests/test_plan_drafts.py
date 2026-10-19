import copy,json
import pytest
from test_api import client,create,approved
from app import main
from app.storage import Store

def endpoint(t):return f"/api/tasks/{t['id']}/plan-draft"
def save(client,t,text='{unfinished',counter=0,**patch):
 return client.put(endpoint(t),json={'revision':t['revision'],'draft_revision':counter,'text':text,**patch})

@pytest.mark.parametrize('mode',['workflow','advanced-chat','agent'])
def test_incomplete_draft_is_persistent_unconfirmed_and_does_not_change_task(client,mode):
 t=create(client,app_type=mode);before=copy.deepcopy(main.get_task(t['id']))
 result=save(client,t);assert result.status_code==200,result.text
 state=result.json();assert state['draft_revision']==1 and not state['stale']
 assert state['record']['verification']=='unconfirmed_local_draft' and state['record']['json_state']=='incomplete_or_invalid'
 assert state['record']['app_type']==mode and state['record']['text']=='{unfinished'
 assert main.get_task(t['id'])==before
 restarted=Store(main.store.root);assert restarted.get('plan_draft',t['id'])['text']=='{unfinished'

@pytest.mark.parametrize('text,state',[('{"schema_version":1,"nodes":[]}','json_object'),('[1,2]','json_non_object'),('{"a":1,"a":2}','incomplete_or_invalid'),('{"a":NaN}','incomplete_or_invalid')])
def test_saved_text_is_not_rewritten_or_claimed_to_be_valid_ir(client,text,state):
 t=create(client);response=save(client,t,text);assert response.status_code==200,response.text
 record=response.json()['record'];assert record['text']==text and record['json_state']==state and record['byte_count']==len(text.encode('utf8'))

def test_counter_conflict_keeps_both_server_draft_and_local_caller_payload(client):
 t=create(client);assert save(client,t,'first incomplete').status_code==200
 response=save(client,t,'second incomplete',0);assert response.status_code==409
 state=client.get(endpoint(t)).json();assert state['draft_revision']==1 and state['record']['text']=='first incomplete'

def test_discard_tombstone_prevents_old_tab_recreating_zero_version(client):
 t=create(client);save(client,t)
 r=client.request('DELETE',endpoint(t),json={'revision':t['revision'],'draft_revision':1});assert r.status_code==200
 assert r.json()['record'] is None and r.json()['draft_revision']==2
 assert save(client,t,'old tab',0).status_code==409
 assert save(client,t,'new edit',2).json()['draft_revision']==3

def test_revision_change_retains_stale_draft_but_blocks_old_revision_write(client):
 t=create(client);save(client,t)
 updated=client.patch(f"/api/tasks/{t['id']}",json={'requirements':{k:'新的明确需求' for k in main.REQ_KEYS}}).json();assert updated['revision']>t['revision']
 state=client.get(endpoint(t)).json();assert state['stale'] and state['blocker'] and state['record']['text']=='{unfinished'
 assert save(client,t,'stale write',1).status_code==409
 assert save(client,updated,'explicit current edit',1).status_code==200

@pytest.mark.parametrize('patch',[{'revision':True},{'draft_revision':True},{'draft_revision':-1},{'text':123},{'unexpected':True}])
def test_strict_versions_and_payload_do_not_create_a_draft(client,patch):
 t=create(client);assert save(client,t,**patch).status_code==422
 assert main.store.get('plan_draft',t['id']) is None

@pytest.mark.parametrize('text',[
 'sk-123456789abcdef123456789',
 'Bearer abcdefghijklmnopqrst',
 '{"api_key":"opaque-private-value",',
 '{"instruction":"password = \'opaque-private-value\'"}',
 '{"api_\\u006bey":"opaque-private-value"}',
 '{"instruction":"sk\\u002D123456789abcdef123456789"}',
 '{"token":"opaque-private-value",',
 '{"instruction":"\\\"api_key\\\":\\\"opaque-private-value\\\"",',
])
def test_credential_patterns_are_rejected_without_echo_or_persistence(client,text):
 t=create(client);response=save(client,t,text);assert response.status_code==422
 assert text not in response.text and 'opaque-private-value' not in response.text and '123456789abcdef' not in response.text
 assert main.store.get('plan_draft',t['id']) is None

@pytest.mark.parametrize('text',['','  ','😀'*500001,'{"a":"\ud800"}'],ids=['empty','whitespace','utf8_byte_limit','invalid_unicode'])
def test_byte_and_unicode_limits_return_clear_errors_without_persisting(client,text):
 t=create(client)
 # Encode invalid Unicode as JSON escape, so the server receives the bad string.
 body=json.dumps({'revision':t['revision'],'draft_revision':0,'text':text},ensure_ascii=True)
 response=client.put(endpoint(t),content=body,headers={'Content-Type':'application/json'});assert response.status_code==422
 assert main.store.get('plan_draft',t['id']) is None

def test_ordinary_budget_field_names_and_unicode_are_retained(client):
 t=create(client);text='{"max_tokens":2000,"document_token":"not-a-credential-hash","instructions":"密码重置说明 😀"}'
 assert save(client,t,text).json()['record']['text']==text

def test_structural_limits_refuse_complete_oversized_json_without_claiming_secret(client):
 t=create(client);value={};root=value
 for _ in range(62):root['next']={};root=root['next']
 response=save(client,t,json.dumps(value));assert response.status_code==422 and '结构检查上限' in response.json()['detail']

def test_foreign_or_missing_task_is_not_created_and_failure_keeps_previous_draft(client):
 t=create(client);save(client,t,'safe old draft')
 assert client.get('/api/tasks/unknown/plan-draft').status_code==404
 assert client.put('/api/tasks/unknown/plan-draft',json={'revision':1,'draft_revision':0,'text':'safe text'}).status_code==404
 assert save(client,t,'sk-123456789abcdef123456789',1).status_code==422
 assert client.get(endpoint(t)).json()['record']['text']=='safe old draft'

def test_validation_errors_never_echo_malformed_draft_credentials(client):
 t=create(client);private='opaque-private-value'
 for patch in ({'revision':private},{'text':{'api_key':private}},{'unexpected':private}):
  response=save(client,t,**patch);assert response.status_code==422 and private not in response.text

def test_confirmations_artifacts_and_budgets_stay_unchanged(client):
 t=approved(client);before=copy.deepcopy(main.get_task(t['id']));budget=client.get(f"/api/tasks/{t['id']}/budget").json()
 assert save(client,t).status_code==200
 assert main.get_task(t['id'])==before and main.get_task(t['id'])['configuration_confirmed']
 assert client.get(f"/api/tasks/{t['id']}/budget").json()==budget
