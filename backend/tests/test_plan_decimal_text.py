import copy,json
import pytest
from test_api import client,create,forbid_api_external_calls
from test_file_structured_run import shape
from test_file_model_run import MODEL
from app import main
from app.file_structured_template import template
from app.plan_text_codec import parse,render

def source(number):
    value=template(json.dumps(shape()),['.txt']);value['nodes'][2]['config']['model']=copy.deepcopy(MODEL)
    return json.dumps(value,ensure_ascii=False).replace('"temperature": 0.3','"temperature": '+number)

@pytest.mark.parametrize('number',['0.10000000000000001','1e-999','0.2999999999999999999999'])
def test_decimal_loss_rejected_before_save_or_preview(client,number):
    task=create(client);before=copy.deepcopy(main.get_task(task['id']));text=source(number)
    for suffix in ['/plan','/plan/change-preview']:
        response=client.post('/api/tasks/'+task['id']+suffix,json={'revision':task['revision'],'plan_text':text})
        assert response.status_code==422,response.text[:300]
        assert main.get_task(task['id'])==before

@pytest.mark.parametrize('raw,expected',[('0.2',0.2),('1e3',1000.0),('1.2500',1.25),('0e999',0.0),('-0.0',-0.0)])
def test_finite_wire_equivalent_decimals_still_accepted(raw,expected):
    assert parse('{"value":'+raw+'}')['value']==expected
    integer=900719925474099312345678901;assert parse(render({'n':integer}))['n']==integer

def test_exact_decimal_plan_still_saves_and_preserves_quote_text(client):
    task=create(client);response=client.post('/api/tasks/'+task['id']+'/plan',json={'revision':task['revision'],'plan_text':source('0.2')});assert response.status_code==200,response.text
    value=response.json();assert parse(value['plan_text'])['nodes'][2]['config']['model']['completion_params']['temperature']==0.2
