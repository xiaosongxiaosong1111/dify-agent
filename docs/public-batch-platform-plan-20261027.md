# 公开批量计算：独立平台批冻结方案（2026-10-27，第179）

状态：本机可执行包及隔离校验完成，**真实平台未批准、未执行**。本方案不复用任何旧批授权，生产中新Task也尚未创建。当前产品仍为0.341.0-cf06d6388885cb69a63c，没有额外部署。

## 要解决的问题

第178提供无模型批量起步，第175可查看和下载保存的逐项结果；它们尚未证明Dify 1.17.1 Sandbox中的实际结果。本批只核固定公开计算，经新Workflow首次发布和一次运行，核实际发布图身份、逐项结果及本机失败JSON导出。不是售后主链重做，不扩大为任意代码执行、节点轨迹、浏览器真实验收或完整业务签收。

公开输入为 `{"items_json":"[\" a \",\"ERR\",\"a\",\"\"]"}`。仅文字完全等于ERR触发ValueError，其余去两端空白后大写。原顺序/重复/空文字保留，预期4项、3成功、1失败，原索引1为ValueError，成功值依次A、A、空文字。六类受控错误继续，其余错误/输入输出错误/超时/Sandbox故障停止，不重试。

完整公开计划、原生DSL、输入、执行器和隔离检查已[保存源码](../tools/public-batch-platform342/README.md)，源自已测试冻结文件；没有复制生产数据、凭据或原始供应商响应。

## 请求的新整批范围

| 操作 | 新批硬派发上限 | 累计变化/保留 |
| --- | ---: | --- |
| 新本机Task | 1 | 原16任务全部保持；新Task正常访谈/确认，不绕门禁 |
| 模型HTTP | 0 | 实际20/保守24、四旧槽及全部旧账本不变 |
| Dify管理GET | 16 | 旧413预留保持，新上界429；成功替身实测11 |
| 登录POST | 1 | 原28预留保持，新上界29；只用专用连接加密资料明确重连 |
| 新Workflow App导入 | 1 | 不传app_id、不覆盖旧App |
| 首次发布 | 1 | 仅本批新App，先读未发布，再核完整发布图 |
| 新运行API Key | 1 | 仅本批已发布App；专用连接切新Key，旧Key加密留档 |
| Service运行POST | 1 | 实际累计16→最多17；App/首次发布/Key各8→最多9 |
| 知识库/外部工具/模型资源 | 0 | 不建库，不动全局模型设置 |

专用连接 `202bfb35-2f92-47c1-bc1b-eac32082181d`，空间固定 `c3306c18-ceb2-4bee-b2d1-796ce2048f17`，不得切其他工作空间。新任务最多1次启动/10分钟/已报告报价阈值0.01 USD。Dify整批估算0.01 USD，**不是账单硬封顶**，Sandbox/宿主费用未知；无模型费用预留转授。旧unknown、settled、所有预留及费用边界保留，不借用、退还或重放。

整批600秒门禁在每次出站之前检查，不承诺取消已在途请求。全部异常或不符即整批停，禁止阶段/整批重试或自动清资源；请求已派发即占次数，丢失写回执保留未知，资源可能已存在。即便登录失败也不自动再登。

## 顺序与保护

1. 直接用户批准需绑定本计划与manifest摘要和实际问答来源；没有批准时在创建消费记录/生产Store前拒绝。常规委托的intake复核记录为agent_delegated，不冒充人类回答。执行器只接受唯一work目录，独占创建attempt.json，重复进入拒绝。
2. 再核运行版本、原279源码/快照文件与所属PID、原16空闲、连接身份及全量旧对象/密文/文件摘要；有漂移停止。运行日志server.out.log/server.err.log和SQLite物理容器/WAL/SHM不作不可变文件，逻辑对象/所有密文、主Key和原任务资产均严格核对。
3. 明确重连同一空间，随后正常创建新Task→保存需求/完整计划→固定样例→intake逐项受托复核→重存计划清stale→原两项确认→新执行限额→构建。
4. 导入新App→首次发布确认→核发布图摘要→创建配对Key并加密保存/归档旧Key→仅运行固定一例。所有物理HTTP前核origin/path/query/body/新App身份/Key/次数/耗时，先持久化派发计数；其他模型/HTTP/旧App动作拒绝。
5. 核实际结果绑定本次发布图、严格完整results和分组/4-3-1计数；再从已存记录只读查看失败原索引1，核JSON导出摘要与原失败对象。任务/外部回执ID和安全计数保存本机，不输出密钥、登录正文或原异常正文。
6. 核原对象/文件/密文及原消费包保持，专用连接仅允许批准的认证字段、运行配对和能力状态变化；新资源归属单一新Task。任何异常只保存安全状态并停止，不自动补救。

