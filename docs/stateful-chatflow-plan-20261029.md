# 361每会话确定补号后完整新批386（执行前冻结）

384唯一失败轮已按批准的4GET诊断，确认补号走intent→clarify。241已实现并部署361的每会话确定路由，175定向检查通过，原23任务及388消费保持，真实新图还未执行。[实际失败](continuation-chatflow-live-result-20261029.md)、[功能修复](pending-order-routing.md)。

新386独立全部新增范围，不重放、改授或借退375/376/378/380/382/384。固定0.361.0-6a7fa27661878cc800e9，新图23节点24边，两个boolean登记/消费标记初始false、按会话隔离、每状态唯一writer。每轮先消费等待，仅等待且当前输入符合原合成单号格式才绕过分类，仍经原提取/成功/非空守卫；普通新话题正常分类，缺号重新登记。不保存单号或其它敏感信息。

新Task.id生成后，两个原生声明ID按uuid5(sierra:conversation:{task_id}:{name})确定实例化，逐项验证除ID外原生图/配置/声明完全不变，冻结文件不改。导入/草稿/当前发布图均精确核含状态的core；不能沿用public-contract原型ID或扩大允许其它状态。保存计划后正常逐项复核conversation_state、重新确认需求并重存当前计划，不放松旧复核门禁。[完整边界代码](../tools/stateful-chatflow386/contract.py)。

正常API新建Task1，公开需求配置→人工模板复核确认→构建→新App首次发布/运行Key→六例及逐轮原生轨迹/交付。原版通过后，仅无答案两处文案加“商品型号”，正常需求修改失效/重新复核确认，新第二App/发布/Key，再六例和第二交付。不换模型、类型或改预期。[全部公开输入/原期望](../tools/stateful-chatflow386/fixture.json)。

每版六例：政策命中含ZXRET715/七天/未拆封；未收录政策固定无答案；范围外固定澄清；模拟订单存在/不存在；缺号固定追问后同会话只补DEMO-001。不同样例新会话，最后两轮分别验规则和轨迹。共同前缀必须经过状态控制三节点；缺号首轮必须登记等待且不查询，补号第二轮必须绕过intent且经过原提取/业务守卫/查询。共12启动14物理Service/14正常轨迹/双ZIP；本机flags=false保持，不改成已平台/业务签收。

## 新批范围

| 项 | 已批准保守上界 | 全部新增最多 | 拟新保守上界 |
|---|---:|---:|---:|
| Sierra模型HTTP | 30 | 0 | 30 |
| 管理GET（含失败轮例外） | 1213 | 128 | 1341 |
| 加密登录 | 43 | 1 | 44 |
| App/首次发布/Key | 各22 | 各2 | 各24 |
| 物理Service | 92 | 14 | 106 |

新增本机Task1，原23保持，完成则24Task；Task12启动/45分钟，整批60分钟。搭建模型/新库0，Dify内部仍调用分类/提取/回答模型及检索，不能把Service当供应商内部HTTP封顶。新增估算0.10 USD，非账单硬封顶、宿主费用未知。主模型账本0.755473652/旧unknown/六settled及全部旧费用预留保持，不借退。

复用原FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1、TopK3/无阈值不重排；deepseek-flash/thinking=false/温度0.2/512，原记忆最近5轮保持。专用连接明确重连原工作空间一次，复用加密凭据，不复制聊天密码。新Key切连接，旧Key加密归档，不覆盖旧App。

## 唯一失败轮有限诊断例外

仅Service成功但业务规则failed，立即停止后续全部外部写入/Service；只对唯一已失败轮按已知App/消息/会话，顺序读取消息关联run→原生详情→节点→当前发布图，最多4管理GET/1本机报告后封存。这4读计入128，无失败不额外读；禁止其它GET/登录/发布/Key/Service，诊断失败不重试。技术/认证/来源异常立即停，不启动此例外，不改判原failed，不用于旧失败批。

state_policy及failure_diagnostic_policy必须明确绑定最终计划/manifest和新直接批准。旧384例外已消费，不能续用；旧余91读/资源1/7Service及更旧余槽均保持。[停止边界](../tools/stateful-chatflow386/boundary.py)、[正常执行与失败捕获](../tools/stateful-chatflow386/journey.py)。

76新门禁通过，覆盖原型/owner ID、初值False与数字0区别、额外/缺失声明、类型/图变更、二次绑定拒绝、来源/次数及有限失败政策；同时收集旧门禁再只选新门禁，确认同名CLI模块隔离，旧57未执行。20独立公开临时23Task完整协议场景通过，正常80读1登录/资源各2/14Service/14轨迹/双ZIP，另覆盖状态初值或发布ID被改、补号仍经过分类、守卫绕过、业务/技术/来源/会话错误及失败轮诊断停止。源绑定摘要一致，真实HTTP0，不是模型真实质量。

原23Task/388消费及密文资产、361/289快照/PID29024归属、原Docker16服务健康只读预检通过，未登录或请求Dify。[安全预检](stateful-chatflow-preflight-20261029.json)。本批是人工图平台核对，不是模型自主访谈规划、一次浏览器全链或全§11/25签收。

冻结work/stateful-chatflow386，15哈希文件另加manifest。plan SHA256 `cf0c13f433c309db977c864b244b9bb2223cbbcb0a05a0a4a73f28aa9b3263c6`；manifest SHA256 `67c8a1623e21a389db4cd8874e14d271b45012ab31d5d51540d48d2e596f54f6`。唯一canonical非优化execute.py，validate已过，无approval/attempt/worker。原数据/源/快照/旧证据变化或Docker未就绪则消费前拒绝。

新增具体资源/次数和费用超出[AGENTS.md](../AGENTS.md)常规委托的“within existing explicit resource and cost bounds”，需一次新直接批准全部范围及限定状态实例化/失败轮例外；原批准不能代替。方案可审查后再统一询问，不逐项索要确认。
