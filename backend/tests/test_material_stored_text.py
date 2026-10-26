import copy,hashlib,json
import pytest
from test_api import client,create,forbid_api_external_calls
from app import main
from app.material_stored_text import MAX_BYTES,entry

def setup(client):
    task=create(client);task['materials']=[{'id':'public-material','name':'公开说明.pdf','sha256':'a'*64,'status':'needs_input','text':'','partial_text':('公开\r\n🙂片段'*1700),'extraction_coverage':{'format':'pdf','scope_note':'只有前两页可提取，其余未知'},'reference_mode':'borrow'}]
    main.save_task(task);return main.get_task(task['id'])

def request(client,task,meta=None,**extra):
    material=task['materials'][0]
    return client.post(f"/api/tasks/{task['id']}/materials/{material['id']}/stored-text/{'page' if extra else 'index'}",json={'revision':task['revision'],'source_sha256':material['sha256'],'source_token':meta['source_token'] if meta else None,**extra})

def test_projection_and_all_pages_preserve_exact_body_and_do_not_write(client,monkeypatch):
    task=setup(client);before=main.store.get('task',task['id'])
    monkeypatch.setattr(main.store,'put',lambda *a,**k:pytest.fail('不得保存'))
    monkeypatch.setattr(main.store,'secret',lambda *a,**k:pytest.fail('不得解密'))
    response=client.get(f"/api/tasks/{task['id']}?workspace_view=compact-v2");assert response.status_code==200,response.text
    value=response.json();material=value['materials'][0];meta=material['text_view']
    assert 'text' not in material and 'partial_text' not in material and value['workspace_view']['schema_version']==2
    assert meta['entries']['text']['state']=='empty' and meta['entries']['partial_text']['state']=='available'
    assert meta['source_metadata']['source_file_parsed'] is False and meta['original_file_rechecked'] is False
    parts=[]
    for offset in range(0,len(task['materials'][0]['partial_text']),4000):
        response=request(client,task,meta,field='partial_text',offset=offset);assert response.status_code==200,response.text
        page=response.json();parts.append(page['content_chunk']);assert page['page_start']==offset and page['page_end']==offset+len(parts[-1])
        assert page['partial_extraction'] is True and page['page_sha256']==hashlib.sha256(parts[-1].encode()).hexdigest()
        assert page['source_token']==meta['source_token'] and response.headers['cache-control']=='no-store'
    assert ''.join(parts)==task['materials'][0]['partial_text']
    assert main.store.get('task',task['id'])==before
    for query in ['', '?workspace_view=compact','?message_window=recent']:
        assert client.get('/api/tasks/'+task['id']+query).json()['materials'][0]['partial_text']==''.join(parts)

@pytest.mark.parametrize('key,value',[('text','变更正文'),('partial_text','变更片段'),('status','parsed'),('sha256','b'*64),('reference_mode','replicate'),('preserve_items','节点'),('source_kind','user_supplied_text'),('extraction_coverage',{'format':'pdf','scope_note':'不同覆盖'})])
def test_identity_changes_reject_old_page_even_at_same_revision(client,key,value):
    task=setup(client);meta=request(client,task).json();changed=copy.deepcopy(task);changed['materials'][0][key]=value;main.save_task(changed)
    response=request(client,task,meta,field='partial_text',offset=0);assert response.status_code==409

def test_append_allowed_but_revision_foreign_material_and_foreign_task_rejected(client):
    task=setup(client);meta=request(client,task).json();task['messages'].append({'role':'user','content':'追加'});main.save_task(task)
    assert request(client,task,meta,field='partial_text',offset=0).status_code==200
    other=setup(client);assert request(client,other,meta,field='partial_text',offset=0).status_code==409
    task['revision']+=1;main.save_task(task);task['revision']-=1
    assert request(client,task,meta,field='partial_text',offset=0).status_code==409

@pytest.mark.parametrize('extra',[{'field':[], 'offset':0},{'field':'unknown','offset':0},{'field':'partial_text','offset':True},{'field':'partial_text','offset':-1},{'field':'partial_text','offset':999999}])
def test_strict_page_request(client,extra):
    task=setup(client);meta=request(client,task).json();assert request(client,task,meta,**extra).status_code==422

def test_size_encoding_and_empty_fields_are_not_silent_truncation():
    assert entry('x'*MAX_BYTES)['state']=='available'
    assert entry('x'*(MAX_BYTES+1))['state']=='oversized'
    assert entry('🙂'*(MAX_BYTES//4+1))['state']=='oversized'
    assert entry('bad\ud800')['state']=='unavailable'
    assert entry(None)['state']=='missing' and entry('')['state']=='empty' and entry(3)['state']=='unavailable'

def test_manual_body_and_original_partial_keep_separate_provenance(client):
    task=setup(client);task['materials'][0].update(status='parsed',source_kind='user_supplied_text',text='用户后补正文',source_coverage_note='只描述公开退货问题');main.save_task(task)
    meta=request(client,task).json();assert meta['source_metadata']['source_kind']=='user_supplied_text' and not meta['source_metadata']['source_file_parsed']
    body=request(client,task,meta,field='text',offset=0).json();partial=request(client,task,meta,field='partial_text',offset=0).json()
    assert not body['partial_extraction'] and body['complete_field'] and partial['partial_extraction']
    assert '原解析片段不当作当前已采用正文' in partial['note']

def test_duplicate_ids_and_oversized_page_refuse_without_modifying_source(client):
    task=setup(client);task['materials'][0]['text']='x'*(MAX_BYTES+1);main.save_task(task);meta=request(client,task).json()
    assert request(client,task,meta,field='text',offset=0).status_code==413
    assert request(client,task,None,field='partial_text',offset=0).status_code==422
    task['materials'].append(copy.deepcopy(task['materials'][0]));main.save_task(task)
    assert client.get(f"/api/tasks/{task['id']}?workspace_view=compact-v2").status_code==409
    assert request(client,task).status_code==409

def test_strict_json_and_task_source_retained(client):
    task=setup(client);before=main.store.get('task',task['id']);path=f"/api/tasks/{task['id']}/materials/public-material/stored-text/index"
    for body in ['{"revision":1,"revision":2}', '{"revision":NaN}', 'x'*8193]:
        assert client.post(path,content=body,headers={'content-type':'application/json'}).status_code in {413,422}
    assert main.store.get('task',task['id'])==before

@pytest.mark.parametrize('kind',['user_supplied_text','reviewed_model_image_text','file_text_parser'])
def test_source_kinds_retained_without_original_file_inspection(client,monkeypatch,kind):
    from app import material_sources
    monkeypatch.setattr(material_sources,'read_source',lambda *a,**k:pytest.fail('不能重读原件'))
    task=setup(client);task['materials'][0].update(status='parsed',source_kind=kind,text='公开文字',source_coverage_note='范围有限',image_model_response_received=kind=='reviewed_model_image_text',image_uncertainties=['小字未知'] if kind=='reviewed_model_image_text' else []);main.save_task(task)
    meta=request(client,task).json();assert meta['source_metadata']['source_kind']==kind
    assert meta['source_metadata']['source_file_parsed']==(kind=='file_text_parser')
    assert request(client,task,meta,field='text',offset=0).json()['original_file_rechecked'] is False
    second=copy.deepcopy(task['materials'][0]);second['id']='second-material';task['materials'].append(second);main.save_task(task)
    path=f"/api/tasks/{task['id']}/materials/second-material/stored-text/page"
    assert client.post(path,json={'revision':task['revision'],'source_sha256':second['sha256'],'source_token':meta['source_token'],'field':'text','offset':0}).status_code==409
