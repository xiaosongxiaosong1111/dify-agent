"""Pinned visual schedule declarations; no scheduling or Dify resource writes."""
import copy,re

ROOT_ENTRY_TYPES={'start','trigger-schedule'}
TIMEZONES={'UTC','Asia/Shanghai'}
FREQUENCIES={'hourly','daily','weekly','monthly'}
FIELDS={'mode','frequency','visual_config','timezone'}
WEEKDAYS={'sun','mon','tue','wed','thu','fri','sat'}
RUNTIME_LIMIT='定时触发支持生成、静态检查与下载，以及已有发布应用的只读核对和单触发器启停方案。通用入口尚未适配定时发布闭环；专用三节点纯文字方案可另行批准新建发布并尝试停用，发布可能直接激活，真实触发业务仍未验收；启用会持续调度，试跑预算不限制后续费用，需独立具体资源方案确认，不能用手动运行冒充定时成功。'


def validate(cfg,mode):
    errors=[]
    if mode!='workflow':errors.append('定时触发只适配Workflow，不能改变Chatflow／Agent类型。')
    if not isinstance(cfg,dict) or set(cfg)!=FIELDS:return errors+['定时配置须完整mode/frequency/visual_config/timezone，不补造或忽略字段。']
    if cfg['mode']!='visual':errors.append('首批定时配置仅visual；任意cron／Webhook／插件触发尚未适配，不删行为后通过。')
    frequency=cfg['frequency'];zone=cfg['timezone'];visual=cfg['visual_config']
    if not isinstance(zone,str) or zone not in TIMEZONES:errors.append('首批须主动选择UTC或Asia/Shanghai；其他时区/DST尚未适配，不猜本机时区。')
    if not isinstance(frequency,str) or frequency not in FREQUENCIES:return errors+['须明确hourly/daily/weekly/monthly频次，不默认每日。']
    expected={'hourly':{'on_minute'},'daily':{'time'},'weekly':{'time','weekdays'},'monthly':{'time','monthly_days'}}[frequency]
    if not isinstance(visual,dict) or set(visual)!=expected:return errors+['visual_config须与当前频次完全匹配，不丢弃旧字段或混用政策。']
    if frequency=='hourly':
        if type(visual['on_minute']) is not int or not 0<=visual['on_minute']<=59:errors.append('小时触发分钟须为0—59真正整数，布尔／文字不转换。')
    else:
        if not isinstance(visual['time'],str) or not re.fullmatch(r'(?:0?[1-9]|1[0-2]):[0-5][0-9] (?:AM|PM)',visual['time']):errors.append('触发时间须明确原生12小时HH:MM AM/PM（1—12时），不猜时段。')
    if frequency=='weekly':
        days=visual['weekdays']
        if not isinstance(days,list) or not 1<=len(days)<=7 or any(not isinstance(day,str) or day not in WEEKDAYS for day in days) or len(set(day for day in days if isinstance(day,str)))!=len(days):errors.append('周触发须明确不重复的sun/mon/tue/wed/thu/fri/sat数组，不补默认周日。')
    if frequency=='monthly':
        days=visual['monthly_days']
        if not isinstance(days,list) or not 1<=len(days)<=32 or any(not (type(day)is int and 1<=day<=31 or day=='last') for day in days) or len({str(day) for day in days})!=len(days):errors.append('月触发日期为不重复的1—31真正整数或last；短月／月末语义须业务验收，不补默认1日。')
    return errors


def native(cfg):return {'version':'1',**copy.deepcopy(cfg)}


def preserved(data):
    if data.get('version','1')!='1' or set(data)-{'type','title','desc','selected','version','mode','frequency','visual_config','timezone','cron_expression'}:raise ValueError('原定时入口含未知版本/执行设置，不删除后声称保留。')
    if data.get('cron_expression') not in (None,''):raise ValueError('原定时入口含cron表达式，首批不忽略或改为visual。')
    cfg={key:copy.deepcopy(data.get(key)) for key in FIELDS}
    errors=validate(cfg,'workflow')
    if errors:raise ValueError('原定时配置无法保留：'+'；'.join(errors))
    return cfg


def has_schedule(plan):
    return isinstance(plan,dict) and isinstance(plan.get('nodes'),list) and any(isinstance(n,dict) and n.get('type')=='trigger-schedule' for n in plan['nodes'])
