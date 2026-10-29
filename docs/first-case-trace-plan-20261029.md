# 375首例失败的独立诊断376（执行前冻结方案）

当前状态：已获call_88f2d09849de46aeb7d3bf8b71f6a314 q0直接批准并唯一执行完成/消费，10读1登录；下文是执行前方案，未批准等措辞按冻结时点理解。[实际结果](first-case-trace-live-result-20261029.md)。

375已唯一执行并在首例FAQ命中规则失败后永久停止。[原始结果](chatflow-order-platform-live-result-20261029.md)保持：运行接口成功，回答是固定无答案，原规则failed；没有节点证据，不能据此认定分类、检索、条件或回答模型哪一项有误。376不续跑375，不改变原输入、预期或结果。

## 唯一目标和来源

固定Task `62bb060f-b7fa-4397-acb0-ba931c7dbfb2` r5；本机run `f7576baa-61f4-43b2-80d9-4ad0609c897f`；App `aa4a052e-c7b4-4b84-b4bf-4fe741afb22f`；消息 `091f7f7e-a0b8-46e2-8abd-d7db285ed11c`；会话 `b4fbd90f-1b62-49f4-b90c-d55d725e1d0e`。只复用原专用环境和空间、FAQ `d12cf081-5c52-41e3-b869-e94e6f8d37b1`。

本机已对照Dify1.17.1指定graphon0.7.0的两段纯条件函数，True/False正常区分；该假设未复现，不据此修改真实图。依据为[固定依赖](https://github.com/langgenius/dify/blob/1.17.1/api/pyproject.toml)及[对应条件处理器](https://github.com/langgenius/graphon/blob/v0.7.0/src/graphon/utils/condition/processor.py)，不是实际节点重跑。

## 完整范围

| 操作 | 本批上限 | 来源和限制 |
|---|---:|---|
| 管理GET | 10 | 拟从375未派发115次中明确改授10次；不新增读取总上界 |
| 加密凭据登录 | 1 | 新增一次，保守登录38→39；原空间验证后才保存令牌 |
| Sierra模型 / 新Task / App / 发布 / Key / Service | 均0 | 不试跑、不重新生成、不改库、不重建索引 |
| 整批时间 | 10分钟 | 任何异常停止，不阶段重试 |

请求顺序固定：一次登录，随后原应用列表探测和空间确认2 GET；原消息关联原生run、详情、节点、当前发布图4 GET；指定FAQ元数据、第一页最多2份文档及其各一次索引状态最多4 GET。文档少于2份则读取更少；has_more保留，不翻页或冒称全库检查。未知ID、重复文档、错误页/条数、来源或发布图变化均停止。

管理读取保守上界701、模型30、资源各14、Service36及模型账本0.755473652 USD均不增，只有拟登录39。模型新增估算0，宿主费用未知；旧375估算0.10及旧unknown/六settled/所有保留槽和费用不退借。本次10次必须新直接改授，其余105未派发读取和旧资源/Service继续保留，不能自动挪用。

## 本机写入和保护

通过正常产品接口给这一个既有run追加一份诊断，仅允许诊断、updated_at和存储序号改变；原结果/失败规则/需求/图/确认/执行限制保持。正常重连仅旋转原连接console/CSRF加密令牌和新增一次重连记录；服务Key、密码、App绑定及其它对象/资产主Key保持。

诊断沿用产品节点报告与来源核对；库/文档读取只存受控状态、布尔、计数、UUID及error_present，不保存库名、文档名、正文、地址、原始错误或任意metadata。当前发布图匹配不能证明不可变发布版本关联，索引完成也不等于回答质量通过。

原19Task、375及更旧287份消费证据精确绑定。每次出站前检查来源；并发编辑后立即停并保留编辑，不用旧快照覆盖；进行中的诊断若不能保存，仍保留已消费请求。原失败不改判，不补跑或重放。认证/HTTP/来源异常整批停，未派发范围和费用不自动归还。静态验收不等于真实诊断成功或业务修复。

## 已完成的本机验证

39项门禁通过，覆盖原App/消息/会话、来源/页码/文档身份、请求上限/顺序/超时、未读HTTPX响应及Cookie上下文、网络失败不重试、严格冻结/批准/一次消费、业务/凭据保护。11个公开临时19Task协议场景通过：正常、分页未完、索引状态错误，以及登录失败、错空间、错消息、节点失败、发布图变化、重复文档、索引HTTP失败、并发来源编辑。正常最多10 GET/1登录、追加1诊断，原规则failed保持；所有替身真实HTTP0。

验收命令：

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_first_case_trace_boundary.py -q --basetemp work/NEW-TRACE-GATES
.\.venv\Scripts\python.exe tools/first-case-trace376/rehearse.py work/NEW-TRACE-REHEARSAL
.\.venv\Scripts\python.exe work/first-case-trace376/execute.py validate
```

已只读核对375后19Task数据完全未变，运行仍0.356.0-5476d30269eac2811387/PID35272/289文件；原dify-local16服务及必需健康项通过，无Dify HTTP或解密登录。本轮仅工具与文档，无产品代码或重启。[安全预检](first-case-trace-preflight-20261029.json)。

## 最终冻结与新批准

新目录work/first-case-trace376，11个哈希条目另加manifest；plan SHA256 `d85d57bbf982218f6008d70c89b7960be797414bdc3ebac9139d91802f07b356`，manifest SHA256 `bdb4c34b811e6604a25a830549eb91e5e57d86c75276355970dbe668b9761d06`。源码、证明、19Task来源、旧回执和运行快照绑定，任何变化消费前拒绝。只有canonical非优化入口可live，无新批准/attempt，旧375批准不适用。

需要一次新的明确改授和登录批准，因为375已经消费；[AGENTS.md](../AGENTS.md)常规委托限于“within existing explicit resource and cost bounds”，不能代造人类新批准。新直接答复绑定最终摘要后才生成approval并唯一执行；失败包不重放。所得实际分支证据用于定位后再开发实质修复，不提前猜测修改。
