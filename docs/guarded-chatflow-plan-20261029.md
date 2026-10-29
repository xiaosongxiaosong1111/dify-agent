# 独立业务非空守卫后的完整Chatflow新批382（未批准）

380已新直接执行并消费：原版前五例/轨迹passed，缺号首轮回复不符即停，未发补号第二轮/修改版/ZIP。235控制成功但空白订单的旧图反例，保留严格提取成功条件、另加独立查询前非空代码/IF，83定向和359保护部署通过。没有改旧Task/App/期望。[真实进展](complete-policy-live-result-20261029.md)、[修复](order-value-guard.md)。

382是独立完整新范围，不重放/改授/借用旧375/376/378/380。固定359售后19节点/19边模板，合同强制保留上下文占位符、政策完整性提示、validate_order代码及check_order_value路由，不能退回旧17节点图或加查询捷径。分类/提取/回答在Dify内部仍调用模型；搭建模型0，不是模型自主访谈规划、一次浏览器全链或全§11/25签收。

通过正常产品API新Task1，原21保持：原公开需求/config→主动采用模板→复核确认→构建→新App首次发布/专属Key→六例→逐轮原生轨迹和交付。六例及原期望不变：政策命中含ZXRET715/七天/未拆封、未收录政策固定无答案、范围外固定澄清、模拟订单有/无、缺号固定追问后同会话只补DEMO-001。不同样例新会话。[完整输入和规则](../tools/guarded-chatflow382/fixture.json)。

有效订单的实际轨迹必须含extract_order/check_order/validate_order/check_order_value/order_lookup/order_answer；缺号首轮必须固定追问且不得有order_lookup，无论是提取失败还是提取成功但业务空白。只看回复文字不足以通过。先核输出规则，规则失败不为诊断继续读取；原生轨迹按正常产品接口采集，异常发现即停止。

原版全部通过后，正常修改需求/重新复核确认，只在无答案固定模板和回答系统提示两处同步增加“商品型号”；其它完整图含非空守卫保持。新第二App/发布/Key，再六例与逐轮轨迹、双ZIP。每版6启动/7物理Service（最后例两轮），共12启动/14Service/14轨迹。打包flags=false，平台证据另列；执行/当前发布/本地核心图匹配不证明不可变发布版本关联。无答案的空检索和有片段不足分别记录。

| 项 | 当前保守上界 | 本批全部新增最多 | 拟新保守上界 |
|---|---:|---:|---:|
| Sierra模型HTTP | 30 | 0 | 30 |
| 管理GET | 957 | 128 | 1085 |
| 加密登录 | 41 | 1 | 42 |
| App / 首次发布 / Key | 各18 | 各2 | 各20 |
| 物理Service | 64 | 14 | 78 |

新Task累计12启动/45分钟，整批60分钟；若完成则22Task。固定deepseek-flash/thinking=false/温度0.2/输出512、记忆最近5轮；复用FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1，TopK3/无阈值/不重排，不建库、不覆盖旧App。新Key切原专用连接，旧Key加密归档；原空间固定，复用加密凭据，不从聊天抄密码。

**Dify新增估算0.10 USD不是账单硬封顶，宿主费用未知。** 每个Service可能包含多个模型/检索/代码节点，不能当供应商内部HTTP封顶。主Sierra模型账本0.755473652和六settled/旧unknown/全部费用保持；375余105读/资源1/13Service、378余115/1/13、380余95/1/8都不退借，376无剩余。

任何技术/认证/来源/图/规则/会话异常整批停止并消费，不循环登录/重试/阶段恢复/放宽原期望，未派发槽和估算不自动返还。原21/密文资产及346旧消费精确绑定，环境仅正常令牌及授权新运行Key切换；旧任务和历史结果不改判。

41项门禁通过，包括上下文/政策完整性和新业务守卫缺失、替换代码或查询捷径拒绝。15个公开独立临时21Task协议场景通过，新增“成功但空单号固定追问”的正例和“输出正确却绕过守卫轨迹”的反例；正常两版0搭建模型/80读/1登录/资源各2/14Service/14轨迹/双ZIP。其它覆盖认证/导入/发布/Key/Service/规则/消息会话/主动停止等；异常请求序列是正常序列前缀。真实HTTP0、源前后摘要一致，不证明真实模型遵循。

验收：`python -m pytest backend/tests/test_guarded_chatflow_boundary.py -q --basetemp work/NEW-GUARDED-GATES`；`python tools/guarded-chatflow382/rehearse.py work/NEW-GUARDED-REHEARSAL`；冻结后`python work/guarded-chatflow382/execute.py validate`。均使用项目.venv，仅定向不全量。

只读预检原21/346旧证据、359-17860f0f9043dfa61c21/PID4028/289源快照及原Docker16服务健康通过；未登录或调用Dify HTTP。[安全摘要](guarded-chatflow-preflight-20261029.json)。

最终work/guarded-chatflow382，15哈希条目另加manifest。plan SHA256 `ef8db0f7ffa722ac13c47cbf7b62c068bbc60c0188ba2dd8a0ee1f6ab1235830`；manifest SHA256 `e15eef199d606488c98eae563c15d4de532dffde7e503009ca6909b5759eb951`。当前无approval/attempt/真实请求。

新直接用户答复绑定最终摘要及全部新增次数/资源/费用后才写approval并唯一canonical非优化execute.py live；来源/冻结/旧证据/运行变化拒绝，Docker未就绪不消费或登录。全部新增范围超出现有明确边界，按[AGENTS.md](../AGENTS.md)“within existing explicit resource and cost bounds”须直接批准；常规委托或旧批批准均不代替。
