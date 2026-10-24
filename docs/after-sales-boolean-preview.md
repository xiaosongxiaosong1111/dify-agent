# 售后候选的独立人工格式修正预览

第84原模型候选仍因boolean右值为字符串"true"失败，原候选／回执／账本保持，不恢复或回填原批。本预览是按用户常规本机工作委托，由代理在新的隔离副本中显式准备的人工格式修正；不是模型纯生成成功，也不是人类最终业务签收。

仅改 `nodes[3].config.cases[0].conditions[0].value`：JSON字符串`"true"`→JSON布尔`true`。varType已经为boolean、上游has_result已声明boolean，且代码按结果条数产生布尔值；没有改变真假分支、节点、提示词、模型、资料、参数或需求。精确比较已验证其余图字段相等。原图摘要62485321bda2d63c644f5221beb0e5b5b2cd23e03137ed09796a1f2a477c9a70，人工预览e68041df55b5d917d5acf5bcaa94fb09de7af438e473af0fcc5e84f28f5893b4。

临时Store经既有API确认已存需求、保存配置：原错误图保存仍422；新副本以`plan_source=manual`显式保存为未确认草稿，再确认配置、静态构建、下载YAML与交付报告。初次辅助脚本误把revision放入不接受该字段的PATCH，按现有API更正后通过，未改变产品接口。原14生产任务／全部对象密文／主Key及旧84包保持，临时Store已清理，模型／Dify请求0，未执行生成代码。

可审查[人工预览YAML](examples/after-sales-manual-boolean-preview.yaml)，SHA256 `1c021e44df3e1fbb04183daee6ca0522cdb00660f3d384bbb8df58316ff95543`。[本机结果](after-sales-boolean-preview-result-20261024.json)。完整本机文件在work/boolean-preview268，静态YAML可用于后续单独批准的验收，不能据此导入或运行。

回答模型提示未硬编码七天／未拆封／180天政策事实，保留检索上下文绑定、单模型参数和严格固定回复；两分支输出result。八节点图包含代码判空，代码对非list结果回落空数组的防御分支仍未实测，不能据此保证检索失败／异常形状的实际传播。静态通过不证明真实检索、LLM、错误路径、原79浏览器连续性或最终业务。
