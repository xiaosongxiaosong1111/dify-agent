# 访谈候选新增主题与失败诊断（0.347，第199）

198真实首轮响应的补丁新增了知识库检索，却仍只交原8项检查；后端按候选算9项后正确拒绝，执行器又访问空复核而遮盖原因。完整候选离线核对还发现追问字段写成manualWork，原契约要求manual_work；这是本次先被主题数量挡住的后续结构问题。旧响应和消费包不改、不重新提交。

提示现在区分更新前清单和候选最终清单，提供来自同一PATTERNS的可触发专项ID/标签/正文规则，说明拟议、needs_input也要覆盖新场景；目录不是必选全集，不能新增业务凑行数。追问的精确字段名也作为结构目录提供。验证器未放松：原8项响应继续拒绝，补齐9项但字段错误或来源不存在仍拒绝；合法且有缺口的候选只保存待追问，不确认、不建流程。

源码检查器在HTTP200后检查本轮是否实际应用，有新失败记录时只输出安全的确定性数量诊断或通用停止说明，不复制模型正文；旧复核不能遮盖新失败，成功复核绑定origin_revision及本轮消息来源。空复核、过期复核或来源变化立即停止，不进入后续复核或HTTP。新增interview-result.cjs列入源码完整文件集合；已消费work/c1-mainline354原15文件和所有摘要保持，源码修复不构成新冻结或真实授权。

验证：37项后端（新增8/相关29）及9项Node检查通过；完整隔离界面链model5/read32/login1/import-publish-Key各2/run4通过，仍为替身/结构复核，不是语义验收。第二轮替身HTTP502场景在complete_interview停止，合计model2各阶段唯一/管理2/登录1/后续资源运行0，无自动重试。生产18Task、账本、密文资产及全部旧消费包保持，新增真实模型/Dify HTTP0，未跑全量。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_intake_candidate_topics.py backend/tests/test_intake_contract_feedback.py backend/tests/test_intake_runtime_scope.py backend/tests/test_contract_preflight.py -q -p no:cacheprovider --basetemp work/pytest-intake355
node --test tools/check_c1_interview_result355.cjs
```

受管理部署0.347.0-1b052af3a24e6f1d591e，287文件；原PID21864归属及原快照/执行文件核实后使用原stop/start，当前PID3348，health/前端200且源码/快照摘要一致。证据work/intake355-ui-final、work/intake355-ui-model-stop和work/intake355-deploy/deployment-proof.json；最新生产保护基线为该目录post-deploy-data-snapshot.json。

提示改进不能保证真实模型遵从；C1仍未通过，不把替身链当真实质量改善，也不复用剩余4模型槽。C2保持固定公开继续范围已关闭；下一整理C3逐项真实证据和受限结论，不自动扩大范围。
