# 自主双版366：本机冻结结果（2026-11-22）

状态：**本机准备已通过，真实批未批准、未派发**。本记录不代表真实模型质量、Dify平台或业务验收通过。方案保持[制定时原文](autonomous-dual366-plan-20261121.md)，冻结后不再修改方案/工具/profile，不覆盖或重建唯一包。

## 冻结身份

- 原机 E:/workSpace/dify-agent；唯一包 work/autonomous-dual366。
- 源实现 Git：`dde3d12268cc80953669fea408fa98ab0cdc3547`（初实现3b70adf，原机路径碰撞修复dde3d12）；新冻结plan记录此完整源commit，后续仅文档提交不改变冻结内容。
- plan SHA256：`a0dbdd41423f9a3076958201f1d8ae911324e63b04abdae77b0efa2cd7ce3dff`。
- manifest SHA256：`dc206134286db2937606989f72dde5619c31e4cf606a787df9a7f854de35cbf6`。
- proposal原始字节 SHA256：`7a9fc81b8989138f0295dd0e6ab3fabf5283a07f57de3ef0e3006e028e501847`；与包内approved_scope.md、plan绑定相符。Git工作区可能使用CRLF，复核以原机冻结字节为准。
- 清单21项，加manifest共22个文件；没有approval.json、attempt.json、worker-started.json，未解密Secret，新增实际模型/Dify/登录/Task/资源/Service均0。

## 实际验收与修复

DeepSeek代码会话287ab2d9-9596-462a-9dc3-935025989481、文档会话a61f9de0-3e5e-4b93-bf21-1c36b48fb066分别限定交付，Codex核差异、复现及返工，不接手产品实现。

1. 初本机62项准入检查过；原机首次pending在stage/canonical创建前实际失败：旧337索引为批内相对名，工具优先解析项目根同名README，误报摘要变化。旧337真实24项SHA均保持。DeepSeek只修prepare.py的批内相对路径解析并加同名/错摘要/绝对路径/逃逸反例；Codex新66项直接过，原机758旧文件只读SHA核过，没有放宽保护或重放旧批。
2. 15共享模块从可信Git blob按CRLF→LF核对，除common批次与worker槽数两处元数据外字节保持；四个新入口/配置/说明与当前已提交实现逐字节一致。旧源、封存和数据仍核原始字节，不规范化旧证据。
3. 三条公开替身路径实际执行，物理模型/Dify HTTP均0。成功序列使用5模型/83管理读/1登录/资源各2/14Service替身，产生12启动、14原生轨迹替身及双ZIP；非法模型JSON在1模型后停止、资源0；第二轮业务失败在3模型/40读/资源各1/7Service后诊断封存，不派发修改版。替身失败路径按预期停止是协议检查通过，不是业务通过。
4. 原机实际生成唯一pending后，execute.py validate-pending通过，独立check366-derived.py核21清单/22文件及摘要通过。未创建或试写canonical批准/运行标记，没有执行approve/live。
5. 原机work/mainline366-freeze-guard/before.json与after.json、私有audit-mainline366.py证明十二数据根、733旧封存、337封存24项及索引保持；新包保护合计758文件。26Task/10环境/2provider及密文资产不变。health/页面200，原快照0.410.0-23c94dbe89553f265c3b/298/PID28732，源码/快照/执行文件一致；没有重新部署。

## 可复核证据

- 根定向命令：原机venv执行克隆tools/autonomous-dual366/checks.py，66 passed；检查只用临时公开数据/合成批准对象，不写真实批准。
- 原机命令：`./.venv/Scripts/python.exe tools/autonomous-dual366/prepare.py pending --project-root E:/workSpace/dify-agent`；随后`./.venv/Scripts/python.exe work/autonomous-dual366/execute.py validate-pending`，均已实际通过。
- 私有独立校验：E:/workSpace/sierra-delegation/check366-derived.py、audit-mainline366.py；私有脚本不属于产品或交付接口。
- 克隆work/mainline366-root-local-report.json记录三条路径及实际计数；success证据mainline366-rehearsal-c6b0f35e39d34dc9a59bb5ce58034c99、JSON拒绝mainline366-invalid-638c3abf2d7f45438060c59d85dedd01、第二轮失败mainline366-second-turn-b6f432a1d9024fc3926afe78b2c9790f。
- 公开仓库只存工具、方案与本摘要，不提交work/data/原供应商回复/密钥/凭据或真实保护快照。

## 唯一下一步

BACKLOG366本机准备关闭；367为这一个新真实整批待直接批准。旧337批准已消费，不能替本批签收。具体资源/费用见冻结方案：新Task1，最多6模型HTTP（成功序列5、修复0，各6000输出tokens/120秒/估≤0.100 USD），资源各2，12启动/14Service/14轨迹/双ZIP，128GET/1加密登录、新库0，Task45/整批60分钟，估0.700 USD非账单硬限、宿主未知。

当前账本仍51模型/1597读/47登录/资源各28/Service134/模型估算2.755473652。批准并真实派发后才按冻结方案记新57/1725/48/各30/148/3.355473652；旧unknown/settled/槽与费用保留不退借。任异常整批停、不重试；仅Service成功而业务失败的唯一轮≤4GET诊断，计入128后封存。

只有收到新实际直接答复“允许独立366完整新范围”，才能在仓库外记录实际call_ID/q0和完整冻结摘要，调用approve、validate与唯一live。Codex实际核FAQ政策及完整模型候选后正常采纳，留代理复核，不伪造人类签收。
