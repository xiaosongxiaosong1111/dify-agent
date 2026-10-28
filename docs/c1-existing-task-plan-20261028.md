# C1复用原空需求任务的独立整批方案（357）

2026-10-28，BACKLOG201实现、202等待对应新直接整批范围。当前真实模型/Dify请求和生产任务写入均0；本地后端此前已停止，已核原PID不存在并仅用原start.ps1恢复相同0.347快照，未停止其他进程。当前PID35976，18Task及除server.pid外全部账本/密文/资产逐项保持。

## 要完成的结果

复用198留下的Task aa827c91-b683-4a34-9e7f-fa0789f5c252/r3，需求全空、无流程/成果/App/运行，原失败候选与唯一settled费用原样保留。通过正常界面选择现任务，先用普通修订API明确本批资源说明，再进行：模糊目标访谈→根代理复核→公开完整答复→根代理复核/需求确认→原版模型规划/根代理复核/配置确认→构建/新App首次发布/Key/命中无命中与原生轨迹/第一ZIP→仅无命中固定文字增加商品型号→变更访谈/根代理复核/重新确认→修改规划候选/根代理复核后主动采纳→第二新App发布/Key/两例轨迹及第二ZIP。

不新建或克隆任务，不直接写Task/需求/图来绕界面准入；配置与原生诊断沿用正常修订/API，其余关键操作在界面，非全鼠标承诺。运行条件沿用4次/20分钟/null报价阈值，不清零或扩大。模型返回结构无效、内容未通过、API异常、过期、原空间不符或停止标记，任一项使整批永久停止，不重试或继续剩余阶段。不能手改真实模型图替代证据。

## 明确改授及新增边界（尚未批准）

- 旧198/354已消费，旧包和旧失败/费用不改、不重放。拟由新的直接批准明确将其**未派发4个模型槽、App/首次发布/Key各2、运行4**改授独立357。原17和所选Task的全部旧消息/版本/失败候选/费用仍保留；所选任务只允许正常追加新阶段。
- 另新增**1个模型槽、48次管理读取、1次加密凭据登录**。新批合计最多5模型HTTP，各最多6000输出tokens/120秒、每阶段1次无自动修复；管理/登录含认证内置读取，不透支后自动续接。
- 模型每次配置价预留≤0.055 USD，五次合计≤0.275；新增1槽估算包≤0.055使含旧保留的模型账本上界0.700473652→**0.755473652 USD**。旧198总预留、95unknown、四旧槽、剩包及已settled不自动退回；四个旧未派发槽仅本次直接明确改授后才能用，不重复新增四槽。
- Dify本批新增估算0.02 USD，整批估算上界**0.30 USD**，非账单硬限，宿主费用未知；所有旧费用与读取/登录预留保持，不按本机失败自动退款。30分钟出站准入边界，不能保证取消已派发请求。
- 新管理/登录预留总上界525/33→**573/34**；保守模型29→**30**，资源各12/运行22不增；实际当前模型21/资源各9/运行17，若完整执行最多模型26/各11/运行21。Task总18保持。旧180等保留资源/运行槽不借用。
- 仍复用原FAQ d12cf081-5c52-41e3-b869-e94e6f8d37b1，不建库；主模型deepseek-flash和运行回答温度0.2/max512/thinking=false、TopK3/无阈值无重排不改。只复用指定原空间加密凭据；每个新App创建专属Key并切同一专用连接，旧Key加密归档，不覆盖旧App。

五处模型内容由根代理按既有委托逐项实际阅读后登记agent_delegated，不逐项向用户索确认，不假称人类签收或Claude审查；它不代替整批资源授权。Claude网关旧预算失败/内部用量未知且无恢复证据，不为形式重试或加预算。若实际Codex额度不足，写stop标记并整份交接，停止新出站，不换号/购买/用券。

## 不可变包与执行入口

- work/c1-existing357，全18文件。plan SHA256：`ab658875a50940336c18433b5de960f392df136be02d0d143f1fd1fc3132b464`；manifest SHA256：`e4414769ebb25ddf57ea1b203cf053de124dbb34d563e6915df2fb84e04d664c`。
- 源码tools/c1-existing357；已消费work/c1-mainline354原15文件、plan/manifest/approval/attempt/worker-started及停止保护回执均被新plan固定摘要引用，不改旧包。
- 只读冻结当前18Task/配置/模型价格/原空间、0.347.0-1b052af3a24e6f1d591e的287源码/快照字节及所属进程；冻结后漂移拒绝派发。
- 缺少新直接批准、精确目标Task、明确改授内容、模型账本新上界、plan/manifest摘要或一次性标记任一项均拒绝。attempt和worker-started独占，源码目录及优化入口不能live。批准尚不存在，不可现在执行。

```powershell
.\.venv\Scripts\python.exe .\work\c1-existing357\execute.py live --playwright C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright
```

## 已完成的隔离验证

66项入口/授权/来源/停止/资源边界门禁；26项真实临时Store的旧失败/消息/版本/settled账本保护；冻结同程序正常及6失败场景，逐阶段精确派发计数通过。正常替身5模型/32管理/1登录/导入发布Key各2/运行4，同Task两ZIP字节摘要及核心图只变固定无命中文字通过。原生形状轨迹LLM1/0/1/0仍只是替身。

额外用冻结程序与正常界面复现HTTP200但8→9漏检索的实际响应形状：vague_interview停，模型替身1/管理2/登录1/后续0，没有复核文件或后续阶段；旧失败与settled仍保留。所有实际物理上游HTTP0、生产18数据与全部旧消费包保持。五次synthetic_structural_checker记录均semantic_reviewed=false，不冒充模型语义验收。

```powershell
.\.venv\Scripts\python.exe tools/check_c1_existing357.py --output work/新独立输出 --playwright C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright
.\.venv\Scripts\python.exe tools/check_c1_rejected_intake357.py --output work/另一新输出 --playwright C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright
```

本机安全预检见[c1-existing-task-preflight-20261028.json](c1-existing-task-preflight-20261028.json)。C1仍未真实通过；C2仅固定公开继续范围保持已关闭，C3结论整理不等于业务通过。原Chatflow订单模拟完整链和六组未适配扩展未由本批替代或删除。
