# 第95执行包的运输合同纠错（仅离线）

第95调用器进入1次，但模型HTTP0。执行包的Python运输函数有两处把HTTPX `Request.url` 属性写成 `request.url()`：一处拆分URL，一处比较模型端点。第一处即触发TypeError，原始运输函数未被调用。供应商适配器捕获TypeError并显示“协议不兼容”，所以这不是供应商返回或访谈语义失败。[原失败取证](complete-mainline-live-result-20261024.json)保持，不重放。

之前完整界面预演直接替换了 `call_model`，没有穿过供应商请求构造到HTTPX运输检查这一层，因此漏检。第96另建只供审查的新副本，两处仅改为读取 `request.url`；原95源码、manifest、批准、receipt、账本和最终任务文件均未改。

离线检查从原/新源码提取同一个 `actual_transport` AST，直接调用当前真实 `providers.call_model`，让它构造选定deepseek协议的请求、经过HTTPX和运输检查、解析假响应。只把最后的原始网络运输替换为本机假响应，使用虚拟Key，不解密生产凭据：

- 原代码稳定复现TypeError，假运输转发0次。
- 修正副本完整通过3次假运输和响应解析；实际构造包含max_tokens、messages、model、response_format、stream和thinking。
- 第4次请求，以及超限tokens、开启stream、消息摘要变化、错误方法和非目标地址，均在假运输转发前拒绝。
- 当前16任务及全部对象/密文/主Key、95原失败包和unknown账本逐项保持；所有真实模型/Dify/其他网络请求0。

检查命令：`.venv\Scripts\python.exe work/transport-contract270/check.py`。8项检查通过，[安全结果](transport-contract-repair-result-20261024.json)。当前仅离线审查副本，不是新的已批准执行包，未重试95，也未升级产品版本。

后续真实整批必须先把这项真实协议合同预检放在一次性回执前，并重新冻结输入/执行器。95已证实零出站的范围若要改授或费用预留若要核对，须另有明确批准；不能改原unknown冒充供应商账单，也不能自动释放旧四项预留。
