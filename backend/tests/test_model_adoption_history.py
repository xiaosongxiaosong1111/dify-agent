import copy,sys,uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
from app.model_adoption_history import summarize
from app import main
from test_api import client
from test_agent_model_adoption import setup,adopt


def row(revision=3):
    return {'id':str(uuid.uuid4()),'revision':revision,'previous_revision':revision-1,
        'reference_id':str(uuid.uuid4()),'document_token':'a'*64,'configuration_sha256':'b'*64,
        'created_at':'2026-10-18T22:20:00.123456+00:00','source':'merged_dsl_preview_model',
        'verification':'local_configuration_only','pending_resource_review':True,
        'choices':{'private':'never-export-history-choice'},'configuration':{'secret':'never-export-history-config'}}


def test_whitelist_is_readonly_and_does_not_translate_historical_pending_into_current_state():
    data=[row()];before=copy.deepcopy(data);out=summarize(data)
    assert data==before and out['total']==1 and out['shown']==1
    assert set(out['rows'][0])=={'id','revision','previous_revision','reference_id','document_token','configuration_sha256','created_at','source','verification'}
    assert out['verification']=='local_adoption_history_only'
    assert 'pending_resource_review' not in out['rows'][0]
    assert 'never-export' not in str(out)
    out['rows'][0]['id']='changed';assert data==before


def test_last20_window_reports_total_and_does_not_pretend_to_validate_older_rows():
    data=[row(i) for i in range(2,27)];data[0]='uninspected corrupt history';data[-2]=None
    out=summarize(data);assert out['total']==25 and out['window_size']==20 and out['truncated']
    assert out['shown']==19 and out['invalid_in_window']==1
    assert out['rows'][0]['revision']==26 and out['rows'][-1]['revision']==7


@pytest.mark.parametrize('records',[None,{},True,'bad'])
def test_unreadable_array_does_not_masquerade_as_no_history(records):
    out=summarize(records);assert out['unavailable'] and out['total'] is None and out['rows']==[]


@pytest.mark.parametrize('key,value',[
    ('revision',True),('previous_revision',True),('revision',5),('previous_revision',0),
    ('id','not-a-uuid'),('reference_id','<script>'),('document_token','A'*64),
    ('configuration_sha256','bad'),('created_at','2026-10-18T22:20:00'),
    ('created_at','2026-10-18😀22:20:00+00:00'),('created_at','2026-10-18T22:20:00+00:00\n'),
    ('created_at','2026-02-30T22:20:00Z'),('source','dify_runtime'),
    ('verification','business_verified'),('pending_resource_review',1),
],ids=[f'bad{i}' for i in range(15)])
def test_invalid_metadata_counts_without_echoing_raw_data(key,value):
    rec=row();rec[key]=value;out=summarize([rec])
    assert out['total']==1 and out['invalid_in_window']==1 and out['shown']==0 and out['rows']==[]


def test_valid_timestamp_zone_variants_and_empty_history():
    records=[]
    for stamp in ('2026-10-18T22:20:00Z','2026-10-18T22:20:00+08:00','2026-10-18T22:20:00.1+00:00'):
        rec=row();rec['created_at']=stamp;records.append(rec)
    assert summarize(records)['shown']==3
    empty=summarize([]);assert empty['total']==0 and empty['shown']==0 and not empty['unavailable']


def test_actual_report_keeps_adoption_separate_from_platform_acceptance_and_does_not_echo_extras(client):
    task,current,p=setup(client);response=adopt(client,task,p);assert response.status_code==200
    task=response.json();task['model_configuration_adoptions'][0]['choices']={'private':'never-export-history-choice'}
    task['model_configuration_adoptions'][0]['configuration']={'secret':'never-export-history-config'}
    main.save_task(task);before=copy.deepcopy(main.get_task(task['id']))
    response=client.get(f"/api/tasks/{task['id']}/report");assert response.status_code==200,response.text
    text=response.text;assert '模型配置采用历史（本机元数据）' in text and 'local_adoption_history_only' in text
    assert 'never-export-history-choice' not in text and 'never-export-history-config' not in text
    assert '不从历史采用推断当前目标资源状态或业务通过' in text
    assert '当前修订尚无匹配的真实导入记录' in text and '原生 Agent 生成路径' in text
    assert main.get_task(task['id'])==before


def test_corrupt_history_is_explicit_in_report_without_dropping_task_or_reference(client):
    task,current,p=setup(client);task['model_configuration_adoptions']=None;main.save_task(task)
    response=client.get(f"/api/tasks/{task['id']}/report");assert response.status_code==200
    section=response.text.split('## 模型配置采用历史（本机元数据）')[1].split('## Dify 试跑用量')[0]
    assert '"unavailable": true' in section and '"total": null' in section
    assert main.get_task(task['id'])['dsl_reference']['id']==p['reference_id']
