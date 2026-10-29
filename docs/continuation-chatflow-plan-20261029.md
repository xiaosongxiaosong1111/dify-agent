# 360会话接续修复后完整新批384（执行前冻结方案）

当前：用户call_1983b4da729a48f3b85da8b5e243c0dd q0已明确批准全部范围及例外并唯一执行/消费；补号failed后已4GET捕获澄清分支并封存。下文按冻结前时点理解。[实际结果](continuation-chatflow-live-result-20261029.md)。

382新直接执行后前五例/业务守卫轨迹及缺号首轮原文追问过，同会话只补DEMO-001却返回范围说明，failed即封存。238仅补order类别和有限接续分类指令，89相关定向/360保护部署过，不硬编码编号或增加状态架构，旧Task/App/原期望不变。[真实失败](guarded-chatflow-live-result-20261029.md)、[代码修复](order-continuation-classification.md)。

384为独立完整新范围，旧375/376/378/380/382不重放、改授或借退。固定360售后19节点/19边，强制资料占位符、政策完整性、独立非空守卫，以及有订单追问上下文才接续补号/无上下文不猜订单的分类说明。真实模型遵循未验证；Sierra搭建模型0，Dify内部仍调用分类/提取/回答模型，不是模型自主访谈规划/一次浏览器全链/全§11或25项签收。

正常产品API新Task1，原22保持：公开需求配置/模板→复核确认→构建→新App首次发布/专属Key→六例/逐轮轨迹/交付。六例及原期望保持：政策命中含ZXRET715/七天/未拆封、未收录政策固定无答案、范围外固定澄清、模拟订单有/无、缺号固定追问后同会话只补DEMO-001。不同样例新会话，有效订单轨迹须经过业务非空守卫，缺号不得查询。[完整公开输入和期望](../tools/continuation-chatflow384/fixture.json)。

原版全部通过后正常改需求/重新复核确认，只两处无答案文案同步加“商品型号”，其它完整图/守卫保持；新第二App/发布/Key，再六例和逐轮轨迹/双ZIP。共12启动/14Service/14轮正常轨迹；本机ZIP flags=false不改为已平台/业务通过。执行/当前发布/本地核心图核对不证明不可变发布版本关联。空检索与片段不足兜底分别记录。

## 本新批唯一拟增的停止后诊断例外

仅当Service执行成功但保存的业务规则failed，立即停止后续发布、Key、Service和其它外部写入；随后只对**唯一已失败轮**，通过正常本机诊断接口保存**1份报告**，最多**4个管理GET**：原App下该消息→关联原生运行详情→节点→当前发布图，之后封存，不继续整批。多轮必须明确选失败轮；来源不明或歧义即停，不改选其它轮或猜ID。

这4次已包含在128管理GET总上限内，正常无失败时不额外读取。边界按唯一已返回消息/会话、原App和严格顺序限制，捕获期间禁止所有外部写入/Service/登录及其它GET。诊断失败不重试，部分请求也计数；原规则failed始终保持，不以诊断成功改判。技术/认证/来源异常立即停，不触发或重试此例外。本机报告/计数写入允许，原22业务保持。

**此例外未获批准，不能用于旧382或任何已消费包。** 必须与最终新摘要和全部范围一并取得直接用户批准；批准文件须明确同一failure_diagnostic_policy，否则执行前拒绝。目的只为新批失败时保留有限定位证据，不延长业务试跑。[受限请求边界](../tools/continuation-chatflow384/boundary.py)、[停止/捕获流程](../tools/continuation-chatflow384/journey.py)。

## 完整新增范围

| 项 | 当前保守上界 | 本批全部新增最多 | 拟新保守上界 |
|---|---:|---:|---:|
| Sierra模型HTTP | 30 | 0 | 30 |
| 管理GET（含失败例外） | 1085 | 128 | 1213 |
| 加密登录 | 42 | 1 | 43 |
| App / 首次发布 / Key | 各20 | 各2 | 各22 |
| 物理Service | 78 | 14 | 92 |

新Task累计12启动/45分钟，整批60分钟，若完成则23Task。固定deepseek-flash/thinking=false/温度0.2/最大输出512、记忆最近5轮；复用原FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1、TopK3/无阈值/不重排，不建库或覆盖旧App。只复用原空间加密凭据；新Key切连接、旧Key加密归档，不从聊天抄密码。

**Dify新增估算0.10 USD非账单硬封顶，宿主费用未知。** 一个Service可含多个模型/检索/代码节点，不能当供应商内部HTTP封顶。主Sierra模型30/账本0.755473652及六settled/旧unknown/所有费用不增不退借。375余105读/资源1/13Service、378余115/1/13、380余95/1/8、382余95/1/7均保留，376无剩余；本批不是旧槽改授。

57门禁通过，含失败政策不能扩为多报告/多读取/后续写入Service、未知消息或换会话拒绝、严格4GET顺序及唯一消费。17个公开独立临时22Task全链场景通过：正常两版0模型/80读1登录/资源各2/14Service/14轨迹/双ZIP；另覆盖成功但空值、绕过守卫、业务失败捕获、第二轮失败准确选第二轮、诊断失败封存及其它认证/导入/发布/Key/Service/会话/来源停止。捕获后只有限定GET尾序列，无后续外部写入/Service；真实HTTP0、源前后摘要一致，不代替真实模型质量。

验收：`python -m pytest backend/tests/test_continuation_batch_boundary.py -q --basetemp work/NEW-CONTINUATION-GATES`；`python tools/continuation-chatflow384/rehearse.py work/NEW-CONTINUATION-REHEARSAL`；冻结后`python work/continuation-chatflow384/execute.py validate`。项目.venv，仅定向不全量。

消费前只读预检原22/367旧证据、360-b8edf5ed1f3251b03bed/PID26172/289源快照及原Docker16服务健康过；未登录/DifyHTTP。[安全摘要和三个失败捕获公开场景](continuation-chatflow-preflight-20261029.json)。

最终work/continuation-chatflow384，15哈希条目另加manifest。plan SHA256 `d6d510749bd035480f22eac84e883a7e4a22b83ac55556e27742f12e8ee57592`；manifest SHA256 `2eb35bb615d54fcc88ef8c4d900a74a1fa69d01603c4fbdf49844f2d616b3239`。无新approval/attempt/真实请求。

全部新增范围及明确失败轮诊断例外超出现有边界，按[AGENTS.md](../AGENTS.md)“within existing explicit resource and cost bounds”需新直接批准，旧常规委托/旧批批准不代替。答复绑定最终摘要后才写approval并唯一canonical非优化live；来源/冻结/旧证据/运行变化拒绝，Docker未就绪不消费或登录。
