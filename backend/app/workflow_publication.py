"""Explicit first publication of a current imported Workflow. No keys or runs."""
import copy
import hashlib
import time
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, StrictStr

from .dify import DifyError
from .dsl_roundtrip import digest, parse

KIND = 'workflow_publication'
NOTE = '只发布已核对的新应用；不创建Key、不试跑。Dify发布接口没有草稿条件锁，核对与发布之间仍可能发生外部编辑；返回后另核对发布图，不代表业务验收。'


class Prepare(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt


class Confirm(Prepare):
    proposal_id: StrictStr
    review_token: StrictStr
    confirm_publish: StrictBool


def core(workflow):
    """Compare all node data/edges/features/variables; ignore canvas geometry only."""
    try:
        graph = workflow['graph']
        nodes = graph['nodes']; edges = graph['edges']
        ids = [n['id'] for n in nodes]
        if not nodes or len(set(ids)) != len(ids): raise ValueError()
        return {'nodes': sorted([{'id': n['id'], 'data': n['data'], 'type': n.get('type'), 'parentId': n.get('parentId'), 'extent': n.get('extent')} for n in nodes], key=lambda n: n['id']),
                'edges': sorted([{'source': e['source'], 'sourceHandle': e.get('sourceHandle'),
                                  'target': e['target'], 'targetHandle': e.get('targetHandle')} for e in edges], key=digest),
                'features': workflow.get('features', {}),
                'environment_variables': workflow.get('environment_variables', []),
                'conversation_variables': workflow.get('conversation_variables', []),
                'rag_pipeline_variables': workflow.get('rag_pipeline_variables', [])}
    except (KeyError, TypeError, ValueError):
        raise HTTPException(422, '平台流程结构不完整，未执行发布。') from None


def public(row):
    return {k: copy.deepcopy(row[k]) for k in ('id', 'task_id', 'revision', 'app_id', 'environment_id',
            'environment_url', 'environment_version', 'artifact_sha256', 'graph_digest',
            'review_token', 'state', 'expires_at', 'created_at', 'write_attempted', 'workflow_id', 'message') if k in row} | {
            'note': NOTE, 'new_apps': 0, 'publish_attempts': 1, 'new_keys': 0, 'runs': 0,
            'planned_console_reads': 5, 'authentication_may_add_reads': True, 'automatic_retry': False, 'business_verified': False}


def register(h):
    router = APIRouter()

    def source(task):
        h.require_intake(task)
        if task.get('app_type') != 'workflow':
            raise HTTPException(422, '此发布入口目前仅适配Workflow；Chatflow和原生Agent请在Dify核对发布，应用类型保持。')
        if not task.get('requirements_confirmed') or not task.get('configuration_confirmed') or task.get('plan_stale'):
            raise HTTPException(409, '请先确认当前修订的需求、配置与流程。')
        h.require_manual_entry_runtime(task)
        app = task.get('dify_app_id')
        try:
            if str(uuid.UUID(app)) != app: raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise HTTPException(422, '缺少当前修订的新建导入App，请先完成导入。') from None
        env = h.environment(task)
        content = h.artifact_path(task).read_text(encoding='utf-8')
        root = parse(content, 'workflow'); graph = core(root['workflow'])
        types = [n['data'].get('type') for n in graph['nodes']]
        if types.count('start') != 1 or any(isinstance(t, str) and t.startswith('trigger-') for t in types):
            raise HTTPException(422, '此入口仅发布手动Start流程；自动触发入口须使用专用资源方案。')
        imports = [r for r in task.get('runs', []) if r.get('kind') == 'import' and r.get('status') == 'success'
                   and r.get('revision') == task['revision'] and r.get('environment_id') == env['id']
                   and (r.get('result') or {}).get('app_id') == app]
        if not imports or digest(core((imports[-1].get('dsl_baseline') or {}).get('workflow', {}))) != digest(graph):
            raise HTTPException(409, '当前成果与本修订的新建导入依据不一致，不能发布未知来源应用。')
        # Any earlier dispatched publication is one-shot, even after a local revision change.
        for row in h.store.list(KIND):
            if (row.get('app_id') == app and row.get('environment_id') == env['id']
                    and row.get('write_attempted')):
                raise HTTPException(409, '该App已有发布派发记录，禁止重复发布；请先在Dify核对原结果。')
        binding = {'task_id': task['id'], 'revision': task['revision'], 'app_id': app,
                   'environment': h.env_snapshot(env), 'artifact_sha256': hashlib.sha256(h.artifact_path(task).read_bytes()).hexdigest(),
                   'graph_digest': digest(graph), 'pause_generation': task.get('pause_generation', 0)}
        return binding, env, graph

    def check(task_id, binding):
        task = h.get_task(task_id)
        current, env, graph = source(task)
        if digest(current) != digest(binding):
            raise HTTPException(409, '任务、成果或环境已变化，原发布核对失效；未派发发布。')
        if task.get('status') == 'paused': raise HTTPException(409, '任务已暂停，未派发发布。')
        return task, env, graph

    async def remote(client, app, graph):
        draft = await client.request('GET', f'/console/api/apps/{app}/workflows/draft', credential='console_token')
        if not isinstance(draft, dict) or not isinstance(draft.get('hash'), str) or not draft['hash']:
            raise HTTPException(422, '无法核对Dify原生草稿hash，未发布。')
        if digest(core(draft)) != digest(graph):
            raise HTTPException(409, 'Dify草稿与本机成果不同，请先核对手工修改；未发布。')
        try:
            published = await client.published_workflow(app)
        except DifyError as exc:
            if exc.http_status != 404: raise
            published = None
        if published is not None:
            raise HTTPException(409, '目标App已有发布版本，此入口不覆盖或再次发布；请核对原发布。')
        return draft

    @router.get('/api/tasks/{item_id}/workflow-publication')
    def history(item_id: str):
        h.get_task(item_id)
        rows = [r for r in h.store.list(KIND) if r.get('task_id') == item_id]
        return {'records': [public(r) for r in rows[:10]], 'note': NOTE}

    @router.post('/api/tasks/{item_id}/workflow-publication/prepare')
    async def prepare(item_id: str, payload: Prepare):
        with h.store.lock:
            task = h.get_task(item_id); h.require_idle(task); h.require_revision(task, payload.revision)
            if task.get('status') == 'paused': raise HTTPException(409, '任务已暂停，请先明确恢复。')
            binding, env, graph = source(task)
        try:
            draft = await remote(h.DifyClient(env, h.store), binding['app_id'], graph)
        except DifyError:
            raise HTTPException(502, '发布前只读核对未通过，请核对Dify连接；未发送发布。') from None
        with h.store.lock:
            task, env, _ = check(item_id, binding); h.require_idle(task)
            row = {'id': str(uuid.uuid4()), 'task_id': item_id, 'revision': payload.revision,
                   'app_id': binding['app_id'], 'environment_id': env['id'], 'environment_url': env['base_url'],
                   'environment_version': env['version'], 'binding': binding, 'artifact_sha256': binding['artifact_sha256'],
                   'graph_digest': binding['graph_digest'], 'draft_hash': draft['hash'], 'draft_digest': digest(draft),
                   'created_at': h.now(), 'expires_at': time.time() + 900, 'write_attempted': False,
                   'state': 'ready', 'message': '草稿匹配且尚未发布。请核对目标后明确确认。'}
            row['review_token'] = digest(row)
            h.store.put(KIND, row['id'], row)
            return public(row)

    @router.post('/api/tasks/{item_id}/workflow-publication/confirm')
    async def confirm(item_id: str, payload: Confirm):
        with h.store.lock:
            task = h.get_task(item_id); h.require_idle(task); h.require_revision(task, payload.revision)
            row = h.store.get(KIND, payload.proposal_id)
            if (not row or row['task_id'] != item_id or row['revision'] != payload.revision
                    or row['review_token'] != payload.review_token or row['state'] != 'ready'
                    or row['expires_at'] < time.time() or payload.confirm_publish is not True):
                raise HTTPException(409, '发布核对不存在、已使用、过期或未明确同意；请重新核对。')
            task, env, graph = check(item_id, row['binding'])
            record = {'id': str(uuid.uuid4()), 'kind': 'publish', 'revision': payload.revision,
                      'environment_id': env['id'], 'app_id': row['app_id'], 'status': 'pending',
                      'created_at': h.now(), 'publication_id': row['id'], 'error': ''}
            task['runs'].append(record); h.save_task(task)
            row.update(state='checking'); h.store.put(KIND, row['id'], row)
        try:
            client = h.DifyClient(env, h.store)
            draft = await remote(client, row['app_id'], graph)
            with h.store.lock:
                check(item_id, row['binding'])
                if digest(draft) != row['draft_digest']:
                    raise HTTPException(409, 'Dify草稿在核对后有变化，请重新核对；未发布。')
                row.update(state='publishing', write_attempted=True)
                record['write_attempted'] = True
                current = h.get_task(item_id)
                next(r for r in current['runs'] if r['id'] == record['id']).update(record)
                h.store.put_many([(KIND, row['id'], row), ('task', item_id, current)])
            # Dify 1.17.1 has no conditional hash parameter on this endpoint.
            await client.request('POST', f"/console/api/apps/{row['app_id']}/workflows/publish",
                                 credential='console_token', json={'marked_name': 'Sierra r' + str(payload.revision),
                                 'marked_comment': 'Explicit current-revision publication ' + row['id']})
            published = await client.published_workflow(row['app_id'])
            try:
                published_id = str(uuid.UUID(published['id']))
            except (ValueError, KeyError, TypeError, AttributeError):
                raise HTTPException(502, '发布返回身份无效，结果待人工核对。') from None
            if digest(core(published)) != row['graph_digest']:
                raise HTTPException(502, '发布后的流程核对未通过，结果待人工核对。')
            with h.store.lock:
                # The source guard deliberately rejects any write_attempted row now.
                current = h.get_task(item_id)
                env_now = h.store.get('environment', env['id'])
                if (current['revision'] != row['revision'] or current.get('dify_app_id') != row['app_id']
                        or current.get('status') == 'paused' or current.get('pause_generation', 0) != row['binding']['pause_generation']
                        or not current.get('requirements_confirmed') or not current.get('configuration_confirmed') or digest(h.env_snapshot(env_now)) != digest(row['binding']['environment'])
                        or hashlib.sha256(h.artifact_path(current).read_bytes()).hexdigest() != row['artifact_sha256']):
                    raise HTTPException(409, '发布返回期间本机状态改变，结果待核对，不标记当前版本发布通过。')
                row.update(state='succeeded', workflow_id=published_id, message='发布已返回且发布图匹配；仍需绑定Key及业务试跑。')
        except BaseException as exc:
            row.update(state='unknown' if row['write_attempted'] else 'failed',
                       message='发布可能已执行，请到Dify核对；禁止自动重发。' if row['write_attempted'] else '发布前核对失败，未派发发布；请刷新后重新核对。')
            finish(item_id, row, record, success=False)
            if isinstance(exc, HTTPException) and not row['write_attempted']: raise
            if not isinstance(exc, Exception): raise
            raise HTTPException(502, row['message']) from None
        finish(item_id, row, record, success=True)
        return public(row)

    def finish(item_id, row, record, *, success):
        with h.store.lock:
            task = h.get_task(item_id)
            target = next(r for r in task['runs'] if r['id'] == record['id'])
            target.update(status='success' if success else ('unknown' if row['write_attempted'] else 'failed'),
                          completed_at=h.now(), error='' if success else row['message'],
                          result={'app_id': row['app_id'], 'publication_id': row['id'], 'state': row['state'],
                                  'workflow_id': row.get('workflow_id'), 'business_verified': False})
            h.store.put_many([(KIND, row['id'], row), ('task', item_id, task)])

    def recover():
        with h.store.lock:
            for row in h.store.list(KIND):
                if row.get('state') in {'checking', 'publishing'}:
                    row.update(state='unknown' if row.get('write_attempted') else 'failed',
                               message='服务重启时发布核对中断，请在Dify核对原结果；不会重发。')
                    h.store.put(KIND, row['id'], row)
    h.workflow_publication_recover = recover
    h.app.include_router(router)
