import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest,copy
from app.http_body import validate
from app.workflow_plan import validate_plan,compile_workflow_plan
from test_preservation_extensions import http_plan,native
from test_aggregation import task
from app.dsl_roundtrip import validate_preserved,load_document
import yaml


@pytest.mark.parametrize('body',[
 {'type':'none','data':[{'type':'text','value':'should-send'}]},
 {'type':'json','data':[{'type':'text','key':'ignored','value':'{}'}]},
 {'type':'json','data':[{'value':'{}'}]},
 {'type':'raw-text','data':[]},
 {'type':'raw-text','data':[{'type':'text','value':'first'},{'type':'text','value':'second'}]},
 {'type':'json','data':[{'type':'text','value':'{"x":1,"x":2}'}]},
 {'type':'json','data':[{'type':'text','value':'{"password":"PRIVATE"}'}]},
 {'type':'json','data':[{'type':'text','value':'{"password":{{#start.query#}}}'}]},
 {'type':'json','data':[{'type':'text','value':'{password: {{#start.query#}}}'}]},
 {'type':'json','data':[{'type':'text','value':'{"x":1e1000}'}]},
 {'type':'json','data':[{'type':'text','value':'[NaN]'}]},
 {'type':'form-data','data':[{'type':'text','key':'x','value':'a'},{'type':'text','key':'x','value':'b'}]},
 {'type':'form-data','data':[{'type':'file','key':'upload','file':['start','files']}]},
 {'type':'binary','data':[{'type':'file','file':['start','files']}]},
 {'type':'raw-text','data':[{'type':'text','value_selector':['start','query']}]},
])
def test_ignored_ambiguous_or_unsupported_body_blocks_plan_and_build(body):
    p=http_plan();p['nodes'][1]['config']['body']=body
    r=validate_plan(task(),p);assert not r['valid']
    assert not compile_workflow_plan({**task(),'workflow_plan':p})[0]
    assert all('PRIVATE' not in e for e in r['errors'])


def test_valid_literal_json_and_legacy_text_string_preserved_without_repair():
    for body in ({'type':'json','data':[{'type':'text','key':'','value':'{"query":"hello","enabled":false,"count":0}'}]}, {'type':'raw-text','data':'legacy text'}, {'type':'form-data','data':[{'type':'text','key':'query','value':'hello'}]}):
        p=http_plan();p['nodes'][1]['config']['body']=body;root=native(p);before=copy.deepcopy(root)
        assert validate_preserved(root)['valid'] and root==before


def test_dynamic_json_is_not_claimed_serialization_verified():
    errors,warnings=validate({'type':'json','data':[{'type':'text','value':'{"query":"{{#start.query#}}"}'}]})
    assert not errors and any('最终转义' in w for w in warnings)


def test_malformed_type_and_too_deep_literal_return_error_not_exception():
    assert validate({'type':[],'data':[]})[0]
    assert validate({'type':'json','data':[{'type':'text','value':'['*2000+'0'+']'*2000}]})[0]


def test_secret_json_string_and_ambiguous_literal_cannot_enter_reference_store():
    for value in ('{"password":"PRIVATE"}','{"api_key":"PRIVATE"}','{password: "PRIVATE"}'):
        root=native(http_plan());data=next(n['data'] for n in root['workflow']['graph']['nodes'] if n['id']=='http')
        data['body']={'type':'json','data':[{'type':'text','value':value}]}
        with pytest.raises(ValueError) as raised:load_document(yaml.safe_dump(root,allow_unicode=True))
        assert 'PRIVATE' not in str(raised.value)


def test_unencodable_strings_and_escaped_json_surrogates_are_field_errors():
    for body in ({'type':'raw-text','data':[{'type':'text','value':'\ud800'}]}, {'type':'form-data','data':[{'type':'text','key':'\ud800','value':'a'}]}, {'type':'json','data':[{'type':'text','value':'{"x":"\\ud800"}'}]}, {'type':'json','data':[{'type':'text','value':'{"\\ud800":"x"}'}]}):
        errors,_=validate(body);assert errors and any('Unicode' in e for e in errors)
    assert not validate({'type':'json','data':[{'type':'text','value':'{"x":"\\ud83d\\ude00"}'}]})[0]


def test_known_secret_looking_raw_body_is_rejected_before_export():
    p=http_plan();secret='sk-'+'x'*32;p['nodes'][1]['config']['body']={'type':'raw-text','data':[{'type':'text','value':secret}]}
    content,result=compile_workflow_plan({**task(),'workflow_plan':p});assert not content and not result['valid']
    assert any('明文密钥' in e for e in result['errors']) and all(secret not in e for e in result['errors'])
    errors,_=validate({'type':'json','data':[{'type':'text','value':'"\\u0073k-'+'x'*32+'"'}]});assert errors and any('明文密钥' in e for e in errors)
