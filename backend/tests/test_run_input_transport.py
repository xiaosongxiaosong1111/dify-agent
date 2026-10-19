import json
import pytest
from fastapi import FastAPI,APIRouter
from fastapi.testclient import TestClient
from test_api import client
from app.run_input_transport import validate,AmbiguousInput,RunInputRoute
from app import main

@pytest.mark.parametrize('raw',[
 b'{"revision":1,"revision":2}',b'{"revision":1,"input":{"query":"first","query":"second"}}',
 b'{"revision":1,"input":{"\\u0071uery":"first","query":"second"}}',b'{"input":{"rows":[{"x":1,"x":2}]}}',
 b'{"input":{"x":NaN}}',b'{"input":{"x":Infinity}}',b'{"input":{"x":1e400}}',
 b'{"input":{"x":1e-999}}',b'{"input":{"x":1.0000000000000001}}',b'{"input":{"x":0.10000000000000001}}',
 b'{"input":{"x":"\\ud800"}}',b'{"\\ud800":"value"}',b'\xff',b'{',b'[]',b'null',
],ids=[f'b{i}' for i in range(16)])
def test_ambiguous_json_rejected_without_echo(raw):
 with pytest.raises(AmbiguousInput) as error:validate(raw)
 assert 'first' not in str(error.value) and 'second' not in str(error.value)

@pytest.mark.parametrize('raw',[
 b'{}',b'{"a":{"same":1},"b":{"same":2}}',b'{"rows":[{"same":1},{"same":2}]}',
 b'{"text":"{\\\"same\\\":1,\\\"same\\\":2}"}',b'{"__proto__":{"x":1},"constructor":2}',
 b'{"input":{"x":9007199254740993}}',b'{"input":{"x":1.5000,"y":0.1,"z":5e-324}}',
],ids=[f'v{i}' for i in range(7)])
def test_unambiguous_json_unchanged(raw):
 assert validate(raw)==json.loads(raw)

def test_size_and_value_bounds_no_partial_input():
 with pytest.raises(AmbiguousInput):validate(b' '*8000001)
 with pytest.raises(AmbiguousInput):validate(json.dumps({'input':list(range(100001))}).encode())

@pytest.mark.parametrize('path',['run','run-input-check','run-case-input-check'])
@pytest.mark.parametrize('raw',[b'{"revision":1,"revision":2}',b'{"revision":1,"input":{"query":"one","query":"two"}}',b'{"revision":1,"input":{"n":1e-999}}'])
def test_all_three_real_routes_stop_before_task_or_resources(client,monkeypatch,path,raw):
 def forbidden(*a,**kw):pytest.fail('Malformed transport must stop before task/credentials/resources')
 monkeypatch.setattr(main,'get_task',forbidden)
 response=client.post('/api/tasks/public-missing/'+path,content=raw,headers={'Content-Type':'application/json'})
 assert response.status_code==422 and isinstance(response.json()['detail'],str)
 assert 'one' not in response.text and 'two' not in response.text

@pytest.mark.parametrize('payload',[
 {'revision':True,'input':{'query':'PRIVATE-INPUT'}}, {'revision':'1','input':{'query':'PRIVATE-INPUT'}},
 {'revision':0,'input':{'query':'PRIVATE-INPUT'}}, {'revision':1,'unexpected':'PRIVATE-INPUT'},
 {'revision':1,'input':['PRIVATE-INPUT']},
])
def test_run_request_strict_revision_shape_and_no_validation_echo(client,monkeypatch,payload):
 def forbidden(*a,**kw):pytest.fail('Invalid request must stop before task lookup')
 monkeypatch.setattr(main,'get_task',forbidden)
 response=client.post('/api/tasks/public-missing/run',json=payload)
 assert response.status_code==422 and 'PRIVATE-INPUT' not in response.text

def test_valid_wire_reaches_handler_without_mutating_large_integer():
 app=FastAPI();router=APIRouter(route_class=RunInputRoute);seen=[]
 @router.post('/run')
 def receive(payload:main.RunRequest):seen.append(payload);return {'accepted':True}
 app.include_router(router)
 with TestClient(app) as local:
  response=local.post('/run',content=b'{"revision":1,"input":{"n":9007199254740993,"query":"public"}}',headers={'Content-Type':'application/json'})
 assert response.status_code==200 and len(seen)==1
 assert seen[0].input['n']==9007199254740993 and type(seen[0].input['n']) is int
