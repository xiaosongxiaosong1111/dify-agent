# 多知识库选择链的当前复核

2026-11-21，BACKLOG350／交付清单12，对应FR19与AT07。

DeepSeek有界核查configuration_proposals.py、resources.py、配置模型契约、配置页面及直接测试；Codex独立读对应入口并实际运行已有测试：

`python -m pytest backend/tests/test_configuration_proposals.py -k "dataset or at07 or source_failure or stale_proposal or offline_retained" -q --tb=short`

实际21通过、26未选。包括三种应用类型多库分页/建议/原样具体ID/理由和影响、明确采纳及重开保存、重复/空白/名称代ID/伪造ID拒绝、遗漏保持与显式移除、跨任务/过期拒绝、目录失败和未核对/空文档确认。旧任务和配置未在建议生成时被自动修改。

正常入口是配置页读取依据→请求建议→看具体ID和理由/影响→明确采纳；仍需另确认配置。需求中的代表问题、专项说明及近期讨论进入模型，目录含描述/数量/permission，15分钟快照绑定连接，读取截断和失败显式保留。程序可以保证来源、结构和明确采用，不能程序断言理由的语义正确或检索质量。

DeepSeek初报only_me目录缺额外确认是缺陷。Codex退回指出：可见私有库可能本就由当前用户合法使用；permission元数据本身不证明不可用，不能据此发明拒绝或额外确认。DeepSeek二次复核撤回该结论，未发现可复现新产品缺口。保留现有实现，不追加等价测试或多余权限流程。

本次仅临时数据和模型/Dify替身，物理产品HTTP0；没有真实多库权限/正文/模型选库理由与代表问题效果证明，固定FAQ不是选库质量验收。无需重复部署，运行保持349的f45af15d6d328c6d20a9。继续清单13资料准备的具体功能核查。
