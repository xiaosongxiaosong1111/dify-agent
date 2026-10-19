"""Group saved attempts without changing their ledger or measuring quality."""
import hashlib,json,math
from decimal import Decimal,InvalidOperation,localcontext
from .planning import validate_pricing

MAX_RECORDS=5000
MAX_GROUPS=100
NOTE='仅账本起始点后的Sierra助手调用，包含重试、失败、中断、旧修订和未知项；Dify运行、建库、连接测试及起始点前历史不在范围内。使用原用途、服务ID、型号、价格快照及文字／图像类别，不读取当前服务设置。返回正文不证明候选或业务通过；历史输入与难度不同，不是受控质量／成本比较，不能证明节省Token或建议自动换模型。金额估算、人工账单与预留分别列出，未知不按0计算；部分流式用量不当最终Token，不改变预算或账本。'


def decimal(value):
    if not isinstance(value,str) or len(value)>100:raise ValueError()
    try:number=Decimal(value)
    except InvalidOperation:raise ValueError() from None
    if not number.is_finite() or number<0 or number.adjusted()>60 or number.as_tuple().exponent < -30:raise ValueError()
    return number


def text(value,limit):
    if not isinstance(value,str) or not value or len(value)>limit or not value.isprintable():raise ValueError()
    value.encode('utf-8')
    return value


def pricing(value):
    rates=validate_pricing(value)
    if rates is None:return None
    normalized={key:decimal(str(rate)) for key,rate in rates.items()}
    return {key:'0' if rate==0 else format(rate.normalize(),'f') for key,rate in normalized.items()}


def metric():
    return {'calls':0,'returned':0,'failed_or_interrupted':0,'pending':0,'outcome_unknown':0,
            'estimated_usd':Decimal(0),'declared_bill_usd':Decimal(0),'known_cost_count':0,'unknown_cost_count':0,
            'held_usd':Decimal(0),'held_unknown_count':0,
            'tokens':{key:{'known':0,'missing':0} for key in ('input','output','total')},
            'elapsed_seconds':Decimal(0),'elapsed_missing':0}


def count(usage,*aliases):
    if not isinstance(usage,dict):return None
    values=[usage[key] for key in aliases if key in usage]
    if not values or any(type(value)is not int or not 0<=value<=10**12 for value in values) or len(set(values))!=1:return None
    return values[0]


def add(target,row):
    status=row.get('status');call=row.get('call_status')
    if status not in {'reserved','settled','unknown','reconciled'}:raise ValueError()
    target['calls']+=1
    if status=='reserved':target['pending']+=1
    elif call=='returned':target['returned']+=1
    elif call in {'failed_or_interrupted','interrupted_by_restart'}:target['failed_or_interrupted']+=1
    else:target['outcome_unknown']+=1
    charge=row.get('charged_usd')
    if charge is None:
        if status in {'settled','reconciled'}:raise ValueError()
        target['unknown_cost_count']+=1
    else:
        if status not in {'settled','reconciled'}:raise ValueError()
        key={'reported_usage':'estimated_usd','user_declared_bill':'declared_bill_usd'}.get(row.get('cost_basis'))
        if key is None:raise ValueError()
        target[key]+=decimal(charge);target['known_cost_count']+=1
    if status in {'reserved','unknown'}:
        if row.get('reserved_usd') is None:target['held_unknown_count']+=1
        else:target['held_usd']+=decimal(row['reserved_usd'])
    for key,aliases in [('input',('prompt_tokens','input_tokens')),('output',('completion_tokens','output_tokens')),('total',('total_tokens',))]:
        value=count(row.get('usage'),*aliases)
        if value is None:target['tokens'][key]['missing']+=1
        else:target['tokens'][key]['known']+=value
    elapsed=row.get('elapsed_seconds')
    if type(elapsed) not in (int,float) or not math.isfinite(elapsed) or not 0<=elapsed<=10**9:target['elapsed_missing']+=1
    else:target['elapsed_seconds']+=decimal(str(elapsed))


def public(value):
    return {key:format(item,'f') if isinstance(item,Decimal) else item for key,item in value.items()}


def summarize(ledger):
    entries=ledger.get('entries');size=len(entries) if isinstance(entries,list) else None
    base={'schema_version':1,'verification':'saved_assistant_ledger_grouping_only','business_quality_verified':False,
          'savings_verified':False,'network_requested':False,'ledger_changed':False,'automatic_retry':False,
          'state':'unavailable','record_count':size,'groups':[],'totals':None,'note':NOTE}
    if not isinstance(entries,list) or size>MAX_RECORDS:return {**base,'message':'账本结构不完整或超过5000条汇总上限；没有选取部分记录或把缺失项当0。'}
    groups={};seen=set();totals=metric()
    try:
        with localcontext() as context:
            context.prec=512
            for row in entries:
                if not isinstance(row,dict):raise ValueError()
                identity=text(row.get('id'),100)
                if identity in seen:raise ValueError()
                seen.add(identity)
                provider=text(row.get('provider_id'),100);model=text(row.get('model'),200);kind=text(row.get('kind'),100)
                modality=row.get('modality')
                if modality not in (None,'text','image'):raise ValueError()
                rates=pricing(row.get('pricing'))
                source={'provider_id':provider,'model':model,'kind':kind,'modality':modality,'pricing':rates}
                digest=hashlib.sha256(json.dumps(source,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()
                if digest not in groups:
                    if len(groups)>=MAX_GROUPS:raise ValueError()
                    groups[digest]={**source,'id':digest,'metrics':metric()}
                add(groups[digest]['metrics'],row);add(totals,row)
            result=[{**row,'metrics':public(row['metrics'])} for row in groups.values()]
            return {**base,'state':'ready','groups':result,'totals':public(totals),'message':'已汇总读取时的完整本机账本；后续调用或账单登记后须重新读取。'}
    except (ValueError,TypeError,KeyError,UnicodeError,OverflowError,InvalidOperation):
        return {**base,'message':'存在重复／缺失标识、未识别状态或金额／价格超出本批精确汇总范围，或超过100个分组；未输出部分统计。原账本保持，可继续查看逐条来源。'}
