# 知识库准备契约

工作台 0.6.0；2026-10-09；Dify 1.17.1。此流程准备资料，不自动判定检索效果或客户业务完成。

## 输入和方案

配置页“准备新知识库”接受明确用途、名称、描述、索引方式、粘贴文本或当前任务已解析资料。最多 10 份资料，每份 10 万字，合计 UTF-8 1 MB；超限不截断。方案保存全部提取文本、来源、字符数和 SHA256，PDF/DOCX 使用现有解析文本，不宣称保留二进制排版。扫描件需先补充可读内容。

方案绑定任务修订、环境连接及实际 Dify 工作空间。生成方案只读取身份／模型条件，不写入 Dify。用户先预览资料，再确认；确认和实际启动分开。修改任务修订或连接后不能将旧批准自动迁移。

经济索引不调用 Embedding；高质量索引必须明确选择当前可用 Embedding 模型，并明确接受此步骤未知的模型费用后才能执行。没有模型时说明缺条件，可补齐或明确改选经济路线，不自动降级。当前没有此流程的供应商账单硬上限；时间上限只停止后续派发，不撤销 Dify 已接收的索引。

## 写入、状态和恢复

执行依次新建一个 only_me 知识库、创建仅授权该库的 Key、提交每份完整文本。Key 在独立作业 ID 下加密保存，不替换环境原有知识库或运行 Key，也不进入返回元数据、DSL 或报告。每阶段派发前记录 pending，得到可核对结果后保存实际 ID。阶段前后读取工作空间；写入期间切换时记为结果待核对、停止后续派发，不能保证跨 Dify 请求的原子隔离。

已提交文档不是索引完成。读取每份真实状态；只有全部 completed 且具有有效正数片段统计才 ready。错误、未知状态、缺少统计或空片段均不冒充可用。ready 仍须独立执行检索样例。

暂停阻止后续派发，已接收索引仍可能运行；已返回的资源结果保留。服务重启将 pending 写入改为 unknown，其他未完成派发暂停，索引状态可重新读取；不自动重复创建。原资源不自动删除。

写入结果未知时不能盲目重试：用户在 Dify 核对后输入实际资源 ID，后端再次验证工作空间、名称与索引方式，再绑定现有结果；文档内容一致性由用户明确核对。创建 Key 响应未知无法找回明文时，用户可明确接受旧 Key 可能存在并新建一次替代 Key，旧结果仍留痕，旧 Key 清理由用户在 Dify 核对。权限拒绝与不明确的写入失败分别记录，HTTP 400/500 不能假定未创建。

## 加入任务

ready 后用户主动“将就绪知识库加入任务配置”。后端重新读取状态，按相同修订检查，并原子写入任务与作业结果。新 ID 加入默认 dataset_ids、推进任务修订、使配置确认失效；已保存流程标为需复核，独立节点 ID 不自动改写。任务变更后的旧准备记录可阅读，不能自动加入新方案；可通过实际目录重新选择已创建 ID 并复核。

## API

- GET/POST /tasks/{id}/knowledge-jobs：读取记录／生成方案（revision、purpose、name、description、indexing_technique、material_ids、text、document_name、embedding_provider/model、max_minutes）。
- GET /knowledge-jobs/{id}：读取持久化方案及实际操作记录。
- POST /knowledge-jobs/{id}/confirm：task_revision、accept_unknown_embedding_cost。
- POST /knowledge-jobs/{id}/execute：主动启动／继续；replace_unknown_key 仅供明确一次替代 Key。
- POST /knowledge-jobs/{id}/refresh：读取实际索引状态，不重新提交文档。
- POST /knowledge-jobs/{id}/pause：暂停后续派发。
- POST /knowledge-jobs/{id}/reconcile：verified_in_dify=true、resource_id；核对现有未知结果。
- POST /knowledge-jobs/{id}/apply：revision；主动将就绪 ID 加入配置。

## 验证

后台 219 项测试通过，含确认、全文快照、费用准入、暂停／并发、未知操作／替代 Key、索引终态、修订／空间变化、重启和错误脱敏。

产品界面真实联调：任务 `85bbd13a-08bf-43bc-8db0-e733756f793e`，作业 `34704883-0cfa-4110-bc81-5eb0e6a13b41`，实际库 `add6c8eb-0882-4bb7-9fff-fa0020abb707`。一份已上传 Markdown 与一份粘贴虚构政策都完成真实经济索引，各有 1 个片段；独立确认与启动、主动加入使修订推进、刷新恢复共 5 项界面检查通过。没有客户资料或 Embedding 调用。记录在 work/knowledge-live-ui-result.json。

高质量路线已用受控传输验证条件和请求，当前未配置可用 Embedding Key，尚未实际索引；检索策略建议、自动重试索引错误、完整预算和客户场景仍待扩展。
