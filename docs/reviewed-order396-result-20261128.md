# 第396项：缺号订单意图修正副本与独立静态验收（2026-11-28）

DeepSeek先只读定位、再按Root审定业务文字实现三新文件；会话be969b2a-2444-4283-8293-fd5ec24bd55f，find/do正常0，宿主固定检查一次通过。Root完整读模块/必要编译代码及报告，独立19项测试通过，并对实际已保存两图纯编译通过。新副本未采纳到生产，不是模型自主重规划或实际分类通过。

确定的代码证据：question_classifier.native和preserved逐值保留instruction、classes和query selector，分类边也保持类别id出口；entry_probe不改sys.query。旧文字把“真实订单”列为范围外，并以“模拟订单/给出或明确要求查询订单号”描述order，与普通用户未提供号的状态查询存在语义冲突。395只有保存路径，没有模型判断理由，不能断言唯一因果或编译器错误。等待状态在非编号下一轮被消费是既有代码行为，本次未顺带修改。

Root决定只明确分类instruction：普通订单状态/物流查询不要求用户先提供号或先说模拟；下游缺号追问，查询仍全程模拟；明确要求接入/操作真实系统和范围外诉求仍拒绝，售后政策包含订单词不等于查某个订单，孤立编号没有上下文不自动当订单。原文与新文及后续代表性真实回归见[候选契约](order-intent396-candidate.md)。

工具`tools/reviewed_order_intent396.py`仅copy/json/math纯函数amend_pair，无IO/CLI/Store/网络或凭据访问。严格验证旧字段、三类id/名称/label、selector、fallback和输入pair仅两文案不同；未知/重复/已改instruction或额外结构/类型差异拒绝。深拷贝不改输入，每版只改classify.config.instruction。

实际根静态证明：

| 项目 | 摘要/结果 |
|---|---|
| 旧原图/改图 | dd71f629… / 3940d849…，真实r8旧图与静态包保持 |
| 新原图 | `2f2cc42643c83dd985e88a4e0bbe5fa931e36665bd2324a644ca0088c6c09f44` |
| 新改图 | `a046fd51b72806104db5fa05027b6dc372516e732f6c0f7e6b21d970f5528767` |
| 完整图/原生输出 | 两版各23节点24边；每版相对旧图仅分类instruction一字段，原生完整JSON亦仅该字段；新双版相对差异仍与旧双版两文案完全相同 |
| 保护 | 实际12根/944逐项保持，Task6225fa08…/预算/配置/期望/凭据不变；真实模型/Dify/Key读取0 |

19项命令：`E:/workSpace/dify-agent/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_reviewed_order_intent396.py`。根证据`work/reviewed-order396-root-tests.log`、`root-compiler-proof.json`、`root-saved-pair.log`；候选四份JSON及review.json在`work/reviewed-order396-candidates`，明确candidate_only、not adopted、真实质量未验。根独立脚本在项目外sierra-delegation，只执行一次并独占创建候选目录，不覆盖旧输出。

分类说明变化会影响所有分类案例，旧五个通过不能冒充新图通过。下一397由DeepSeek制作新的本机完整验收编排与可审查方案，重新覆盖两版全部六例七轮；保持旧App/回执，采用新App而非覆盖已发布旧图。必须重新计算累计Task启动、Service、资源、管理/登录和费用范围，现有12启动已用6，不可重置或自动借用未用槽；只有新直接批准后才能真实执行。
