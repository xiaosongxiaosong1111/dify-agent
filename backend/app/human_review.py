"""Root Workflow review-only HITL draft; no forms/delivery/resume execution."""
import copy,re,uuid
from .conversation_state import safe_text

FIELDS={'form_content','inputs','user_actions','timeout','timeout_unit','delivery_methods'}
HANDLES={'approve','reject','__timeout'}
RUNTIME_LIMIT='人工审核首批只支持根Workflow审核草稿、静态检查与下载，批准／拒绝／节点超时三路须完整。仅WebApp交互，访问权限、提交／恢复和平台全局过期尚未验收；通用入口暂不导入或运行含此节点的成果，纯模板专用资源方案需另行批准后执行，实际平台联调尚未验收；不自动提交人工决定或发送通知。'


def references(config):
    text=config.get('form_content','')
    return [m.group(1).split('.') for m in re.finditer(r'\{\{#(.*?)#\}\}',text)] if isinstance(text,str) else []


def validate(config,mode):
    errors=[]
    if mode!='workflow':errors.append('首批人工审核只支持Workflow根节点，不自动换Chatflow／Agent类型。')
    if not isinstance(config,dict) or set(config)!=FIELDS:return errors+['人工审核须完整form_content/inputs/user_actions/timeout/timeout_unit/delivery_methods，不补默认或丢字段。']
    text=config['form_content']
    if not safe_text(text,16000) or not text.strip():errors.append('人工审核须有最多16000字符的非空审核对象说明，不填写凭据。')
    elif text.count('{{#')!=len(re.findall(r'\{\{#(.*?)#\}\}',text)) or any(len(ref)!=2 or any(not re.fullmatch(r'[\w-]+',v) for v in ref) for ref in references(config)):errors.append('审核说明仅使用明确二段上游文字引用，不忽略残缺引用、子路径或$output输入占位。')
    if config['inputs']!=[] or not isinstance(config['inputs'],list):errors.append('首批仅审核动作，没有补充输入／选择／文件表单，不清空字段后通过。')
    actions=config['user_actions'];ids=[]
    if not isinstance(actions,list) or len(actions)!=2:errors.append('首批须明确approve和reject两个动作及其显示标题，不猜其他动作或删除。')
    else:
        for action in actions:
            if not isinstance(action,dict) or set(action)!={'id','title','button_style'}:errors.append('审核动作须完整id/title/button_style，不补默认或忽略额外字段。');continue
            ids.append(action['id'])
            if not safe_text(action['title'],100) or not action['title'].strip() or not isinstance(action['button_style'],str) or action['button_style'] not in {'primary','default','accent','ghost'}:errors.append('动作须有明确标题和已支持按钮样式。')
        if any(not isinstance(v,str) for v in ids) or set(v for v in ids if isinstance(v,str))!={'approve','reject'}:errors.append('首批动作ID仅approve/reject，分别对应明确批准／拒绝，不自行改名或映射。')
    timeout=config['timeout'];unit=config['timeout_unit']
    if not isinstance(unit,str) or unit not in {'hour','day'} or type(timeout)is not int or not 1<=timeout<=(72 if unit=='hour' else 3):errors.append('须明确1—72整数小时或1—3整数天的节点等待上限，布尔／文字不转换；平台全局过期仍需环境核对。')
    methods=config['delivery_methods']
    if not isinstance(methods,list) or len(methods)!=1:errors.append('首批只允许一个明确启用的WebApp交互方式，不默认邮件或忽略其它送达方式。')
    else:
        row=methods[0]
        if not isinstance(row,dict) or set(row)!={'id','type','enabled','config'} or row.get('type')!='webapp' or row.get('enabled') is not True or row.get('config')!={}:errors.append('WebApp送达须明确id/type=webapp/enabled=true/config={}，其它服务与身份限制尚未适配。')
        else:
            try:uuid.UUID(row['id'])
            except (ValueError,TypeError,AttributeError):errors.append('WebApp送达方式须有明确UUID，不生成或替换原ID。')
    return errors


def native(config):return {'version':'1',**copy.deepcopy(config)}


def preserved(data):
    if data.get('version','1')!='1' or set(data)-FIELDS-{'type','title','desc','selected','version'}:raise ValueError('原人工审核有未适配版本／执行字段，不删除后冒称保留。')
    cfg={key:copy.deepcopy(data.get(key)) for key in FIELDS};errors=validate(cfg,'workflow')
    if errors:raise ValueError('原人工审核无法保留：'+'；'.join(errors))
    return cfg


def has_review(plan):return isinstance(plan,dict) and isinstance(plan.get('nodes'),list) and any(isinstance(n,dict) and n.get('type')=='human-input' for n in plan['nodes'])
