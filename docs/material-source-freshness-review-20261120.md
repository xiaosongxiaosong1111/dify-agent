# 材料来源与裁定新鲜度复核（2026-11-20）

交付清单08、任务346，FR06/10/11/40、AT03/08/19。DeepSeek只读调查，Codex独立读直接实现与案例并执行定向检查。当前沿用d22d023源码，没有新增产品修改，不重写已具备的功能。

- 上传、修改引用方式和移除材料绑定当前修订，先保存旧版本、再使相关需求/配置/成果失效。原文件保留在本机；移除后当前材料入口不再冒用历史原件。当前无独立替换接口，采用移除后重传；同名不自动决定新旧事实。
- 未读文件补充正文须同一Task/材料/SHA、原件可读和当前修订，并标明用户提供的文字；已有可读正文不能通过该接口静默覆盖。原解析片段和当前采用正文分开，人工文字不声称OCR或原文件解析成功。
- 保存文字索引/分页的来源指纹包含Task、修订、材料ID、文字摘要和来源标签。正文、片段或来源标签变化会拒绝旧页，跨任务和旧修订也拒绝；这是保存记录的核对，不是原文件已重读的证明。
- 原件核对/下载在读取后重新确认修订与材料记录，文件摘要或归属不符时拒绝；不拿提取文字重建丢失原件。该部分本轮读源码，未新增浏览器或重跑原件完整套件。
- 冲突上下文含当前材料列表。当前材料变化会使旧检查/裁定过期；345已补来源移除后的明确撤销和审计，不能自动按旧结果通过。

实际命令：`python -m pytest backend/tests/test_material_revision.py backend/tests/test_material_review.py -q --tb=short`，32通过；另运行test_material_stored_text.py中test_identity_changes_reject_old_page_even_at_same_revision、test_append_allowed_but_revision_foreign_material_and_foreign_task_rejected、test_manual_body_and_original_partial_keep_separate_provenance，10通过。复用本轮345的89后端及实际App来源移除/撤销/单独确认，不再重复执行。

未发现新的实质产品缺口。DeepSeek未自行运行命令；42项结果来自Codex实际执行。替换前后业务含义、真实模型的冲突识别质量和原件全部格式仍不据此验收；本项物理模型/Dify为0、未访问生产资料或修改凭据。运行保持0.410.0-7e6f0aefffe51b7f0675/298/PID35824。
