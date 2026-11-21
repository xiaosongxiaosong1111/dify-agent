# 原生保留文件的目标端口与构建重核

2026-11-21，BACKLOG357／清单25局部，DeepSeek实施、Codex复现及独立验收。

根在正常参考读取/合并/确认/build入口复现targetHandle为false或数组仍全部200且非法字段保留到DSL。原因是validate_preserved投影根边时丢失实际目标端口，后续校验只见默认target。DeepSeek无损传入存在的原生targetHandle，不以or吞掉false/null，不重写原文；缺失默认与显式target保持，非法来源可保存供查看但预览无效、不能采用。

进一步验收用旧校验器仅在进程内生成历史已确认快照，再恢复当前校验器，发现build仍200：旧overlay.validation缓存被直接信任。DeepSeek经新窄授权只改main.build保留分支，在归属/摘要检查后对实际Workflow/Chatflow原文重新静态验证，并传入原parallel_reviews/loop_reviews；无效在写成果前422，旧文件/缓存/确认/引用/任务保持。Agent独立保留流程不套Workflow验证，原模拟交付与参考策略检查继续执行。

根最终独立88项通过，加1项保护循环完整API：新原生目标回归、DSL往返、根端口、Agent实际手改文本、并行声明、容器正文、参考指定保留/严格复现及循环。新legacy用例有真实POST/build、齐备确认和valid=true旧缓存，并核target错误、任务和目录/原文字节不变，不以缺确认假通过。DeepSeek两阶段各有一次新测试夹具/准备顺序自修，无旧用例弱化。全部临时数据和假导出/导入，产品模型/DifyHTTP0，不跑全量；无前端/依赖修改。

本项没有签收全部最新应用来源：DS另报的连续导入来源疑点已被根正常API证实（第二App成功→编辑需求使当前App失效→再读却导出第一App）；work/dsl-next-app-source-repro.json。下一独立358处理，当前不混改来源规则；真实手改/自主模型质量也未因此完成。

实现50dce4b已保护部署0.410.0-c74b0545840c294df3ba/298/PID20012，十二根/733/337封存24/原26密文保持，health/页面200、源码/快照/执行文件一致。原机work/dsl357-deployment/before/after.json为实际回执，勿覆盖。旧任务、密文、证据和账本保持。
