# 382实际：前五例及缺号追问通过，同会话补号失败即停

用户call_04cbd9d61092473791ace6e2ce29a0b1 q0直接批准后382唯一执行并消费。实际0搭建模型/33管理读/1登录/Task1/App首次发布Key各1/Service7，共44 HTTP。原版前五例及五份原生轨迹再通过，有效订单轨迹已包含validate_order/check_order_value；第六首轮固定追问passed，同会话补号第二轮却返回范围说明，evaluation=failed即停。未读失败例两轮轨迹、第二版或ZIP，无重试/规则放宽。

新Task `d000fee9-75b1-455b-ae31-1180a7475b40` r5/run_completed，App `4f568de2-3aec-4f5e-8890-f4d320fadac0`。当前22Task，原21/账本密文资产及346消费文件保持；专用运行Key切新App、旧Key加密归档。

第六run `c7160ca7-b76c-4886-868e-cbbe37606e12`：第一轮按原文“订单查询目前为模拟，请提供订单号。”，第二轮只输入DEMO-001，实际“目前只支持售后资料问答和模拟订单查询，请说明您的诉求。”，原预期仍为带模拟标记的已发货文字。两轮返回及传入conversation_id一致，排除本次客户端换会话；未读该两轮原生提示/轨迹，不能声称实际模型记忆内容已核实。

已对照Dify1.17.1固定依赖graphon0.7.0的[分类提示构建](https://github.com/langgenius/graphon/blob/v0.7.0/src/graphon/nodes/question_classifier/question_classifier_node.py#L543)：支持从memory构建历史并写入系统提示；本机编译图配置有界记忆。旧人工模板分类指令只说“只有明确订单查询才选order”，未明确“上一轮追问后只补编号”的接续情形。下一先补有限的会话接续分类说明，不把新会话孤立编号自动当订单，不更换会话/模型或改原输入期望；源码支持记忆不等于真实本次记忆已证实，效果仍需新批准观察。

保守上界1085读/42登录/资源各20/Service78，Sierra模型30/账本0.755473652保持。实际累计Sierra26/资源各15/Service36；本批6次Service规则命中（五单轮+缺号首轮）、5个完整样例通过，累计逐次规则命中30，不等于完整任务业务通过。旧unknown/六settled及全部费用保持，平台报价不是账单，Dify估0.10非硬限/宿主未知。

余95管理读/资源1/7Service保留不借退，旧375/376/378/380/382不重放。运行359/PID4028/289文件未变；新保护基线work/guarded-chatflow382/post-live-data-snapshot.json，不能直接套旧21全量相同的381保护。原§11完整连续会话、修改版和双交付仍未闭合。[逐轮输入/原期望/实际/用量及证据摘要](guarded-chatflow-live-result-20261029.json)。
