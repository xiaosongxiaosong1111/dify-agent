import re
from datetime import datetime

_UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_HEX64 = re.compile(r'[0-9a-f]{64}')
_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2})')

def _uuid(v):
    return isinstance(v, str) and _UUID.fullmatch(v) is not None

def _hex(v):
    return isinstance(v, str) and _HEX64.fullmatch(v) is not None

def _time(v):
    if not isinstance(v, str) or not 1 <= len(v) <= 64:
        return False
    if _TIME.fullmatch(v) is None or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in v):
        return False
    try:
        d = datetime.fromisoformat(v[:-1] + '+00:00' if v.endswith('Z') else v)
    except (ValueError, TypeError):
        return False
    return d.tzinfo is not None and d.utcoffset() is not None

def _ok(r):
    if not isinstance(r, dict):
        return False
    if not (_uuid(r.get('id')) and _uuid(r.get('reference_id'))):
        return False
    a = r.get('revision')
    b = r.get('previous_revision')
    if type(a) is not int or type(b) is not int:
        return False
    if a <= 0 or b <= 0 or a != b + 1:
        return False
    if not (_hex(r.get('document_token')) and _hex(r.get('configuration_sha256'))):
        return False
    return (_time(r.get('created_at')) and r.get('source') == 'merged_dsl_preview_model'
            and r.get('verification') == 'local_configuration_only'
            and r.get('pending_resource_review') is True)

def summarize(records):
    if not isinstance(records, list):
        return {'verification': 'local_adoption_history_only', 'total': None,
                'window_size': 0, 'shown': 0, 'invalid_in_window': 0,
                'truncated': False, 'unavailable': True, 'rows': []}
    total = len(records)
    window = records[-20:] if total > 20 else list(records)
    rows = []
    bad = 0
    for rec in reversed(window):
        if not _ok(rec):
            bad += 1
            continue
        rows.append({k: rec[k] for k in ('id', 'revision', 'previous_revision',
                                         'reference_id', 'document_token',
                                         'configuration_sha256', 'created_at')})
        rows[-1].update(source='merged_dsl_preview_model',
                        verification='local_configuration_only')
    return {'verification': 'local_adoption_history_only', 'total': total,
            'window_size': len(window), 'shown': len(rows), 'invalid_in_window': bad,
            'truncated': total > 20, 'unavailable': False, 'rows': rows}