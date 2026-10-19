"""Local saved-case input checks: no credentials, dispatch or task mutation."""
import copy
import hashlib
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, StrictInt, Field
from .run_input_transport import RunInputRoute
from .start_inputs import check_values, require_stable_chat_turns
from .evaluation import validate_test_cases


class CaseCheck(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: StrictInt = Field(ge=1)
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    case_id: str = Field(min_length=1, max_length=256)


def encoded_case(value):
    try:
        text = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
        if len(text) > 2000000: raise ValueError()
    except (TypeError, ValueError, RecursionError, UnicodeError):
        raise HTTPException(422, '固定样例须为最多2MB的有限JSON，结构或编码无效时不显示原输入。') from None
    return text


def saved_case(task, case_id):
    if not isinstance(task.get('test_cases', []), list): raise HTTPException(422, '固定样例列表结构无效，未检查或修正其它内容。')
    rows = [r for r in task.get('test_cases', []) if isinstance(r, dict) and r.get('id') == case_id]
    if len(rows) != 1: raise HTTPException(404, '选定固定样例不存在或ID不唯一，未检查其它样例。')
    return copy.deepcopy(rows[0])


class RunCaseInputCheck:
    def __init__(self, host): self.h = host
    def register(self):
        h = self.h
        router = APIRouter(route_class=RunInputRoute)

        @router.post('/api/tasks/{item_id}/run-case-input-check')
        def check(item_id: str, payload: CaseCheck):
            with h.store.lock:
                task = h.get_task(item_id)
                h.require_revision(task, payload.revision)
                if task['app_type'] not in {'workflow','advanced-chat'}: raise HTTPException(422, '本机入口检查只适配Workflow／Chatflow，不替换所选应用类型。')
                schema = h.read_run_input_schema(item_id)
                if schema['source_sha256'] != payload.source_sha256:
                    raise HTTPException(409, '最终成果入口已改变，请刷新入口后重新检查固定样例。')
                case = saved_case(task, payload.case_id)
                encoded = encoded_case(case)
                validation = validate_test_cases([case], task['app_type'])
                if not validation['valid']:
                    raise HTTPException(422, '固定样例结构未通过检查：'+'；'.join(validation['errors']))
                turns = [case, *case.get('followups', [])]
                errors = []
                for index, turn in enumerate(turns):
                    try:
                        check_values(schema['fields'], turn['input'])
                        if task['app_type'] == 'advanced-chat' and not turn['input'].get('query', '').strip():
                            raise ValueError('Chatflow需要非空query文本。')
                    except ValueError as exc:
                        errors.append(f'第{index+1}轮：{exc}')
                if task['app_type'] == 'advanced-chat' and case.get('followups') and len(schema['fields']) > 1:
                    try: require_stable_chat_turns(case)
                    except ValueError as exc: errors.append(str(exc))
                if errors: raise HTTPException(422, '固定样例入口未通过本机检查：'+'；'.join(errors))
                latest_schema = h.read_run_input_schema(item_id)
                latest_task = h.get_task(item_id)
                h.require_revision(latest_task, payload.revision)
                if latest_schema['source_sha256'] != schema['source_sha256'] or encoded_case(saved_case(latest_task, payload.case_id)) != encoded:
                    raise HTTPException(409, '检查期间成果入口或固定样例改变，未采用旧结果。')
                return {'task_id':item_id, 'revision':payload.revision, 'case_id':payload.case_id,
                        'source_sha256':schema['source_sha256'], 'case_sha256':hashlib.sha256(encoded).hexdigest(),
                        'valid':True, 'checked_turns':[{'index':i+1,'valid':True} for i in range(len(turns))],
                        'verification':'local_case_input_shape_only', 'platform_checked':False,
                        'business_verified':False, 'defaults_copied':False, 'checked_at':h.now(),
                        'note':'仅检查当前最终成果与已保存样例的全部入口及固定参数一致性；不改样例／填默认，不保存检查记录，不执行模型、Dify或预算登记。没有为预期答案评分，也不代表已发布入口、资源可用或业务通过。修改成果、样例或修订后须重新检查；hash不保证输入匿名化。'}

        h.app.include_router(router)
