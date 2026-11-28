# 第396项：订单意图分类 instruction 已审修正副本（本机、纯函数）

状态：本机人工审定副本，**未采纳到生产，未导入真实 Dify，未做真实模型验收**。旧 r8 图、944 父封存包、已消费 395 批次均未改动。本批不恢复真实执行，不是 Primary 模型调用，也不是模型自主重规划。

## 产物（仅此三个文件）

- `tools/reviewed_order_intent396.py`：内存纯函数，导入无副作用（只 import `copy`／`json`／`math`）。无 Store、模型、HTTP、CLI、配置或文件读写，不具备任何外部副作用权限。
- `backend/tests/test_reviewed_order_intent396.py`：合成图/假数据静态测试。
- `docs/order-intent396-candidate.md`：本说明。

## 唯一改动字段

两版本（original / modified）同步只改 `classify.config.instruction` 一个字段。以下全部原样保留、不修改：

- 类别 id／name／label 及顺序：`faq`／`order`／`out_of_scope`；
- `query_variable_selector=["sys","query"]`、`unmatched_policy={behavior:first_class,class_id:faq}`；
- 其它所有节点、边、代码、会话状态、模型参数、记忆、FAQ 内容、订单模拟接口、无答案文案；
- 未修旁支等待消费，未新增硬编码样例、关键词或字符串路由，未改期望。

两版本相对差异仍只有既有两处无答案文字：

- `no_hit_text.config.template`：`知识库暂无相关信息，请联系人工客服。` → `知识库暂无相关信息，请联系人工客服并提供商品型号。`
- `faq_llm.config.system_prompt` 中同一句子恰一次对应变化。

## 人工审定文字

旧值必须与已保存公开片段逐字相等（函数拒绝模糊替换／静默归一化）：

> 判断用户本轮诉求属于：1)售后资料／政策问答；2)查询模拟订单状态（用户本轮给出或明确要求查询订单号，或结合上文的订单查询话题）；3)其它范围外请求（例如预订、支付、真实订单、闲聊等）。没有订单上下文时，孤立的编号不要自动当作订单。

新值（Root 审定，逐字保留，不夹带待办或承诺）：

> 按用户本轮的主要业务诉求分类：faq为售后资料、政策和规则问答，即使提到订单也不等于查询订单状态；order为查询某个订单的当前状态、物流或发货进度。普通订单查询无论是否提供订单号、是否说“模拟”，都进入order；缺号由后续流程追问，不得因缺号或未说“模拟”判为范围外。所有订单查询始终使用模拟接口，归入order不表示接入真实系统。out_of_scope为预订、支付、闲聊等不支持的诉求，以及明确要求连接、接入或操作真实订单系统或外部真实订单接口的请求；不要把普通订单查询等同于这种真实系统接入要求。没有订单上下文时，孤立编号不要自动当作订单查询。

## 纯函数契约

`amend_pair(original, modified) -> (original_copy, modified_copy)`

- 两个输入都必须是严格 JSON 计划对象；拒绝 NaN／Infinity、元组等非 JSON 类型、非字符串键、循环引用。
- 每个输入须有唯一 `id=classify`／`type=question-classifier` 节点，且旧 instruction、三类 id／name／label、`["sys","query"]`、首项 faq 的 unmatched policy 逐值相符；缺失、重复、类型错误、未知或已修改 instruction 一律拒绝。
- pair 以严格 JSON 规范化比较：仅允许上述两处无答案文案不同；数值类型（如 `1` vs `1.0`）、布尔、代码、参数、边、节点顺序等其它差异一律拒绝。
- 不修改输入；输出为深拷贝，各自相对输入仅 instruction 一字段变化，pair 相对仍只有原两文案差异；不向图本体新增包装元数据。

输入完整 SHA 由 Root 在调用前绑定：original 为 `dd71f629c0d6a1e82d8e88aa424341fbe751369fbe0cedf19a9f1b5f44198c69`，modified 为 `3940d849…`（Root 绑定的完整值）。本纯函数不内置隐藏 SHA 校验、force 开关或审批机制。

## 定向验收

```
E:/workSpace/dify-agent/.venv/Scripts/python.exe -m unittest discover -s backend/tests -p test_reviewed_order_intent396.py
```

静态测试覆盖：单字段差异、双版原两差异、输入不变、数字／布尔／Unicode／代码／参数未改、缺失／重复／漂移／selector／未知 instruction 拒绝、非 JSON 拒绝。**它只证明所审文字与结构，不证明真实模型分类质量，也不构成平台或业务验收。**

## 待新独立批批准的真实回归清单

| 场景 | 静态／假模型可证明 | 需新真实批准 |
| --- | --- | --- |
| 明确订单缺号：“我想查询订单状态，但尚未提供订单号。” | instruction 措辞、order 分支存在 | 模型是否归 order、追问与等待是否触发 |
| 首轮直接给号：DEMO-001 | 图运行前无等待，仍走分类 | 模型归 order 与实际派发 |
| 等待后补号 | 代码节点 is_followup 逻辑可单测 | 真实会话状态与派发 |
| DEMO 编号孤立且无上下文 | instruction 含“孤立编号”约束 | 模型是否不当作订单 |
| 明确要求真实订单系统 | instruction 把此类列入 out_of_scope | 模型实际分类 |
| 售后政策含订单词 | instruction 明确“提到订单不等于查询状态” | 模型实际分类 |
| 范围外请求 | out_of_scope 分支存在 | 模型实际分类 |

上述真实项均需新的独立真实批批准；本批不做任何外部调用，不读取真实响应／历史检查点，不重放 395。

## 人工审阅说明

该 instruction 修正属人工审定副本，静态测试不保证实际分类效果；若后续改用其它措辞，必须重新走人工审阅与真实批批准，不能由模型或本工具自动改写字句。
