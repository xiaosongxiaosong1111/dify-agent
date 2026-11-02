import copy
import pytest
from test_api import client,approved
from test_image_messages import png
from app import main


def setup(client):
    task=approved(client);task=client.post(f"/api/tasks/{task['id']}/materials",files={'file':('图像.png',png(),'image/png')}).json();material=task['materials'][-1]
    provider=client.post('/api/providers',json={'name':'隔离识图服务','provider':'custom','role':'vision','protocol':'openai-compatible','model':'fixture-vision','base_url':'https://example.test/v1','api_key':'test-only-image-key','pricing':{'input_per_million_usd':1,'output_per_million_usd':2}}).json()
    return task,material,provider


def prepare(client,task,m,p,**patch):
    return client.post(f"/api/tasks/{task['id']}/materials/{m['id']}/image-interpretation/prepare",json={'revision':task['revision'],'source_sha256':m['sha256'],'provider_id':p['id'],'instruction':'读取可见文字与连接，不确定之处明确说明','image_reserve_usd':'.25',**patch})


def test_prepare_freezes_safe_preview_without_model_or_task_changes(client,monkeypatch):
    t,m,p=setup(client);before=main.get_task(t['id'])
    async def forbidden(*args,**kwargs):raise AssertionError('preview must not dispatch')
    monkeypatch.setattr(main,'call_model',forbidden)
    response=prepare(client,t,m,p);assert response.status_code==200,response.text
    value=response.json();record=value['record']
    assert value['can_execute'] and value['preflight_blocker'] is None
    assert record['source']['sha256']==m['sha256'] and record['source']['width']==1
    assert record['provider']['role']=='vision' and record['image_reserve_usd']=='0.25'
    assert record['output_limit']==4000 and record['timeout_seconds']==120
    assert all(not key.startswith('_') for key in record)
    assert 'test-only-image-key' not in response.text and 'data:image/' not in response.text and 'key_digest' not in response.text
    assert main.get_task(t['id'])==before and not main.budgets.get(t['id'])['entries']
    assert client.get(f"/api/tasks/{t['id']}/materials/{m['id']}/image-interpretation").json()==value


@pytest.mark.parametrize('fault',['role','missing_key','missing_price','wrong_hash','stale_revision','empty_instruction','low_reserve','over_limit','bad_source'])
def test_unready_source_service_or_fee_never_creates_plan_or_pending(client,fault):
    t,m,p=setup(client);patch={}
    if fault=='role':client.patch('/api/providers/'+p['id'],json={'role':'main'})
    elif fault=='missing_key':p=client.post('/api/providers',json={'name':'缺Key识图服务','provider':'custom','role':'vision','protocol':'openai-compatible','model':'fixture','base_url':'https://example.test/v1','pricing':{'input_per_million_usd':1,'output_per_million_usd':2}}).json()
    elif fault=='missing_price':client.patch('/api/providers/'+p['id'],json={'pricing':None})
    elif fault=='wrong_hash':patch['source_sha256']='0'*64
    elif fault=='stale_revision':patch['revision']=t['revision']-1
    elif fault=='empty_instruction':patch['instruction']=' '
    elif fault=='low_reserve':patch['image_reserve_usd']='.00001'
    elif fault=='over_limit':patch['image_reserve_usd']='2'
    elif fault=='bad_source':(main.DATA_ROOT/t['id']/'materials'/(m['id']+'.png')).write_bytes(b'changed')
    before=main.get_task(t['id']);response=prepare(client,t,m,p,**patch)
    assert response.status_code in {409,422},response.text
    assert not main.store.list('image_preview') and main.get_task(t['id'])==before
    assert not main.budgets.get(t['id'])['entries']


@pytest.mark.parametrize('change',['key','price','model','source','task_revision','settings','budget_policy'])
def test_reading_current_preview_marks_changed_binding_without_rewriting_preview(client,change):
    t,m,p=setup(client);value=prepare(client,t,m,p).json();record=main.store.get('image_preview',value['record']['id']);before=copy.deepcopy(record)
    if change=='key':main.store.set_secret(p['id'],'api_key','different-image-test-key')
    elif change=='price':client.patch('/api/providers/'+p['id'],json={'pricing':{'input_per_million_usd':2,'output_per_million_usd':3}})
    elif change=='model':client.patch('/api/providers/'+p['id'],json={'model':'different-fixture'})
    elif change=='source':(main.DATA_ROOT/t['id']/'materials'/(m['id']+'.png')).write_bytes(b'changed')
    elif change=='task_revision':client.patch(f"/api/tasks/{t['id']}/materials/{m['id']}",json={'revision':t['revision'],'reference_mode':'borrow'})
    elif change=='settings':client.patch('/api/settings',json={'max_cost_usd':.2})
    elif change=='budget_policy':
        budget=main.budgets.get(t['id']);budget['policy_revision']+=1;main.store.put('task_budget',t['id'],budget)
    result=client.get(f"/api/tasks/{t['id']}/materials/{m['id']}/image-interpretation").json()
    assert result['preflight_blocker'] and not result['can_execute']
    assert main.store.get('image_preview',record['id'])==before



def test_local_image_view_is_owned_uncached_readonly_and_hash_bound(client,monkeypatch):
    t,m,p=setup(client);before=main.get_task(t['id'])
    async def forbidden(*a,**kw):raise AssertionError('本机看原图不能调用模型')
    monkeypatch.setattr(main,'call_model',forbidden)
    url=f"/api/tasks/{t['id']}/materials/{m['id']}/image-source"
    response=client.get(url,params={'source_sha256':m['sha256']})
    assert response.status_code==200 and response.content==png() and response.headers['content-type']=='image/png'
    assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'
    assert main.get_task(t['id'])==before and not main.budgets.get(t['id'])['entries'] and not main.store.list('image_preview')
    assert client.get(url,params={'source_sha256':'b'*64}).status_code==409
    assert client.get(f"/api/tasks/{t['id']}/materials/wrong/image-source",params={'source_sha256':m['sha256']}).status_code==404
    (main.DATA_ROOT/t['id']/'materials'/(m['id']+'.png')).write_bytes(b'changed')
    assert client.get(url,params={'source_sha256':m['sha256']}).status_code==409



def test_changed_oversize_source_read_is_bounded_before_material_or_budget_changes(client,monkeypatch):
    t,m,p=setup(client);before=main.get_task(t['id']);path=main.DATA_ROOT/t['id']/'materials'/(m['id']+'.png')
    from pathlib import Path
    original_open=Path.open;reads=[]
    class Oversize:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self,size):
            reads.append(size);assert size==20*1024*1024+1
            return b'x'*size
    def bounded(self,*args,**kwargs):
        if self==path and args==('rb',):return Oversize()
        return original_open(self,*args,**kwargs)
    monkeypatch.setattr(Path,'open',bounded)
    response=prepare(client,t,m,p)
    assert response.status_code==409 and reads==[20*1024*1024+1]
    assert main.get_task(t['id'])==before and not main.store.list('image_preview') and not main.budgets.get(t['id'])['entries']
