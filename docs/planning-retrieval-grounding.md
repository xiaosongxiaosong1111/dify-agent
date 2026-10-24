# 规划的检索事实来源边界

第81项真实规划结构有效，但回答LLM提示把售后政策写成“资料补充”，允许模型在检索上下文外取得事实，违反用户“提示中只使用检索资料”。根代理在配置确认和构建前拒绝，未手改候选、不重试；真实图与失败回执保持。

后续第84项新范围中，回答提示已不再硬编码七天／未拆封／180天政策事实，只保留检索绑定、行为指令和编号示例，观察到局部改善；但完整候选因JSON布尔值类型错误未通过，未完成整体图内容核对或运行，不能称完整语义通过。[实际结果](grounding-planning267-result-20261024.json)。

0.267在Workflow／Chatflow规划系统提示及工作流契约中明确：当用户要求只据检索资料时，需求中的知识库内容介绍、政策事实、测试期望都不是独立回答来源；即使被整理进rules字段或附带“与检索冲突时以检索为准”，也不能硬编码到提示／模板／代码作为补充。角色、行为指令、变量绑定、字段名及明确固定回复可保留。用户明确允许静态事实时按其范围处理，与只检索要求冲突则澄清，不猜优先级。原生Agent不继承这段DAG规划指令。

没有增加通用关键词语义判错器，没有删除或自动修补模型图。24项定向（41未选）通过，包括实际规划消息包含当前来源边界、真正缺失仍返回needs_decision、既有本机入口行为及类型隔离。两条API替身回放中，旧81原图与已知好图均原样保存为未确认候选，未确认构建继续422；这说明处理器未强改答案，不证明实际模型已改善，也不把结构有效当业务正确。

已部署0.267.0-6a994909219eb1f54944，健康200；源码与快照一致，运行仅main.py及workflow-plan-contract.md变化。原14任务／所有对象密文／主Key／旧81和更早包保持。前端未改，未跑全量，本项实际模型／Dify新增0。[安全结果](planning-retrieval-grounding-result-20261024.json)。

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_planning_entry_context.py backend/tests/test_assistant_scope_prompt.py backend/tests/test_intake.py -k "scope or catalog or test_workflow or test_new_entry or test_readonly_discussion or test_at01_nonempty_but_unresolved_topic_blocks_confirmation" -q -p no:cacheprovider --basetemp=work/pytest-grounding-fresh
.venv\Scripts\python.exe work/grounding267-check.py
```

使用专用空FLOWCRAFT_DATA_DIR及未存在basetemp。实际语义核对仍须独立新范围，保守19/19已用满，旧81不重放。
