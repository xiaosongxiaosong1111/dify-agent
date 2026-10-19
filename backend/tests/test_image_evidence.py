import json
from test_api import client
from test_image_review_drafts import ready,url,payload
from test_image_execution import route,RESULT
from app import main
from app.image_evidence import summary


def test_delivery_trace_binds_adopted_text_and_excludes_candidate_or_review_drafts(client,monkeypatch):
    t,m,r=ready(client,monkeypatch);client.put(url(t,m,r),json=payload(t,m,text='private-unadopted-review'))
    empty=summary(main,main.get_task(t['id']));assert empty['materials']==[]
    response=client.post(route(t,m,'adopt'),json={'revision':t['revision'],'plan_id':r['id'],'candidate_token':r['candidate_token'],'text':'采用的人工作品','coverage_note':'只覆盖左侧','acknowledge_review':True,'acknowledge_uncertainties':True});assert response.status_code==200
    evidence=summary(main,response.json());item=evidence['materials'][0]
    assert item['source_record_matched'] and item['source_sha256']==m['sha256'] and item['provider']['model']=='fixture-vision' and item['human_review_acknowledged']
    assert item['applied_revision']==t['revision']+1 and item['uncertainties']==RESULT['uncertainties']
    public=json.dumps(evidence,ensure_ascii=False);assert 'private-unadopted-review' not in public and RESULT['transcription'] not in public and 'test-only-image-key' not in public and 'data:image' not in public and '_provider_stamp' not in public
    report=client.get(f"/api/tasks/{t['id']}/report");assert report.status_code==200,report.text
    assert '已采用图像文字来源链' in report.text and m['sha256'] in report.text and 'fixture-vision' in report.text
    record=main.store.get('image_preview',r['id']);record['task_id']='foreign';main.store.put('image_preview',r['id'],record)
    unmatched=summary(main,response.json())['materials'][0];assert not unmatched['source_record_matched'] and 'provider' not in unmatched and '来源链完整' in unmatched['note']
