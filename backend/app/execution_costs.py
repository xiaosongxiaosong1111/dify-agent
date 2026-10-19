"""Read-only accounting of saved Dify usage; never a provider bill or budget."""
import re
import uuid
from decimal import Decimal, InvalidOperation

MAX_ENTRIES = 5000
NOTE = '只汇总本任务已保存的 Dify 试跑返回，包含旧修订和失败／未知结果；按币种分别合计已知金额，缺失不按零计算。Dify 报价不等于供应商账单，报价为 0 也不证明免费。未覆盖建库、连接测试、外部工具费用或未保存的运行；不计入 Sierra 助手预算，不实施运行费用硬上限。'


def amount(value):
    if type(value) not in (str, int, float) or len(str(value)) > 40:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return None
    if not number.is_finite() or number < 0 or number > 1000000 or number.as_tuple().exponent < -12:
        return None
    return format(number, 'f')


def tokens(value):
    return value if type(value) is int and 0 <= value <= 10**12 else None


def identifier(value):
    try:
        return str(uuid.UUID(value)) if isinstance(value, str) else None
    except (ValueError, AttributeError):
        return None


def reported(result, mode):
    result = result if isinstance(result, dict) else {}
    meta = result.get('metadata')
    metadata_usage = meta.get('usage') if isinstance(meta, dict) else None
    legacy_data = mode not in {'workflow', 'advanced-chat', 'agent'} and not isinstance(metadata_usage, dict)
    if mode == 'workflow' or legacy_data:
        data = result.get('data')
        usage = data if isinstance(data, dict) else {}
        price, currency = None, None
        basis = 'saved_data_tokens_without_type' if legacy_data else 'workflow_result_tokens_only'
    else:
        usage = metadata_usage
        usage = usage if isinstance(usage, dict) else {}
        price = amount(usage.get('total_price'))
        raw_currency = usage.get('currency')
        currency = raw_currency if isinstance(raw_currency, str) and re.fullmatch('[A-Z]{3}', raw_currency) else None
        basis = 'saved_metadata_usage_without_type' if mode not in {'advanced-chat', 'agent'} else 'dify_message_metadata_usage'
    total = tokens(usage.get('total_tokens'))
    prompt, completion = tokens(usage.get('prompt_tokens')), tokens(usage.get('completion_tokens'))
    token_conflict = total is not None and prompt is not None and completion is not None and total != prompt + completion
    return {'reported_amount': price, 'currency': currency, 'total_tokens': None if token_conflict else total,
            'prompt_tokens': prompt, 'completion_tokens': completion, 'token_conflict': token_conflict,
            'cost_known': price is not None and currency is not None, 'basis': basis}


def executions(run):
    result = run.get('result')
    if isinstance(result, dict) and result.get('conversation_case') is True:
        rows = result.get('turns')
        if not isinstance(rows, list):
            yield None, {}
            return
        for row in rows:
            index = row.get('index') if isinstance(row, dict) else None
            yield index if type(index) is int and 1 <= index <= MAX_ENTRIES else None, row.get('result') if isinstance(row, dict) else {}
        pending = result.get('pending_turn')
        if isinstance(pending, dict):
            index = pending.get('index')
            yield index if type(index) is int and 1 <= index <= MAX_ENTRIES else None, pending.get('result')
        elif not rows:
            yield None, {}
    else:
        yield None, result


def summary(task):
    from .run_diagnostics import remote_id
    groups, entries, overflow = {}, [], False
    for run in reversed(task.get('runs', [])):
        if not isinstance(run, dict) or run.get('kind') != 'run':
            continue
        for turn, result in executions(run):
            if len(entries) >= MAX_ENTRIES:
                overflow = True
                break
            mode = run.get('app_type')
            result = result if isinstance(result, dict) else {}
            info = reported(result, mode)
            remote = remote_id(result, mode)
            message = identifier(result.get('message_id')) if mode in {'advanced-chat', 'agent'} else None
            identity = remote or message
            app = identifier(run.get('app_id'))
            binding = run.get('environment_binding')
            trusted = isinstance(binding, str) and bool(re.fullmatch('[0-9a-f]{64}', binding)) and app is not None and identity is not None
            # Missing snapshots cannot be attributed to a current instance or deduplicated across records.
            key = (binding, app, 'workflow' if remote else 'message', identity) if trusted else None
            entry = {'run_id': run.get('id'), 'revision': run.get('revision'), 'environment_id': run.get('environment_id'),
                     'turn': turn, 'status': run.get('status'), 'app_type': mode, 'remote_id': identity,
                     'identity_verified': trusted, **info}
            entries.append(entry)
            groups.setdefault(key if key is not None else ('local', len(entries)), []).append(entry)
        if overflow:
            break
    charges, totals = {}, []
    for members in groups.values():
        prices = {(row['currency'], Decimal(row['reported_amount'])) for row in members if row['cost_known']}
        token_values = {row['total_tokens'] for row in members if row['total_tokens'] is not None}
        token_conflict = len(token_values) > 1 or any(row['token_conflict'] for row in members)
        conflict = len(prices) > 1
        known = len(prices) == 1
        currency, price = next(iter(prices)) if known else (None, None)
        if known:
            charges[currency] = charges.get(currency, Decimal(0)) + price
        totals.append({'sources': [{'run_id': row['run_id'], 'turn': row['turn'], 'revision': row['revision']} for row in members],
                       'cost_known': known, 'cost_conflict': conflict, 'currency': currency,
                       'reported_amount': format(price, 'f') if known else None,
                       'total_tokens': next(iter(token_values)) if len(token_values) == 1 and not token_conflict else None,
                       'token_conflict': token_conflict,
                       'identity_verified': members[0]['identity_verified'], 'remote_id': members[0]['remote_id']})
    return {'task_revision': task.get('revision'), 'scope': 'saved_dify_runs_all_revisions', 'verification': 'dify_reported_not_provider_bill',
            'entries': entries, 'executions': totals, 'record_count': len(entries), 'execution_count': len(totals),
            'duplicate_record_count': len(entries) - len(totals), 'unknown_cost_count': sum(not row['cost_known'] for row in totals),
            'cost_conflict_count': sum(row['cost_conflict'] for row in totals),
            'known_amounts_by_currency': {key: format(value, 'f') for key, value in sorted(charges.items())},
            'known_total_tokens': sum(row['total_tokens'] for row in totals if row['total_tokens'] is not None),
            'unknown_token_count': sum(row['total_tokens'] is None for row in totals), 'truncated': overflow,
            'note': NOTE + (' 本次超过 5000 条采集上限，仅汇总已展示的新记录，不能称为完整累计。' if overflow else '')}
