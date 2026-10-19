"""Reviewed official presets. Catalog presence is not account verification."""
import copy

VERIFIED_AT = '2026-10-10'
DEEPSEEK_PRICE = 'https://api-docs.deepseek.com/quick_start/pricing/'
OPENAI_MODELS = 'https://developers.openai.com/api/docs/models/'
QWEN_PRICE = 'https://www.alibabacloud.com/help/en/model-studio/model-pricing'


def model(id, label, api_model, description, input_rate, output_rate, *, cached=None, note='', profile=''):
    price = {'input_per_million_usd': input_rate, 'output_per_million_usd': output_rate}
    if cached is not None: price['cached_input_per_million_usd'] = cached
    return {'id': id, 'label': label, 'model': api_model, 'description': description, 'pricing': price, 'note': note, 'request_profile': profile}


VENDORS = [
    {'id': 'deepseek', 'name': 'DeepSeek', 'mark': 'D', 'base_url': 'https://api.deepseek.com', 'protocol': 'openai-compatible',
     'source_url': DEEPSEEK_PRICE, 'pricing_basis': '按官方峰值单价保守估算，不计非高峰折扣。',
     'models': [
         model('deepseek-flash', 'V4.1 Flash', 'deepseek-flash', '通用对话与流程规划，预设默认关闭额外思考。', .3, 1.2, cached=.006, profile='deepseek'),
         model('deepseek-v4-pro', 'V4 Pro', 'deepseek-v4-pro', 'Pro 系列，预设同样默认关闭额外思考。', 1.32, 3.96, cached=.044, profile='deepseek'),
         model('deepseek-v4-flash', 'V4 Flash（兼容入口）', 'deepseek-v4-flash', '保留旧模型名的接入选择。', .3, 1.2, cached=.006, profile='deepseek', note='官方已将此旧型号请求转到 V4.1 Flash，按 Flash 单价计费。'),
     ]},
    {'id': 'openai', 'name': 'OpenAI / GPT', 'mark': 'G', 'base_url': 'https://api.openai.com/v1', 'protocol': 'openai-compatible',
     'source_url': OPENAI_MODELS, 'pricing_basis': '按标准处理的长上下文档保守估算：输入／缓存为基础价 2 倍、输出 1.5 倍；短请求实际单价可更低。不含工具和缓存写入费用。',
     'models': [
         model('openai-gpt-6.1-sol', 'GPT-6.1 Sol', 'gpt-6.1-sol', '通用助手与复杂流程规划，使用低强度推理。', 4, 15, cached=.2, profile='openai-reasoning'),
         model('openai-gpt-6-luna', 'GPT-6 Luna', 'gpt-6-luna', '轻量任务与日常对话，默认关闭额外推理。', .2, .75, cached=.02, profile='openai-luna'),
     ]},
    {'id': 'anthropic', 'name': 'Claude', 'mark': 'C', 'base_url': 'https://api.anthropic.com', 'protocol': 'anthropic',
     'source_url': 'https://platform.claude.com/docs/en/models/sonnet-5-5/overview', 'pricing_basis': '官方标准文本单价，不含工具、缓存写入或加速模式。',
     'models': [
         model('claude-sonnet-5-5', 'Sonnet 5.5', 'claude-sonnet-5-5', '通用 Claude 助手，采用服务商默认推理设置。', 2, 10, cached=.1),
         model('claude-opus-5-5', 'Opus 5.5', 'claude-opus-5-5', 'Opus 系列，适合需要更多推理的工作。', 4, 20, cached=.2),
     ]},
    {'id': 'qwen', 'name': '通义千问（北京区）', 'mark': 'Q', 'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'protocol': 'openai-compatible',
     'source_url': QWEN_PRICE, 'pricing_basis': '按北京区最高常规输入档的 USD 参考价保守估算，不计活动或缓存折扣。其他地域 Key 请使用自定义接入。',
     'models': [
         model('qwen3.7-plus', 'Qwen3.7 Plus', 'qwen3.7-plus', '使用北京区百炼 Key，默认关闭额外思考。', .826, 3.301, profile='qwen'),
         model('qwen3.6-plus', 'Qwen3.6 Plus', 'qwen3.6-plus', 'Qwen3.6 系列，使用北京区百炼 Key。', 1.101, 6.602, profile='qwen'),
     ]},
]


def get_preset(preset_id):
    for vendor in VENDORS:
        for choice in vendor['models']:
            if choice['id'] == preset_id:
                return copy.deepcopy({**choice, 'provider': vendor['id'], 'base_url': vendor['base_url'],
                                      'protocol': vendor['protocol'], 'name': vendor['name'] + ' · ' + choice['label'],
                                      'pricing_note': f'官方参考价，核对日期 {VERIFIED_AT}。{vendor["pricing_basis"]} 估算不是账单。',
                                      'source_url': vendor['source_url']})
    raise ValueError('该预设型号不存在，请刷新模型列表或选择自定义接入。')


def matches(provider, preset):
    return all(str(provider.get(k, '')).rstrip('/') == str(preset[k]).rstrip('/') for k in ('base_url', 'model', 'protocol', 'provider'))


def runtime_profile(provider):
    if not provider.get('preset_id'):
        # Older official DeepSeek entries predate preset_id. Apply the same
        # reviewed request adaptation, without guessing from model names or
        # mutating the saved connection, credential or price configuration.
        normalized={**provider,'protocol':provider.get('protocol','openai-compatible')}
        for vendor in VENDORS:
            if vendor['id']!='deepseek':continue
            for choice in vendor['models']:
                preset=get_preset(choice['id'])
                if matches(normalized,preset):return preset['request_profile']
        return ''
    preset = get_preset(provider['preset_id'])
    if not matches(provider, preset):
        raise ValueError('预设与实际服务地址／模型不一致，请重新选择预设或改为自定义接入。')
    return preset['request_profile']


def catalog():
    return {'verified_at': VERIFIED_AT, 'vendors': copy.deepcopy(VENDORS), 'availability': 'account_unverified'}
