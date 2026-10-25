"""Task-list projection only; full task reads remain explicit and backward compatible."""
def summaries(store):
    return {'schema_version':1,'view':'summary','items':store.task_summaries(),
            'note':'列表只含任务标识、名称、类型、修订、已保存状态与更新时间；对话、材料、配置和成果按选择读取。状态不等于业务已验收。'}
