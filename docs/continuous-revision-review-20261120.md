# 连续自然语言改版：当前本机链核对

2026-11-20，BACKLOG342/交付清单04。FR11/24/38/40/41、AT19/24。DeepSeek只读核当前重规划上下文及候选采用，Codex独立读planning_context、两组关键API案例和主流程短段，并实际运行三组直接相关检查：`python -m pytest backend/tests/test_replanning_context.py backend/tests/test_replanning_context_api.py backend/tests/test_replanning_changes.py -q`，24 passed。

连续两次访谈修改进入当前requirements，原图匹配的非过期历史快照提供真正修改前基线，不取已经含部分改动的过期快照；原图无历史基线时明确未知。变化候选保留在planning_runs，不自动替换正式图/原成果/确认。正常页面可读取并明确载入，显式保存按当前修订生效，旧版先快照，相关确认/成果失效。

未证实新产品缺口，保留#319已有修复和当前采用机制，不重复开发，不添等价测试。人工编辑入口允许按当前修订提交明确文本，不强制它必须来自某条模型记录；这与页面候选来源核对是不同入口。此次24项是临时Store与模型替身，未新跑浏览器或真实模型/Dify，完整语义保留及自主双版仍未闭合。
