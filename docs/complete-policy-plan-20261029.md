# 政策完整性修复后完整Chatflow新批380（执行前冻结方案）

当前：用户call_14745c342af64442b0c9a528431e8ba9 q0新直接批准后已唯一执行并消费；原版前五例和轨迹过，第六缺号首轮failed即停。下文按冻结前时点理解。[实际结果](complete-policy-live-result-20261029.md)。

378已按新直接批准执行，首例回答有编号却缺原规则适用条件，永久消费并停止。232据实际保存结果补通用条件/编号/结论要求，52定向及358保护部署通过；没有改旧回答、规则或发布App。[实际失败](corrected-chatflow-live-result-20261029.md)、[358修复](policy-answer-completeness.md)。380是新独立完整范围，不重放、改授或借用旧375/376/378。

使用358售后人工17节点模板，合同同时强制retrieve.result→`{{#context#}}`提示引用，以及政策适用条件/编号/结论明确要求。只按资料回答，不硬编码政策事实，thinking=false/0.2/512、记忆最近5轮；复用原FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1、TopK3/无阈值不重排，不建库。分类/提取/回答在真实Dify运行中仍调用模型；搭建模型0，不宣称模型自主访谈规划或全§11/25项验收。

通过正常产品API新Task1，原20保持。原版复核确认→构建→新App首次发布/专属Key→六例→每轮原生轨迹/图来源→交付。六例仍为：政策命中（ZXRET715/七天/未拆封均须包含）、未收录政策编号固定无答案、范围外固定澄清、模拟订单存在/不存在、缺号固定追问后同会话只补DEMO-001。最后一例两轮，其余单轮；不同样例新会话，原所有期望不放宽。[完整公开输入及规则](../tools/complete-policy380/fixture.json)。

原版全部通过后，正常改需求并重新复核确认，仅两处同步无答案文案增加“商品型号”（no_hit固定模板和grounded_answer系统提示）；其它完整图含上下文/完整性要求保持。新第二App/发布/Key，再六例、逐轮轨迹和双ZIP。两版共12启动/14物理Service/14轮原生轨迹；静态ZIP flags=false，不改为实际业务通过。执行/当前发布/本地核心图一致不证明不可变发布版本关联。无答案可为空检索或有片段不足，分别记录。

| 项 | 当前保守上界 | 本批全部新增最多 | 拟新保守上界 |
|---|---:|---:|---:|
| Sierra模型HTTP | 30 | 0 | 30 |
| 管理GET | 829 | 128 | 957 |
| 加密凭据登录 | 40 | 1 | 41 |
| App / 首次发布 / Key | 各16 | 各2 | 各18 |
| 物理Service | 50 | 14 | 64 |

新Task上限12启动/45分钟，整批60分钟；若完成则21Task。**Dify新增估算0.10 USD不是账单硬封顶，宿主费用未知**；Service可含多个模型/检索/代码节点，不能当供应商内部HTTP封顶。Sierra模型账本0.755473652不增，六settled0.132110088及旧unknown/所有费用保持。375剩105读/资源1/13Service、378剩115读/资源1/13Service及费用均保留，不退借；376无剩余。

固定原专用连接/原空间，复用已保存加密登录资料，不复制聊天密码；初始一次明确重连，后续认证异常停止，不循环登录。新Key切专用连接、旧Key加密归档，不覆盖旧App，原20Task/凭据资产及325旧消费证据保护。任何技术、来源、图、输出规则或会话异常整批停止并消费；不重试/阶段恢复/放宽规则，未派发槽和费用不自动归还。不能为了诊断继续失败后的步骤。

38项门禁通过：范围/来源/会话/一次消费/凭据保护，以及拒绝上下文遗漏或缺完整性要求的旧图；两版只有两处文案差异。13个公开独立临时20Task协议场景通过，正常精确0搭建模型/80管理读/1登录/资源各2/14Service/14轨迹/双ZIP；其它覆盖非空但不足、认证/导入/发布/Key/Service/规则/会话来源/主动停止，异常为正常序列前缀。全部真实HTTP0、源前后哈希一致，不证明真实模型遵循或业务质量。

验收：`python -m pytest backend/tests/test_complete_policy_boundary.py -q --basetemp work/NEW-POLICY-GATES`；`python tools/complete-policy380/rehearse.py work/NEW-POLICY-REHEARSAL`；冻结后`python work/complete-policy380/execute.py validate`。使用项目.venv。仅定向，不全量。

消费前只读预检原20/325旧证据、358-5b2b413df12148f3e015/PID572/289源快照及原Docker16服务健康通过；未登录或读取Dify HTTP。[安全摘要](complete-policy-preflight-20261029.json)。

最终目录work/complete-policy380，15哈希条目另加manifest。plan SHA256 `0bad3a04f6ad0c7496a154c429376828b42aaa052c423ddb37b5654f34bfb257`；manifest SHA256 `7dea2ace6a50b72213a4a7f986c4443f468c86cf4ccc9c07bb3b2dcae7fdfb37`。当前无approval/attempt/真实请求。

新直接用户答复绑定最终摘要及全部新增资源/次数/费用后才写approval并唯一执行canonical非优化入口；来源/冻结/旧证据/运行变化拒绝，本机Docker未就绪则不消费或登录。该完整新范围超过既有明确边界，按[AGENTS.md](../AGENTS.md)“within existing explicit resource and cost bounds”须直接批准；常规委托和旧375/376/378批准不能代替。
