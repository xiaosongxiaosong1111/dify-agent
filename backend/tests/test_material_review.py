import copy,json,hashlib
import pytest
from test_api import client,create,forbid_api_external_calls
from test_material_parsing import upload
from test_conflicts import prepared,review,save
from app import main


def read(client,task):
    response=client.get(f"/api/tasks/{task['id']}/material-review",params={'revision':task['revision']})
    assert response.status_code==200,response.text
    return response.json()


def test_exact_byte_duplicates_and_current_text_duplicates_are_separate(client):
    task=create(client);task,a=upload(client,task,'one.txt',b'public text');task,b=upload(client,task,'two.txt',b'public text')
    result=read(client,task)
    assert result['original_digest_duplicates']==result['exact_text_duplicates']==[{'material_ids':[a['id'],b['id']]}]
    assert not result['same_name_different_content'] and not result['original_files_rechecked'] and not result['semantic_conflicts_checked']
    assert result['unconfirmed_reference_count']==2 and result['conflicts']['state']=='not_enabled'


def test_decoded_text_can_match_while_original_file_bytes_differ(client):
    task=create(client);task,a=upload(client,task,'one.txt',b'public');task,b=upload(client,task,'two.txt',b'\xef\xbb\xbfpublic')
    result=read(client,task)
    assert not result['original_digest_duplicates'] and result['exact_text_duplicates']==[{'material_ids':[a['id'],b['id']]}]


def test_same_name_different_content_is_a_clue_not_an_automatic_version_choice(client):
    task=create(client);task,a=upload(client,task,'Rules.txt',b'rule: seven days');task,b=upload(client,task,'rules.TXT',b'rule: thirty days')
    before=copy.deepcopy(task);result=read(client,task)
    assert result['same_name_different_content']==[{'material_ids':[a['id'],b['id']]}]
    assert not result['original_digest_duplicates'] and not result['exact_text_duplicates']
    assert main.get_task(task['id'])==before and not result['conflicts']['unresolved_count']
    assert '正确版本' in result['note'] and 'newest' not in json.dumps(result)


def test_same_name_identical_file_is_not_a_different_version(client):
    task=create(client);task,_=upload(client,task,'rules.txt',b'same');task,_=upload(client,task,'rules.txt',b'same')
    result=read(client,task);assert len(result['original_digest_duplicates'])==1 and not result['same_name_different_content']


def test_needs_input_partial_text_does_not_become_readable_or_text_duplicate(client):
    task=create(client);task,a=upload(client,task,'bad.json',b'{"private-body-marker": [}');task,b=upload(client,task,'bad2.json',b'{"private-body-marker": [}')
    task['materials'][0]['partial_text']='private-partial-marker';main.store.put('task',task['id'],task)
    result=read(client,task)
    assert len(result['original_digest_duplicates'])==1 and not result['exact_text_duplicates'] and result['needs_text_count']==2
    assert 'private-body-marker' not in json.dumps(result) and 'private-partial-marker' not in json.dumps(result)


def test_manual_text_duplicate_does_not_imply_same_original_file(client):
    task=create(client)
    for name,raw in [('one.png',b'one'),('two.png',b'two')]:
        task,m=upload(client,task,name,raw)
        response=client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/text",json={'revision':task['revision'],'source_sha256':m['sha256'],'text':'公开的人工文字','coverage_note':'用户自己的说明，原图未解析','acknowledge_manual_source':True})
        assert response.status_code==200;task=response.json()
    result=read(client,task)
    assert not result['original_digest_duplicates'] and len(result['exact_text_duplicates'])==1
    assert all(r['text_source']=='user_supplied_text' for r in result['records'])


def test_json_semantic_equivalence_is_not_claimed_as_exact_text_duplicate(client):
    task=create(client);task,_=upload(client,task,'one.json',b'{"a":1}');task,_=upload(client,task,'two.json',b'{ "a": 1 }')
    result=read(client,task);assert not result['exact_text_duplicates'] and not result['original_digest_duplicates']


def test_unknown_digest_and_inconsistent_legacy_text_are_not_assumed_equal(client):
    task=create(client);task['materials']=[{'id':'a','name':'same.txt','status':'needs_input','sha256':'bad','text':''},{'id':'b','name':'same.txt','status':'parsed','sha256':None,'text':7}]
    main.store.put('task',task['id'],task);result=read(client,task)
    assert result['unknown_digest_count']==2 and result['needs_text_count']==2
    assert not result['original_digest_duplicates'] and not result['same_name_different_content']


def test_inspection_is_readonly_and_never_decrypts_or_calls_models(client,monkeypatch):
    task=create(client);task,_=upload(client,task,'public.txt',b'private-text-marker')
    before=copy.deepcopy(main.get_task(task['id']))
    def forbidden(*a,**kw):raise AssertionError('read-only inspection must not write or decrypt')
    monkeypatch.setattr(main.store,'secret',forbidden);monkeypatch.setattr(main.store,'put',forbidden);monkeypatch.setattr(main.store,'put_many',forbidden)
    result=read(client,task);assert main.get_task(task['id'])==before and 'private-text-marker' not in json.dumps(result)
    assert len(result['snapshot_hash'])==64


def test_different_task_materials_are_never_joined_and_stale_revision_refuses(client):
    task=create(client);task,_=upload(client,task,'one.txt',b'same');other=create(client);other,_=upload(client,other,'one.txt',b'same')
    assert not read(client,task)['original_digest_duplicates']
    assert client.get(f"/api/tasks/{task['id']}/material-review",params={'revision':task['revision']-1}).status_code==409
    assert client.get('/api/tasks/missing/material-review',params={'revision':1}).status_code==404


def test_existing_unresolved_business_conflicts_stay_separate_and_unconfirmed(client):
    task=prepared(client);response=save(client,task,review(task));assert response.status_code==200;task=response.json()
    before=copy.deepcopy(task);result=read(client,task)
    assert result['conflicts']['state']=='needs_review' and result['conflicts']['unresolved_count']==1
    assert not result['original_digest_duplicates'] and main.get_task(task['id'])==before


def test_bounded_report_does_not_claim_to_cover_hidden_materials(client):
    task=create(client);task['materials']=[{'id':str(i),'name':str(i)+'.txt','status':'parsed','reference_mode':'borrow','text':str(i),'sha256':hashlib.sha256(str(i).encode()).hexdigest()} for i in range(101)]
    task['materials'][-1]['sha256']=task['materials'][0]['sha256'];main.store.put('task',task['id'],task)
    result=read(client,task)
    assert result['truncated'] and result['shown']==100 and result['material_total']==101
    assert not result['original_digest_duplicates'] and result['limit']==100
