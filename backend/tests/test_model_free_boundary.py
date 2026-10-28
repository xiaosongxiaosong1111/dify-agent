import importlib.util,sys
from pathlib import Path
import httpx,pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/c1-planning365'))
spec=importlib.util.spec_from_file_location('model_free_boundary',ROOT/'tools/c1-model-free368/boundary.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def boundary(phase='reconnect'):
    return module.ModelFreeBoundary({'base_url':'https://public-dify.invalid'},{'base_url':'https://api.deepseek.com','model':'deepseek-flash'},{},{'phase':phase},[])


@pytest.mark.parametrize('url',['https://api.deepseek.com/chat/completions','https://other.invalid/console/api/apps'])
def test_no_provider_or_foreign_request_can_dispatch(url):
    b=boundary()
    with pytest.raises(RuntimeError):b.admit(httpx.Request('POST',url,json={}))
    assert sum(b.counts.values())==0


def test_read_limit_rejects_before_counting_an_extra_dispatch():
    b=boundary();request=httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1')
    for _ in range(28):b.admit(request)
    with pytest.raises(RuntimeError):b.admit(request)
    assert b.counts['reads']==28 and b.counts['model']==0


def test_model_is_forbidden_even_with_a_colocated_provider_and_forged_pending_call():
    from guard import digest
    b=boundary();b.provider['base_url']=b.env['base_url'];b.record['model_requests']=[{'phase':'forged'}]
    b.model_pending={'messages_sha256':digest([])}
    request=httpx.Request('POST',b.env['base_url']+'/chat/completions',json={'model':'deepseek-flash','max_tokens':6000,'stream':False,'messages':[],'thinking':{'type':'disabled'}})
    with pytest.raises(RuntimeError):b.admit(request)
    assert b.counts['model']==0 and b.record['dispatches']==[]


@pytest.mark.parametrize('kind,phase,path,cap',[
    ('login','reconnect','/console/api/login',1),('import','modified_import','/console/api/apps/imports',1),
    ('publish','modified_publish','/console/api/apps/public-app/workflows/publish',1),
    ('key','modified_key','/console/api/apps/public-app/api-keys',1),('run','modified_hit','/v1/workflows/run',2),
])
def test_tighter_remaining_caps_do_not_increment_rejected_calls(kind,phase,path,cap):
    b=boundary(phase);b.counts[kind]=cap
    with pytest.raises(RuntimeError):b.admit(httpx.Request('POST','https://public-dify.invalid'+path,json={}))
    assert b.counts[kind]==cap


@pytest.mark.parametrize('phase',['first_plan','changed_plan','original_import','original_hit'])
def test_consumed_original_or_model_phases_cannot_be_used(phase):
    b=boundary(phase)
    with pytest.raises(RuntimeError):b.admit(httpx.Request('GET','https://public-dify.invalid/console/api/apps?page=1&limit=1'))
    assert sum(b.counts.values())==0
