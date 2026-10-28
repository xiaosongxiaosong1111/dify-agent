"""Local comparison for this case's two fixed literal locations. No execution/approval."""
import copy,hashlib,json


class ScopeError(ValueError):pass


def canonical(value):
    try:
        text=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
        raw=text.encode('utf-8')
        if len(raw)>2_000_000:raise ValueError()
        return raw
    except (ValueError,TypeError,RecursionError,OverflowError,UnicodeError):
        raise ScopeError('计划不是有界有限JSON，未核对变更。') from None


def check(original,candidate,before,after):
    """Require the two known literal substitutions and byte-equivalent remaining content."""
    if not all(isinstance(v,str) and v.strip() for v in (before,after)) or before==after:
        raise ScopeError('需要不同且明确的原提示与新提示。')
    original_bytes=canonical(original);candidate_bytes=canonical(candidate)
    if not isinstance(original,dict) or not isinstance(candidate,dict):raise ScopeError('缺少完整计划对象。')
    nodes=original.get('nodes')
    if not isinstance(nodes,list) or not nodes or any(not isinstance(n,dict) or not isinstance(n.get('id'),str) or not n['id'] for n in nodes):raise ScopeError('节点来源不明确。')
    if len({n['id'] for n in nodes})!=len(nodes):raise ScopeError('节点身份重复，不能推定目标位置。')
    fixed=[n for n in nodes if n.get('type')=='template-transform'];answers=[n for n in nodes if n.get('type')=='llm']
    if len(fixed)!=1 or len(answers)!=1:raise ScopeError('本案例需要唯一固定回复节点和回答节点。')
    template=fixed[0].get('config');llm=answers[0].get('config')
    if not isinstance(template,dict) or template.get('template')!=before or not isinstance(llm,dict):raise ScopeError('原固定回复位置不匹配。')
    prompt=llm.get('system_prompt')
    if not isinstance(prompt,str) or prompt.count(before)!=1:raise ScopeError('原回答提示须有唯一同文案位置。')
    expected=copy.deepcopy(original)
    for n in expected['nodes']:
        if n['id']==fixed[0]['id']:n['config']['template']=after
        if n['id']==answers[0]['id']:n['config']['system_prompt']=prompt.replace(before,after,1)
    if canonical(expected)!=candidate_bytes:raise ScopeError('除两处同话术替换外仍有变更，未接受候选。')
    return {'state':'two_literal_locations_only','original_sha256':hashlib.sha256(original_bytes).hexdigest(),
            'candidate_sha256':hashlib.sha256(candidate_bytes).hexdigest(),
            'changed_fields':[{'node_id':answers[0]['id'],'field':'config.system_prompt'},{'node_id':fixed[0]['id'],'field':'config.template'}],
            'other_content_unchanged':True,'candidate_changed':False,'network_requested':False,
            'resource_authorized':False,'platform_checked':False,'business_verified':False}
