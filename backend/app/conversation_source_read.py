"""Local provenance inspection only; never decrypt credentials or contact Dify."""
from fastapi import APIRouter, HTTPException, Query
from .conversation_inputs import custom_input_source
from .start_inputs import check_values
from .plan_drafts import DraftRoute


class ConversationSourceRead:
    def __init__(self, host): self.h = host
    def register(self):
        h = self.h
        router = APIRouter(route_class=DraftRoute)

        @router.get('/api/tasks/{item_id}/conversation-input-source/{run_id}')
        def read(item_id: str, run_id: str, revision: int = Query(ge=1), source_sha256: str = Query(pattern=r'^[a-f0-9]{64}$')):
            with h.store.lock:
                task = h.get_task(item_id)
                h.require_revision(task, revision)
                if task['app_type'] != 'advanced-chat':
                    raise HTTPException(422, '原参数会话来源核对只适配Chatflow，不更换应用类型。')
                schema = h.read_run_input_schema(item_id)
                if schema['source_sha256'] != source_sha256:
                    raise HTTPException(409, '当前成果已改变，未采用另一份入口的来源核对。')
                fields = [r['variable'] for r in schema['fields'] if r['variable'] != 'query']
                result = {'task_id':item_id,'revision':revision,'run_id':run_id,'source_sha256':source_sha256,
                          'verification':'local_custom_conversation_source_only','platform_checked':False,
                          'business_verified':False,'runtime_inputs_checked':False,
                          'credentials_decrypted':False,'network_requested':False,'checked_at':h.now(),
                          'source_binding_valid':False,'state':'not_ready','custom_field_count':len(fields),
                          'note':'仅核对本机原记录、当前成果／目标和运行凭据密文版本；不解密、不连接Dify或模型、不保存结果或修改Task。不检查本次新输入、平台会话是否仍存在或业务；真实派发仍须重新核对。'}
                if not fields:
                    return {**result,'state':'not_applicable','reason':'当前成果没有自定义开始参数，不将此结果冒充普通会话来源许可。'}
                try:
                    sources = [r for r in task['runs'] if isinstance(r,dict) and r.get('id') == run_id]
                    if len(sources) != 1:
                        raise HTTPException(422, '所选本机会话记录缺失或不唯一，未核对其它来源。')
                    source = sources[0]
                    value = source.get('result')
                    cid = value.get('conversation_id') if isinstance(value,dict) else None
                    env = h.environment(task)
                    if not task.get('dify_app_id') or env.get('service_app_id') != task['dify_app_id']:
                        raise HTTPException(422, '当前登记运行Key的App ID与任务不一致，未将其当作原会话目标。')
                    original = custom_input_source(h.store,task,env,{'source_run_id':run_id,'conversation_id':cid},source_sha256)
                    original = {k:v for k,v in original.items() if k != 'conversation_id'}
                    check_values(schema['fields'],original)
                    if not original['query'].strip(): raise ValueError('原记录的query不是当前可用问题。')
                except HTTPException as exc:
                    if exc.status_code >= 500:
                        return {**result,'source_binding_valid':None,'state':'unknown','reason':str(exc.detail)}
                    return {**result,'reason':str(exc.detail)}
                except (ValueError,TypeError,KeyError):
                    return {**result,'reason':'原记录输入与当前入口结构不一致，未修正或忽略字段。'}
                return {**result,'source_binding_valid':True,'state':'locally_matched',
                        'reason':'原记录来源通过本机核对；尚未核对本次输入或执行续聊，不是资源／业务通过。'}

        h.app.include_router(router)
