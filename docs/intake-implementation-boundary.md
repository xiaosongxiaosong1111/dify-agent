# 访谈的技术实现与业务决定边界

0.266针对第76项实际访谈仍反复索要已有技术规则的问题：Workflow需求检查的系统消息现在直接带程序生成的当前Sierra入口契约，与访谈／规划共用同一来源。它只能解释用户已经提出的行为如何由Sierra本机接口覆盖，不能替用户补业务决定或声称Dify直调已经验证；其他类型、只读讨论不继承这段访谈指令。

用户已经说明必填文本空白拒绝、失败停止且没有特殊入口或自定义错误要求时，不把相同strip判空、HTTP错误与成功result分离当成需要用户重述的决定。明确条件可由支持的类型／比较器／连接无歧义表达时，写法留给规划；“结果集合非空”不被扩成“文本也必须有效”这一额外业务条件。类型未知、真实规则缺失／冲突、要求不同入口或错误合同、当前能力不能满足时仍澄清。

未改变准入处理器、证据来源契约或模型返回内容。24项定向检查（41未选）通过，覆盖实际模型消息中的可信技术事实、用户文字不能篡改这些事实、其他应用／只读讨论隔离、既有422／502行为对照和真正缺口仍阻断。两条API替身回放：第76项原始问题和需求逐字保留且确认仍422；正常替身可进入待确认草案，但不自动确认／构建／创建资源。这些检查均无实际模型／Dify调用，不能证明实际语义已改善。

部署0.266.0-80e68e15c4f9cb2cd3e2，健康200，源码与快照匹配。仅运行文件assistant_scope_prompt.py、main.py和intake-model-contract.md变化；原14任务／全部对象密文／主密钥／第76及更早包保持，前端未改，无全量测试。

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_assistant_scope_prompt.py backend/tests/test_planning_entry_context.py backend/tests/test_intake.py -k "scope or catalog or test_workflow or test_new_entry or test_readonly_discussion or test_at01_nonempty_but_unresolved_topic_blocks_confirmation" -q -p no:cacheprovider --basetemp=work/pytest-boundary-fresh
.venv\Scripts\python.exe work/intake-boundary266-check.py
```

测试使用专用空FLOWCRAFT_DATA_DIR和未存在basetemp。[本机安全结果](intake-implementation-boundary-result-20261024.json)。随后第79项新范围直接批准后，首轮实际访谈九主题和根代理12项内容核对通过，未再索要已有技术规则，精确回复／原规则／资源条件保持。这是当前公开合成单例的实际改善，不是一般语义保证；随后验证进程中断，第二模型未调用、完整连续链未完成。原回执及失败／未用预留保持，保守18/18，详见[实际结果](continuous-model266-result-20261024.json)。