## 已执行的本机验证

- 38项入口/哈希/授权来源/唯一消费/次数/出站/数据保护校验通过；缺少真实批准的实际入口退出，未创建attempt。
- 正常新Task链11次本机API通过，intake与plan_review保持，确认由原门禁推进，不用legacy helper改状态。
- 同一执行流程的替身成功路径与8类失败路径通过：错空间、登录503、导入401、发布502、Key502、Key回执丢失、运行失败、错误逐项结果。成功替身11读取/1登录/导入发布Key运行各1；非成功阶段停止，Key不确定状态保持unknown。
- 真实原16快照、旧消费包、配置/账本/密文/主Key保持，实际模型/Dify HTTP为0，生产新Task为0。证据见[本机结果](public-batch-platform-local-result-20261027.json)。未全量测试，未运行用户任意代码，未取得真实Sandbox结果。
- 本机只读运行核对需要管理员CIM权限；已在所属PID22248/原快照验证。测试冻结前发现运行访问日志会因只读请求追加，已明确排除根运维日志并重跑本次定向校验；不扩大业务文件例外。首次未通过/旧回执保留。
- Claude318失败原因/内部请求账单未知，无恢复证明，未为形式再试、未伪称子审查成功。

## 冻结身份

- 本机唯一包：`work/batch-platform342`，入口 `execute.py live`。
- plan SHA256：`53b821675dfc812bf246a78c7ba408eb75e8a7adcaad2cd0f762a2686fe256d5`。
- manifest SHA256：`25fd79d6af049e1f766a1bdd129bf87e6fbe80cc3a785eb842948da23a28dcd4`。
- 方案、脚本、公开输入/DSL任一变更均拒绝旧批准；manifest精确覆盖以下14文件。plan含本机保护摘要清单，留本机不提交；公开副本其余13文件逐字节匹配。

| 文件 | SHA256 |
| --- | --- |
| `boundary.py` | `7b4de131cc37c498990f139471b2aee3a87b86a658af56d01c0a979d83051760` |
| `candidate-plan.json` | `d29240a2429537c0e63bfa06aa4b2b81b2da7b8b73a4ab7a40aa8c4f41921f50` |
| `candidate.yml` | `5750ad3950262a269648362788a24c08e01d68be1f0734916de431311847ac90` |
| `data_guard.py` | `1bc0593b3f2e8885a24b4d1931c4f0f378b90a5b1015d0908b2f00b9ffc8ea18` |
| `execute.py` | `ce5acb9a1012d0997b2e21de0b30871c3c8d263d0ee4c2474d944f9088772c75` |
| `fixture.json` | `78f23855d4a07342fb4197b5614f5cb0a852073bc4a914d0d9b2f08b974c5b70` |
| `freeze_bundle.py` | `00cc9ec1e642608a79b7a95122ae1fbe6e0feb03c719079b5a8270bd30183e1c` |
| `gates_check.py` | `321772ef9125bdb81c92aabfeef7fae3fcbc0ac5137771e1e691c538aa7c6590` |
| `local_pipeline.py` | `e4e99cff301c42cd833e1ab221f2efbea17e71ee7a3776d68872d8dff918aeed` |
| `local_rehearsal.py` | `69f30f17ea57175c922bf63923d4fbd6dde2d3caa6aca8bc03e3ba0ed0604815` |
| `plan.json` | `53b821675dfc812bf246a78c7ba408eb75e8a7adcaad2cd0f762a2686fe256d5` |
| `platform_pipeline.py` | `b40880f757be6e5e675a0debebde0a2cbabc52f75a814581d3b46f259daf3275` |
| `rehearse_platform.py` | `721c48d8c63d1b2c373cbfd1f3d82cfa95f69ff96d4d9d35bf5b142a5e61227a` |
| `synthetic_transport.py` | `901df4c82aca6a4ff5fb5bddd109981133344672336f11f9484e03fd9db651d9` |

原candidate-manifest仅最初静态候选历史，不能当live包或批准。approval.json/attempt.json均尚不存在。批准后不得重冻结/重建包；恢复执行须先核现有安全回执，绝不重放已消费入口。

根据[AGENTS.md](../AGENTS.md)的常规委托只覆盖“within existing explicit resource and cost bounds”，原16次运行和资源各8的范围已用完，所以需要一次明确的新整批范围批准。不得把本方案或代理受托决定伪造成人类批准。
