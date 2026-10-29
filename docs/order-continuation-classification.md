# 售后分类明确会话内补号接续（0.360）

382真实两轮使用同一conversation_id：缺号首轮固定追问passed，第二轮只补DEMO-001却返回范围说明，原规则failed后永久停止。未读该例原生提示/轨迹，不断言本次模型实际看到哪些历史。[真实结果](guarded-chatflow-live-result-20261029.md)。

固定Dify1.17.1依赖graphon0.7.0的[分类提示构建](https://github.com/langgenius/graphon/blob/v0.7.0/src/graphon/nodes/question_classifier/question_classifier_node.py#L543)支持把记忆历史写入提示；本机配置开启有界记忆。旧模板未明确“前轮追问后只补编号”的分类接续，并要求只有明确查询才选订单。

此次只修改售后模板order类别说明和分类instruction：结合本会话历史，订单查询追问后仅补订单号仍归order；无订单上下文时，孤立编号不自动当订单；明确的新资料/范围外诉求不被旧订单话题覆盖。没有硬编码样例编号、增加状态架构或改变模型/记忆窗口/类别ID/默认澄清。19节点/19边、业务非空守卫和原全部试跑期望保持。

实际382失败作为复现；89项相关售后/样例/两轮/分类/记忆/原生保留定向通过，只验证配置、静态编译和正常API，不伪造模拟模型分类通过。真实新模型是否遵循接续指令仍待新批准观察，提示不是质量保证，旧22Task/App不自动迁移。

核359/PID4028归属后原stop/start部署360-b8edf5ed1f3251b03bed，289源快照匹配、新PID26172/前后端200；22Task/账本密文资产及367消费文件精确保留。新保护基线work/order-continuation383/post-deploy-data-snapshot.json，模型/Dify HTTP0。[部署摘要](order-continuation-classification-result-20261029.json)。
