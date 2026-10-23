# 访谈获知既有Sierra入口与错误契约

0.265修复73实际访谈暴露的上下文遗漏。访谈与规划共用一份Sierra普通Workflow入口说明：基于最终DSL的required文本用strip判空，派发前422且不写运行记录；明确平台失败终态502、任务error/记录failed、保存诊断，未知终态记录unknown而非成功。成功Workflow输出与Sierra HTTP错误分开；不假造错误result，也不保证Dify直接入口或实际节点路径。

这只是告知模型已有技术行为，不替用户决定自定义错误文案／结构。用户已给定ID/型号/参数并声明为后续条件时，未联网核对本身不再次成为需求缺口；仍须在配置/导入/运行前核对资源，不称就绪，真正缺值/冲突照常澄清。其他应用类型不继承Workflow入口保证。

23项定向检查通过（41未选，无全量）：实际访谈/规划消息均带对应契约，两种required文本的空白拒绝/原文保留、平台明确失败和未知终态HTTP/记录对照，以及真正业务缺口继续阻止确认。两条API替身回放表明旧73问题仍原样保留并阻止确认，没有在处理器删除模型问题；正确原文及可选风险只在回复时仍待确认。额外回放包装器修正路径/固定替身选取后通过，均真实出站0。

已部署0.265.0-da8b6413b9a732bf0ce1，源与快照匹配；运行仅main.py及intake-model-contract.md变化，14任务/全部对象密文/主密钥及旧73包保持。无实际模型或Dify请求；实际模型改善未验证，不能将替身通过称语义成功。

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_planning_entry_context.py backend/tests/test_assistant_scope_prompt.py backend/tests/test_intake.py -k "scope or catalog or test_workflow or test_new_entry or test_at01_nonempty_but_unresolved_topic_blocks_confirmation" -q -p no:cacheprovider --basetemp=work/pytest-entry-context-unique
.venv\Scripts\python.exe work/intake-entry265-check.py
```

使用专用空FLOWCRAFT_DATA_DIR和未存在basetemp，保持生产数据。模型保守14/14范围已消耗，继续实际验证必须另有直接新范围；旧71/73不可重放或退预留。[安全结果](intake-entry-context-result-20261024.json)。
