"""Read installed model rules before starting a persisted model operation."""
from pathlib import Path
from fastapi import HTTPException

NAMES={
    'workflow-plan-contract.md':'Workflow／Chatflow规划',
    'agent-plan-contract.md':'Agent规划',
    'intake-model-contract.md':'需求访谈',
    'case-model-contract.md':'验收样例建议',
    'configuration-model-contract.md':'配置建议',
    'coverage-contract.md':'范围核对',
    'conflict-contract.md':'冲突核对',
}


def load_contract(project:Path,name:str)->str:
    if name not in NAMES:
        raise HTTPException(422,'模型规则名称未适配，本次没有开始模型操作。')
    try:
        content=(project/'docs'/name).read_text(encoding='utf-8')
        if not content.strip():raise ValueError('empty contract')
    except (OSError,UnicodeError,ValueError):
        raise HTTPException(422,f'{NAMES[name]}规则未就绪，本次没有调用模型或改变任务。请恢复本机安装中的规则文件后再继续；不会使用空规则、旧缓存或自动重试。') from None
    return content
