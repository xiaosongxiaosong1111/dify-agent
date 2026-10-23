# 访谈精确原文与建议边界

0.264修复71实际访谈暴露的提示缺失：用户指定固定／严格相等输出、标识和数值时，requirements_patch与验收说明的引用必须保留句尾标点、大小写和有意义空白。未采纳风险／优化建议放message，不塞进已有明确需求或仅因存在优化空间就把明确规则变成needs_input；真正缺失、冲突、不可实现仍澄清。用户请求补拟缺失规则仍可给明确未决草案，不作为已确认。

本次只修改访谈提示与契约，后端处理逻辑未强制改写模型答案或解除准入。22项相关目录/真实缺口/建议等待确认检查通过（38未选，无全量）；两条实际访谈API的模型替身回放显示：旧71失去句号/needs_input响应原样保留、确认仍422；固定输出正确且可选风险只在message时，需求原样、来源就绪且仍未确认。固定替身不证明实际模型效果。

已部署0.264.0-75e7b81dad5f0c709f6a，运行仅backend/app/assistant_scope_prompt.py、docs/intake-model-contract.md和版本号变化，源码匹配快照；源14任务/全部对象密文/主密钥及旧71回执账本保持，真实模型/Dify0。71原失败不重放，不把它回填成功。

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_assistant_scope_prompt.py backend/tests/test_intake.py -k "scope or catalog or test_at01_nonempty_but_unresolved_topic_blocks_confirmation or test_at02_rules_and_examples_wait_for_user_then_require_revision_confirmation" -q -p no:cacheprovider --basetemp=work/pytest-intake-literals-unique
.venv\Scripts\python.exe work/intake-literals264-check.py
```

测试使用专用空FLOWCRAFT_DATA_DIR及未存在basetemp，保留生产数据。实际改善需独立新批核对，仍受最后1保守模型槽和费用边界；不得靠额外重试耗费。[安全证据](intake-literals-result-20261023.json)。
