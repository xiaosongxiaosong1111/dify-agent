"""Explicit, bounded Chatflow history settings for Dify 1.17.1."""
def memory_configuration(mode,configuration):
    enabled=configuration.get('conversation_memory',False)
    turns=configuration.get('memory_turns',5)
    if not isinstance(enabled,bool) or isinstance(turns,bool) or not isinstance(turns,int) or not 1<=turns<=50:
        raise ValueError('对话记忆开关须为布尔值，历史窗口须为 1—50 的整数。')
    if enabled and mode!='advanced-chat':
        raise ValueError('对话记忆仅适用于 Chatflow，不会在 Workflow 中静默忽略。')
    if not enabled:return None
    # Dify queries a Message row for the unanswered current turn, then removes it.
    return {'query_prompt_template':'{{#sys.query#}}','role_prefix':{'assistant':'','user':''},'window':{'enabled':True,'size':turns+1}}
