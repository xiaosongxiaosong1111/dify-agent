"""Public protocol responses only; only the three remaining model stages are served."""
import copy
import json
from uuid import uuid4

import httpx

from common import MODEL_STAGES, require


class Stream(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        yield self.body


def response(value, status=200, headers=()):
    return httpx.Response(status, headers=[('content-type', 'application/json'), *headers],
                          stream=Stream(json.dumps(value, ensure_ascii=False).encode()))


class PlatformSynthetic:
    def __init__(self, b, mode):
        self.b = b
        self.mode = mode
        self.apps = {}
        self.messages = {}
        self.runs = {}

    async def __call__(self, request):
        b = self.b
        path = request.url.path
        method = request.method
        body = json.loads(request.content) if request.content else {}
        if path == '/console/api/login':
            return response({'result': 'success'}, 503 if self.mode == 'fail_login' else 200,
                            [('set-cookie', 'access_token=PUBLICCONSOLETOKEN123456789; Path=/'),
                             ('set-cookie', 'csrf_token=PUBLICCSRFTOKEN123456789; Path=/')])
        if path == '/console/api/workspaces/current/summary':
            return response({'id': str(uuid4()) if self.mode == 'wrong_workspace'
                             else b.env['console_workspace_id']})
        if path == '/console/api/apps':
            return response({'data': []})
        if path == '/console/api/apps/imports':
            if self.mode == 'fail_import':
                return response({'error': 'PUBLIC_FAILURE'}, 502)
            from app.dsl_roundtrip import parse
            app = str(uuid4())
            self.apps[app] = {'draft': parse(body['yaml_content'], 'advanced-chat')['workflow']
                              | {'hash': 'public-' + app}, 'published': None, 'keys': []}
            return response({'status': 'completed', 'app_id': app})
        app = path.split('/')[4] if path.startswith('/console/api/apps/') else b.current
        if app in self.apps:
            row = self.apps[app]
            if path == f'/console/api/apps/{app}':
                return response({'id': app, 'mode': 'advanced-chat'})
            if path.endswith('/workflows/draft'):
                value = copy.deepcopy(row['draft'])
                if self.mode == 'changed_draft_state':
                    value['conversation_variables'][0]['value'] = True
                return response(value)
            if path.endswith('/workflows/publish'):
                if method == 'POST':
                    if self.mode == 'fail_publish':
                        return response({'error': 'PUBLIC_FAILURE'}, 502)
                    row['published'] = copy.deepcopy(row['draft']) | {'id': str(uuid4())}
                    return response({'result': 'success', 'created_at': 1700000000})
                if row['published'] is None:
                    return response(None, 404)
                result = copy.deepcopy(row['published'])
                if self.mode == 'changed_published':
                    result['graph']['nodes'][0]['data']['title'] = 'changed'
                if self.mode == 'changed_published_state':
                    result['conversation_variables'][0]['id'] = str(uuid4())
                return response(result)
            if path.endswith('/api-keys'):
                if method == 'POST':
                    if self.mode == 'fail_key':
                        return response({'error': 'PUBLIC_FAILURE'}, 502)
                    row['keys'] = [{'id': str(uuid4()), 'token': 'app-PUBLIC-' + str(uuid4())}]
                    return response(row['keys'][0])
                return response({'data': row['keys']})
        if path == '/v1/chat-messages':
            if self.mode == 'fail_service':
                return response({'error': 'PUBLIC_FAILURE'}, 502)
            case = b.f['cases'][b.case_index]
            second = 'conversation_id' in body
            turn = case['followups'][0] if second else case
            expected = turn['expectation']['expected']
            answer = ' '.join(expected) if isinstance(expected, list) else expected
            if b.version == 'modified' and b.case_index == 1:
                answer = b.f['changed_no_hit_reply']
            if self.mode in {'business_failure', 'failure_diagnostic_error'}:
                answer = '公开替身错误答案'
            if self.mode == 'second_turn_business_failure' and second:
                answer = b.f['inputs']['clarify_reply']
            cid = body.get('conversation_id') or str(uuid4())
            if second and self.mode == 'changed_session':
                cid = str(uuid4())
            mid, rid = str(uuid4()), str(uuid4())
            self.messages[mid] = {'id': mid, 'conversation_id': cid, 'workflow_run_id': rid}
            ids = {'start', 'order_followup', 'consume_order_wait', 'route_order_followup'}
            i = b.case_index
            if not second:
                ids.add('intent')
            if self.mode == 'followup_classifier_bypass' and second:
                ids.add('intent')
            if i in (0, 1):
                ids |= {'retrieve', 'collect_docs', 'check_hit'} | (
                    {'grounded_answer', 'faq_answer'} if i == 0 or self.mode == 'nonempty_no_answer'
                    else {'no_hit', 'no_hit_answer'})
            elif i == 2:
                ids |= {'clarify', 'clarify_answer'}
            elif i in (3, 4) or second:
                ids |= {'extract_order', 'check_order', 'validate_order', 'check_order_value',
                        'order_lookup', 'order_answer'}
                if self.mode == 'bypass_order_value':
                    ids -= {'validate_order', 'check_order_value'}
            else:
                ids |= {'extract_order', 'check_order', 'request_order_wait', 'missing_order',
                        'missing_order_answer'}
                if self.mode == 'blank_order':
                    ids |= {'validate_order', 'check_order_value'}
            if self.mode == 'second_turn_business_failure' and second:
                ids = {'start', 'order_followup', 'consume_order_wait', 'route_order_followup',
                       'intent', 'clarify', 'clarify_answer'}
            graph = copy.deepcopy(self.apps[b.current]['published']['graph'])
            nodes = []
            for n in graph['nodes']:
                if n['id'] in ids:
                    row = {'id': str(uuid4()), 'node_id': n['id'], 'node_type': n['data']['type'],
                           'title': n['data']['title'], 'status': 'succeeded', 'error': None}
                    if n['id'] == 'extract_order':
                        row['outputs'] = {'__is_success': 0 if i == 5 and not second
                                          and self.mode != 'blank_order' else 1,
                                          'order_no': '' if i == 5 and not second else 'DEMO-001'}
                    if n['id'] == 'validate_order':
                        row['outputs'] = {'has_order': not (i == 5 and not second)}
                    if n['id'] == 'retrieve':
                        row['outputs'] = {'result': [{'content': '公开资料'}]
                                          if i == 0 or self.mode == 'nonempty_no_answer' else []}
                    nodes.append(row)
            self.runs[rid] = {'detail': {'id': rid, 'status': 'succeeded', 'graph': graph},
                              'trace': {'data': nodes}}
            return response({'event': 'message', 'mode': 'advanced-chat', 'id': mid,
                             'message_id': mid, 'conversation_id': cid, 'answer': answer,
                             'metadata': {'usage': {'total_tokens': 10, 'total_price': '0.0001',
                                                    'currency': 'USD'}}})
        if '/messages/' in path:
            value = copy.deepcopy(self.messages[path.rsplit('/', 1)[-1]])
            if self.mode == 'wrong_message_source':
                value['conversation_id'] = str(uuid4())
            return response(value)
        for rid, items in self.runs.items():
            if path.endswith('/' + rid):
                return response(items['detail'])
            if path.endswith('/' + rid + '/node-executions'):
                if self.mode == 'failure_diagnostic_error':
                    return response({'error': 'PUBLIC_DIAGNOSTIC_FAILURE'}, 502)
                return response(items['trace'])
        raise RuntimeError('Unexpected public fixture path')


class Synthetic(PlatformSynthetic):
    def __init__(self, b, mode, h):
        super().__init__(b, mode)
        self.h = h

    async def __call__(self, request):
        b = self.b
        path = request.url.path
        if str(request.url) == b.provider['base_url'].rstrip('/') + '/chat/completions':
            stage = b.phase
            require(stage in MODEL_STAGES, 'Old interview or unknown model stage is forbidden')
            messages = json.loads(request.content)['messages']
            task = self.h.get_task(b.owner)
            if stage == 'modified_interview':
                context = json.loads(messages[1]['content'].split('当前任务资料：', 1)[1])
                review = copy.deepcopy(context['previous_intake'])
                source = next((x for x in reversed(context['intake_sources'])
                               if x['kind'] == 'message' and b.f['changed_no_hit_reply'] in x['text']),
                              None)
                require(source is not None, 'Synthetic modified-interview source missing')
                for row in review['checks']:
                    if row['topic'] in {'output', 'dialogue'}:
                        row['evidence'] = [{'kind': 'message', 'id': source['id'],
                                            'quote': b.f['changed_no_hit_reply']}]
                body = {'message': '已记录两处公开合成回复变化，其余规则保持，请复核。',
                        'requirements_patch': {'output': task['requirements']['output'].replace(
                            b.f['inputs']['no_hit_reply'], b.f['changed_no_hit_reply'])},
                        'intake_review': review}
            elif stage == 'original_plan':
                from app.after_sales_starter import prepare
                raw, checked = prepare(task, b.f['inputs'])
                require(checked['valid'], 'Synthetic original starter invalid')
                body = json.loads(raw)
            elif stage == 'modified_plan':
                from candidate import replace_text
                body = replace_text(b.contract['original']['plan'], b.f['inputs']['no_hit_reply'],
                                    b.f['changed_no_hit_reply'])
            else:
                raise RuntimeError('Unexpected model stage')
            text = '{"broken": [}' if self.mode == 'invalid_model_json' else json.dumps(
                body, ensure_ascii=False)
            usage = {} if self.mode == 'unknown_model_usage' else {
                'prompt_tokens': 200, 'completion_tokens': 300, 'total_tokens': 500}
            return response({'choices': [{'finish_reason': 'stop',
                                          'message': {'role': 'assistant', 'content': text}}],
                             'usage': usage}, 502 if self.mode == 'fail_model' else 200)
        dataset = b.f['configuration']['dataset_ids'][0]
        prefix = '/console/api/datasets/' + dataset
        if path == prefix:
            return response({'id': dataset, 'name': '公开合成FAQ'})
        doc = '33333333-3333-4333-8333-333333333333'
        if path == prefix + '/documents':
            page = int(request.url.params.get('page', '1'))
            limit = int(request.url.params.get('limit', '2'))
            rows = [{'id': doc, 'indexing_status': 'completed', 'name': '公开政策'}]
            return response({'data': rows, 'has_more': len(rows) == limit, 'total': len(rows),
                             'page': page, 'limit': limit})
        if path == prefix + '/documents/' + doc + '/segments':
            page = int(request.url.params.get('page', '1'))
            limit = int(request.url.params.get('limit', '20'))
            text = '公开FAQ政策ZXRET715：签收七天内且商品未拆封，允许退货。' \
                if self.mode != 'wrong_faq' else '公开但不对应本案的政策。'
            rows = [{'id': '44444444-4444-4444-8444-444444444444', 'content': text,
                     'status': 'completed', 'enabled': True}]
            return response({'data': rows, 'total': len(rows), 'total_pages': 1,
                             'page': page, 'limit': limit})
        return await super().__call__(request)

    def expectations(self, candidate):
        common = {'start', 'order_followup', 'consume_order_wait', 'route_order_followup'}
        result = {}
        for i, case in enumerate(self.b.f['cases']):
            rows = {}
            for turn in (1, 2) if case.get('followups') else (1,):
                needed = set(common)
                forbidden = set()
                if turn == 2:
                    forbidden |= {'intent', 'request_order_wait'}
                else:
                    needed.add('intent')
                if i == 0:
                    needed |= {'retrieve', 'collect_docs', 'check_hit', 'grounded_answer', 'faq_answer'}
                elif i == 1:
                    needed |= {'retrieve', 'collect_docs', 'check_hit', 'no_hit', 'no_hit_answer'}
                elif i == 2:
                    needed |= {'clarify', 'clarify_answer'}
                elif i in (3, 4) or turn == 2:
                    needed |= {'extract_order', 'check_order', 'validate_order',
                               'check_order_value', 'order_lookup', 'order_answer'}
                else:
                    needed |= {'extract_order', 'check_order', 'request_order_wait',
                               'missing_order', 'missing_order_answer'}
                if not (i in (3, 4) or turn == 2):
                    forbidden.add('order_lookup')
                rows[str(turn)] = {'must': sorted(needed), 'must_not': sorted(forbidden)}
            result[case['id']] = rows
        return result
