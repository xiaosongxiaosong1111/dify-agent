# 当前修改版的独立零搭建模型平台收尾（368，第216）

当前r13完整修改计划已正常采用213第二次模型原候选并静态交付；原版r9 App及命中/无命中两例已真实通过。365已消费并停止，不能继续其剩余阶段。新执行器复用已经保存的图，不再访谈、规划、自动修复或手改模型候选，只补修改版平台证据。

图内严格允许原模型已有的两处相同话术替换：无命中模板、LLM资料不足时的提示均增加“商品型号”；其它节点、边、输入输出、资源和参数逐项保持。对照原版模型计划和已保留修改候选的摘要、当前保存图、既有真实运行及静态文件，不把代码相同当新生成或人类签收。

执行前本机更新本批资源说明；同步验收说明中唯一遗留旧固定回复，使其与已经更新的输出和`test_cases`一致。使用正常PATCH与`intake/manual`，明确agent_delegated/agent_declared，再由根代理读源复核；正常确认需求、用原封不动的已保存图重新校验、确认配置、静态构建。预计本地r13→r17，原版、旧文字及所有历史保留。这些步骤不调用搭建模型。

通过后只创建一个新App，不覆盖原版；首次发布、创建专属运行Key并切换专用连接，旧Key加密归档；命中、无命中各运行一次并读取原生节点轨迹，核对LLM路径1/0、图归属及修改版ZIP。

| 边界 | 拟直接批准的完整范围 |
|---|---|
| 明确改授 | 365未派发28次管理读取、App/首次发布/Key各1、运行2；旧365及其它消费包永久不重放 |
| 新增登录 | 仅1次复用加密资料的明确重连，登录预留36→37；新token须先证明同一原工作空间，失败不第二次登录 |
| 搭建模型 | Sierra模型HTTP、访谈、规划均0，旧六笔费用禁止新增/改写；已有Key只可用于本机诊断脱敏 |
| Dify回答 | 命中例仍执行已配置回答LLM一次；无命中走固定文字分支，不调用回答LLM。费用计入Dify估算，不声称全流程免费 |
| Task/库/策略 | 0新Task/知识库，保留18Task；原Task已用2/4次，本批最多补2次，原4次/20分钟阈值不变，本批30分钟准入 |
| 估算与总界 | 新Dify估算0.01 USD，非账单硬限、宿主未知；模型保守30/读取573/资源各12/运行22/模型账本0.755473652不增加；旧unknown/费用与其它保留槽不退还、不借用 |
| 内容绑定 | 根代理复核后，需求/配置/完整图/样例/材料/类型/环境均绑定；仅正常确认、版本及成果元数据可变化，任一内容变化在平台阶段前停止 |
| 异常 | 任一异常整批停，不重试、不重新派发、不给旧失败改判；模型出站来源和原批阶段一律拒绝 |

最终固定包work/c1-model-free368共**24文件**，源tools/c1-model-free368。plan SHA **7fea9063dac6e957dd044b071cfc3cf4fa7c90e4a25df5ab501e051e480ed475**；manifest SHA **39e79c2c9470d8db32a20861664e1ee6dffd8985426037ac39c160178eac1616**。当前无approval/attempt/worker-started，未执行认证、模型或平台请求。先前未批准的23文件版本完整保存在work/c1-model-free368-before-criteria-sync，不执行。

53项准入/复核门禁、29项实际Guarded Store保护、36项纯范围/零模型边界检查通过。固定最终包正常及9异常场景精确计数通过：正常0模型/17管理读取/1登录/资源各1/运行2；登录失败、新token401、错空间、导入失败、返回旧App、发布失败、Key失败、运行失败、轨迹不匹配均立即停，未派发后续。全部SDK未读响应替身、临时公开案例复制及PUBLIC假凭据，原始数据库/主Key未复制；旧已通过历史不算本次新运行。不是实际模型语义或平台通过。

本机实际管理员上下文核原dify-local16容器/5健康，351-3ab205b3fbb44bae4789/287文件/PID4172及源码快照一致；实际数据、原18、密文资产和所有旧消费包保持。服务健康不代表认证或业务通过。[最终本机证据](model-free-closeout-preflight-20261028.json)。配置、逐项复核、同图校验及诊断使用正常API，其余关键步骤同一界面，不宣称全鼠标。

```powershell
# 只运行隔离检查，输出目录必须为新目录：
.\.venv\Scripts\python.exe tools\check_c1_model_free368.py --output work\model-free368-check-NEW --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
# 仅在新的直接整批批准与上述双摘要绑定后唯一执行：
.\.venv\Scripts\python.exe work\c1-model-free368\execute.py live --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```

真实前仍须重新核固定文件、实际版本/PID归属、保存数据和服务，再独占attempt。根代理须实际读取当前review-source并显式proceed/reject，结构替身不能代替这一步。当前修改版仍仅静态交付；完成本批也只闭合该固定公开售后案例，不等于原25业务、Chatflow订单链及全项目验收。
