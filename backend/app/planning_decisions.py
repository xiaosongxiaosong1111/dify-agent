"""Bounded model questions, never answers, approvals or an adopted plan."""
import json
from .plan_drafts import inspect_text

FIELDS = ('question', 'recommendation', 'reason', 'experience', 'cost', 'manual_work')


def summarize(value):
    report = {'schema_version': 1, 'verification': 'model_clarification_only',
              'message': '模型请求补充条件，但说明格式不完整，请核对原始响应。',
              'questions': [], 'incomplete': False, 'format_valid': True}
    try:
        inspect_text(json.dumps(value, ensure_ascii=False))
    except Exception:
        report.update(incomplete=True, format_valid=False,
                      message='模型的澄清内容未通过安全文字检查，未展开；请人工核对，不自动继续。')
        return report
    error = value.get('error')
    if isinstance(error, str) and error.strip() and len(error) <= 2000:
        report['message'] = error
    else:
        report.update(incomplete=True, format_valid=False)
    if set(value) - {'error', 'needs_decision'}:
        report.update(incomplete=True, format_valid=False)
    rows = value.get('needs_decision', [])
    if not isinstance(rows, list):
        report.update(incomplete=True, format_valid=False)
        return report
    if len(rows) > 20:
        report.update(incomplete=True, format_valid=False)
    for row in rows[:20]:
        if isinstance(row, str):
            row = {'question': row}
        if not isinstance(row, dict) or set(row) - {*FIELDS, 'id'}:
            report.update(incomplete=True, format_valid=False)
            continue
        if not isinstance(row.get('question'), str) or not row['question'].strip() or len(row['question']) > 2000:
            report.update(incomplete=True, format_valid=False)
            continue
        # IDs are model metadata, never task/approval IDs or action destinations.
        if 'id' in row and (not isinstance(row['id'], str) or not 1 <= len(row['id']) <= 128):
            report.update(incomplete=True, format_valid=False)
            continue
        if any(key in row and (not isinstance(row[key], str) or not row[key].strip() or len(row[key]) > 2000) for key in FIELDS[1:]):
            report.update(incomplete=True, format_valid=False)
            continue
        report['questions'].append({key: row.get(key, '') for key in FIELDS})
    return report


def history(task):
    """Whitelist saved questions for handoff; no raw model output or secrets."""
    note='仅为模型提出、尚未核实的问题；历史修订不是当前确认，不代表计划已采纳或Dify已运行。'
    result={'verification':'model_clarification_only','state':'ready','records':[],'note':note}
    def unavailable():
        return {**result,'state':'unavailable','records':[], 'note':note+' 历史结构或大小超出可导出范围；没有导出部分记录，请回到任务逐项核对。'}
    if type(task.get('revision')) is not int or task['revision']<1:return unavailable()
    runs=task.get('planning_runs',[])
    if not isinstance(runs,list) or len(runs)>5000:return unavailable()
    for position,run in enumerate(runs,1):
        if not isinstance(run,dict):return unavailable()
        if 'decision_report' not in run:continue
        source=run['decision_report'];revision=run.get('revision')
        if not isinstance(source,dict) or source.get('schema_version')!=1 or type(source.get('schema_version')) is not int or source.get('verification')!='model_clarification_only' or type(revision) is not int or revision<1:return unavailable()
        if type(source.get('incomplete')) is not bool or type(source.get('format_valid')) is not bool:return unavailable()
        rows=source.get('questions')
        if isinstance(rows,list):rows=[{k:v for k,v in row.items() if not(k in FIELDS[1:] and v=='')} if isinstance(row,dict) else row for row in rows]
        report=summarize({'error':source.get('message'),'needs_decision':rows})
        report['incomplete']=report['incomplete'] or source['incomplete'] or set(source)!={'schema_version','verification','message','questions','incomplete','format_valid'}
        report['format_valid']=report['format_valid'] and source['format_valid'] and not report['incomplete']
        result['records'].append({'planning_position':position,'input_revision':revision,'is_current_revision':revision==task.get('revision'),'report':report})
        if len(result['records'])>50 or len(json.dumps(result,ensure_ascii=False).encode('utf-8'))>256000:return unavailable()
    return result
