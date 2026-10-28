# 搭建前逐项复核误触发批量（0.349，第207）

206真实完整需求说明和候选goal都含“先整理草案和逐项核对，待我／用户确认再搭建”。旧batch文本规则直接匹配逐项，把Sierra搭建前复核误当应用批量业务，当前标准10行而实际应基础8＋retrieval共9行。原公开案例每次只处理一个问题，没有批量要求。

仅在批量主题匹配前，排除这一明确搭建前草案语句的逐项含义；不修改保存的原需求／消息／引文。其它主题按原文字核对，真实逐项核对订单、处理工单、多条／数组／批量、既有迭代图仍查batch；不广泛删除逐项，不放宽数量或来源校验。模型收到同一明确规则，避免为错误标准补不存在的业务。

另明确提示questions同topic最多一问，多缺口合并，只挑1—3优先主题。程序仍严格拒绝重复，不自动合并；给出固定“追问主题重复”诊断，不回显未知模型topic。离线对206保留完整候选复核，修复后9主题匹配，但三条rules追问仍被严格拒绝，原候选和历史失败未修改或应用。其业务澄清也未被自动采纳。

18新增及76相关共94项定向检查通过，覆盖原公开说明、引文不变、真实批量/迭代保护、数量/来源/重复追问及正常API保存未确认草案。全部临时Store及固定模型响应，实际模型/Dify HTTP0，未全量。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_intake_prebuild_review.py backend/tests/test_intake.py backend/tests/test_intake_runtime_scope.py backend/tests/test_intake_contract_feedback.py backend/tests/test_intake_candidate_topics.py -q -p no:cacheprovider --basetemp work/pytest-prebuild361-final
```

0.349.0-602bce0b6435996a669b/287文件，按原26424/348快照及执行文件归属验证后原stop/start部署，现PID5540；health及前端200、源码/快照字节匹配。206停止后18任务（含r5真实首访谈和新两笔费用）、所有密文资产、旧360/357/354等全消费回执保持，只更新server.pid。最新基线work/prebuild361/post-deploy-data-snapshot.json。[安全结果](prebuild-intake-review-result-20261028.json)。

当前C1仍未完整通过，首轮真实访谈可以保留为后续续做证据。不能因代码已修而重放360、继续旧阶段或动用余下3模型槽；旧失败及预留保持。未来范围应复用已有进度、按正常产品门禁明确核对，不把代理人工声明当模型或人类验证。
