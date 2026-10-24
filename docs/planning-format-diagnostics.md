# 模型候选格式错误与业务未决分别呈现

第84项模型将boolean条件的value写成JSON字符串"true"，已有严格校验正确拒绝，但规划器统一将非自动修复错误称为“需要人工确认”资源／业务问题，误导用户再次决定已有规则。

0.268只为根if-else中is／is not运算、boolean声明、value精确为字符串"true"或"false"，且全部诊断恰好是这些类型错误的候选，返回invalid_plan_format及明确中文说明。停止一次调用，原候选和类型保持，不自动转值、不采纳、不继续请求。混有其他结构问题、未知布尔文字、未知运算或真实模型澄清仍保持原处理，不把它们归成可忽略格式问题。

56项定向检查通过：两种字面量及0／3修复预算均只调用一次；真实validator确认原图无效、布尔类型的新测试副本有效；混合图错误／未知文字与坏运算仍停，真实缺条件仍保留needs_decision；API保留旧计划／修订／确认和一条费用记录。测试收集还发现planning_decisions使用了已更名的禁止外联fixture，改为实际存在名称后重验通过。未跑全量。

两条API替身回放中，旧84候选原样保留且仍422，使用新格式诊断；好替身可保存为未确认草案，但未确认构建仍422。原84回执不回填、不重放，本次不证明模型格式生成已改善。

已部署0.268.0-6b739828b437b14f1469，health200，源码匹配；运行仅condition_settings.py／planning.py／main.py变化。原14任务／所有对象密文／主Key及旧84和更早包保持，前端无需修改。实际模型／Dify新增0。[安全结果](planning-format-diagnostics-result-20261024.json)。

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_planning_format_diagnostics.py backend/tests/test_planning.py backend/tests/test_planning_decisions.py -q -p no:cacheprovider --basetemp=work/pytest-format-fresh
.venv\Scripts\python.exe work/planning-format268-check.py
```

使用专用空FLOWCRAFT_DATA_DIR及未存在basetemp。提示中的事实来源边界在84候选有局部改善，但完整图仍未通过；保守20/20范围已满，任何新实际模型调用需独立范围。
