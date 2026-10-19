# 运行前节点执行规模预览

已部署0.190.0-1c49cd5992f42c4896db（197文件，原数据独立）。

Workflow／Chatflow流程页提供默认折叠的“运行前：节点执行规模预览”。不自动读取输入或请求模型；用户可对每个根迭代手填0—100000项的本次假设，留空为未知。循环按原loop_count计算，不可从此覆盖。所有分支保守相加，只计算编辑器声明节点的次数上界，不包含编译生成保护节点、最终DSL、Dify手改保留、发布图或插件隐含节点，目标应用实际次数可能更多；Agent自主工具／轮次不使用此估算。

分别展示声明总节点、LLM／分类／参数提取、知识检索和HTTP的次数上界。存在未知项数时总次数保持null，受影响的资源次数也保持null，不把已知部分当总数；不含该资源的分量可为0。明确空批量时正文为0次，但根控制节点仍按声明计；模型0不能代表免费。项数只是用户假设，不限制真实运行，并行不减少总次数；循环提前停止或分支未执行可能减少次数。

这是逻辑节点次数，不能作为API请求次数上限：节点内部重试、结构修复、Embedding、rerank及HTTP可额外产生请求／费用。不读取价格，不估Token或金额，cost_usd始终null；不抵扣预算、改变原执行限制、确认或派发。改草稿（含撤回到原文）清旧假设／结果；未保存的全局需求配置不能混用。迟到、其它任务、改变范围或声称已查最终DSL的回执拒绝；15秒超时不重试。

API：POST /api/tasks/{id}/execution-scale，严格revision、完整plan_text、item_counts字典（可省略）及UUID request_nonce；无未知字段，旧修订409，非法数量／旧节点／坏完整图422。原文先检查凭据和结构，静态整体有效后才计算，不执行代码。响应source_kind=editor_plan_only、final_dsl_checked=false、actual_api_calls_known=false、cost_estimate_available=false、verification=local_declared_node_visits_only；任务／联网／业务标志为false。仅预览，原Task、预算、确认及运行保持。

24新增，最终132相关通过9.35秒；25GUI全fixture／原两Task保持、构建主519.79KB体积提示通过。先前脚本切任务后未按应用默认需求页再点流程，修正脚本后通过；开发中也补齐撤回原文不复活假设、明确不含手改／最终DSL的范围。仅增加本机只读预览和公共能力说明，未重复完整后台；最近完整为0.189的4003项356.59秒，不冒称190已完整或业务验收。

部署页面另25项全fixture通过；固定本机2次预览与冻结纯helper一致、三模块／schema／asset200及原11Task保持，见work/execution-scale-deployed-check.json。真实模型／Dify／资源写入和代码执行0。


## 0.238：HTTP声明重试尝试量

0.238已部署 **0.238.0-2c5455ccb20695a5991d**（229冻结文件）：运行前规模预览新增逐HTTP节点声明尝试量，按首次加已启用的重试、迭代项数或循环轮数计算；逻辑访问单列，未知项数不当0，关闭重试的保留次数不参与。逐项公式和毫秒间隔可查看，不当实际API请求、时长、费用硬限或业务通过。缺字段旧回复明确未知，错误总数/因子/范围/证明拒绝；合法constructor迭代ID的输入/解析按自有属性处理。84后端相关2.37s、7有效/8坏及旧回复合同、11源＋11部署新GUI和25部署旧规模GUI、TS/build通过。原11Task/密文/Key/七模型合同保持，未执行真实HTTP/模型/Dify。最近完整仍235的4861项630.37s；不以测试量换算项目完成度。

API新增可选http_attempts，逐项node_id/scope_id/logical_visits/attempts_per_visit/max_attempts、retry_enabled/max_retries/retry_interval_ms；total任一未知则null，无HTTP为0。basis=declared_http_node_retries_only，actual_http_requests_known/internal_requests_counted均false。这里只算声明首次＋节点重试，不含重定向、客户端/代理、代码或插件内部请求。0不能证明没有外部调用或免费。旧服务缺此字段显示未知，不能推成0。证据work/http-attempt-238-deployed-check.json与ui-source/deployed.json；旧execution-scale-ui-result.json为25部署兼容检查。


## 0.239：独立核算

0.239已部署 **0.239.0-0a160cc393f3946abae6**（229冻结文件）：规模预览按当前编辑图独立核对声明总数、模型/检索/HTTP分量和各容器的正文数量、倍率、依据；拒绝数值正确类型但与请求图不一致的回执，不显示部分结果。不改变生成/审批/费用或运行。11有效/18坏合同、15源＋15部署隔离GUI与TS/build过；原11Task/密文/Key/七模型合同保持，后台只有版本变化，完整回归仍沿用235的4861，不冒称239全量或业务验收。 无新增后台接口或供应商调用。CLI15未返回候选，主Agent直接实现；CLI费用字段超过设置值且用量为0，不能当实际账单或节省证据。后续暂停派发，先排查本机Claude配置/计费来源。
