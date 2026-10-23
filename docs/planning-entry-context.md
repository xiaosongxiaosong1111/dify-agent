# 规划模型获知本机入口校验

0.263修复第65项实际规划暴露的上下文遗漏。规划请求现在说明：Sierra普通Workflow试跑按最终成果的start变量检查required文本，text-input/paragraph的缺失、非字符串和strip后空白会在派发前拒绝，不清洗原文；该说明不代表Dify直接调用/已发布应用入口已经验证。Agent不继承Workflow保证。既有规则能按契约无歧义实施时直接生成待复核图，真正缺失/冲突/业务费用体验取舍仍保留澄清。

本次没有改变原运行校验逻辑或替模型填业务答案。第65原HTTP1/needs_decision/无图失败保持；当前修改是否改善实际模型行为尚未验证，不能把固定模型替身的通过当模型成功。

新增定向4项将实际规划API捕获的上下文与真实本机运行门禁对照：两种文本类型、四类空白未派发且无运行记录，首尾空格和可选空白原样保留；真正缺失政策仍停下，Agent无跨类型保证。相关能力/澄清7项通过。旧能力测试的Agent替身改为返回原已存图，避免把目录测试混入改图确认门禁。没有全量测试。

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_planning_entry_context.py backend/tests/test_planning_capability_context.py -q -p no:cacheprovider --basetemp=work/pytest-planning-entry-unique
```

使用专用空FLOWCRAFT_DATA_DIR和未存在的basetemp；不要将测试数据指向生产。已部署0.263.0-169da3097967a3828842，运行快照仅backend/app/main.py变化，源文件摘要一致，13任务全部对象/密文/主密钥及旧失败和账本保持。当前r5耗尽时按钮仍停用。真实模型/Dify0。[安全证据](planning-entry-context-result-20261023.json)。
