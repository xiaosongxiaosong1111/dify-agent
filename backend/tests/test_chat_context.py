import copy,hashlib,json,uuid
import pytest
from test_api import client,create,forbid_api_external_calls
from test_interview_progress import configured
from app import main
from app.intake import model_sources


def long_task():
    return {'revision':4,'requirements':{k:'公开要求'+('规则'*3000) for k in main.REQ_KEYS},'materials':[],
            'messages':[{'role':'user' if i%2==0 else 'assistant','content':f'原话{i}：'+('公开文字🙂'*2000),'context_revision':4} for i in range(16)]+[{'role':'user','content':'本次完整原话'+('新规则🙂'*3000),'context_revision':4}]}


def test_latest_evidence_identity_survives_full_requirement_excerpt_budget():
    task=long_task();before=copy.deepcopy(task);value=model_sources(task)
    assert any(row['kind']=='message' and row['id']=='16' and row['text'].startswith('本次完整原话') for row in value)
    assert sum(len(row['text']) for row in value)<=24000 and task==before
    assert {row['id'] for row in value if row['kind']=='requirement'}==set(main.REQ_KEYS)


def test_explicit_compact_choice_keeps_current_user_and_binds_real_message_sources():
    from app.chat_context import assemble_history
    task=long_task();before=copy.deepcopy(task)
    messages,summary=assemble_history(task,compact=True)
    assert summary['mode']=='bounded_excerpts' and summary['history_text_characters']<=24000
    assert summary['current_user_message_complete'] and summary['truncated_count']+summary['omitted_count']>0
    assert task['messages'][-1]['content'] in messages[-1]['content']
    current=summary['entries'][-1];assert current['source_id']=='16' and current['excerpt_truncated'] is False
    assert current['source_sha256']==hashlib.sha256(task['messages'][-1]['content'].encode()).hexdigest()
    assert 'message:16' in messages[-1]['content'] and task==before
    assert '本次完整原话' not in json.dumps(summary,ensure_ascii=False)


def test_default_recent_history_is_not_silently_truncated():
    from app.chat_context import assemble_history
    task=long_task();messages,summary=assemble_history(task,compact=False)
    assert summary['mode']=='recent_full' and summary['history_text_characters']>24000
    assert summary['truncated_count']==0 and summary['omitted_count']==0 and len(messages)==12
    assert all(row['included_length']==row['full_length'] for row in summary['entries'])


def test_discussion_and_assistant_records_are_never_labelled_requirement_evidence():
    from app.chat_context import assemble_history
    task={'revision':3,'messages':[{'role':'user','purpose':'discussion','content':'只讨论规则'},{'role':'assistant','content':'助手建议'},{'role':'system','content':'系统记录'},{'role':'user','content':'本次明确原话','context_revision':3}]}
    messages,summary=assemble_history(task,compact=True)
    assert messages[0]['content'].startswith('【只读讨论记录，未作为需求或批准】')
    assert [r['source_id'] for r in summary['entries']]==[None,None,'3']
    assert 'message:0' not in messages[0]['content'] and 'message:1' not in messages[1]['content']
    assert 'message:3' in messages[2]['content']


def test_actual_request_records_summary_without_storing_prompt_or_losing_current_requirements(client,monkeypatch):
    task,_=configured(client);long=long_task();task['requirements']=long['requirements'];task['messages']=long['messages'][:-1];main.save_task(task);calls=[]
    async def model(provider,key,messages,**kwargs):
        calls.append(messages);current=main.get_task(task['id']);record=main.store.get('interview_operation',current['active_interview_id']);summary=record['context_summary']
        assert summary['mode']=='bounded_excerpts' and summary['history_text_characters']<=24000
        assert '本次完整原话' in messages[-1]['content'] and '需求证据ID message:16' in messages[-1]['content']
        context=json.loads(messages[1]['content'].split('当前任务资料：',1)[1]);assert context['requirements']==task['requirements']
        assert any(x['kind']=='message' and x['id']=='16' for x in context['intake_sources'])
        assert '本次完整原话' not in json.dumps(summary,ensure_ascii=False)
        return json.dumps({'message':'本机隔离回复','requirements_patch':{}}),{'prompt_tokens':10,'completion_tokens':5}
    monkeypatch.setattr(main,'call_model',model)
    value={'request_id':str(uuid.uuid4()),'revision':task['revision'],'content':long['messages'][-1]['content'],'compact_history':True}
    response=client.post(f"/api/tasks/{task['id']}/messages",json=value);assert response.status_code==200,response.text
    assert len(calls)==1
    assert client.post(f"/api/tasks/{task['id']}/messages",json=value).status_code==200 and len(calls)==1
    assert client.post(f"/api/tasks/{task['id']}/messages",json={**value,'compact_history':False}).status_code==409


def test_false_compact_option_keeps_previous_request_fingerprint_compatible():
    from app.message_requests import fingerprint
    value={'request_id':str(uuid.uuid4()),'revision':2,'content':'旧协议公开请求','mode':'discussion','stream_response':False}
    expected=hashlib.sha256(json.dumps({k:v for k,v in value.items() if k!='request_id'},ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    assert fingerprint(main.Message(**value))==expected
    assert fingerprint(main.Message(**value,compact_history=False))==expected
    assert fingerprint(main.Message(**value,compact_history=True))!=expected


def test_compact_option_must_be_boolean_and_does_not_mutate_on_invalid_request(client):
    task=create(client);before=copy.deepcopy(main.store.get('task',task['id']))
    response=client.post(f"/api/tasks/{task['id']}/messages",json={'content':'公开请求','compact_history':'true'})
    assert response.status_code==422 and main.store.get('task',task['id'])==before
