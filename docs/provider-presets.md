# 常用模型快捷接入

工作台 0.8.0；目录核对日期 2026-10-10。

## 用户操作

打开左侧“模型接入”，点击“添加”，依次选择服务商、型号并填写 API Key，点击“保存模型”。无需填写服务地址、协议、名称、用途和单价。保存只写入本机配置，不自动发起模型请求；列表中的“测试连接”和 JSON 检查是单独的实际调用。

“高级设置”默认折叠，可改显示名称、用途和估算单价。代理、其他厂商或其他百炼地域使用“自定义 / 兼容服务”。自定义服务仍需明确地址、API 模型名、协议以及用于规划预算的单价。Key 不写入 localStorage 或 sessionStorage，提交到后台加密存储。

## 预设与依据

| 服务商 | 可选型号 | 官方依据 |
| --- | --- | --- |
| DeepSeek | V4.1 Flash、V4 Pro、V4 Flash 兼容入口 | [模型／价格](https://api-docs.deepseek.com/quick_start/pricing/)、[思考参数](https://api-docs.deepseek.com/guides/thinking_mode/) |
| OpenAI / GPT | GPT-6.1 Sol、GPT-6 Luna | [Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol)、[Luna](https://developers.openai.com/api/docs/models/gpt-6-luna)、[Chat 参数](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) |
| Claude | Sonnet 5.5、Opus 5.5 | [Sonnet](https://platform.claude.com/docs/en/models/sonnet-5-5/overview)、[Opus](https://platform.claude.com/docs/en/models/opus-5-5/overview)、[Messages](https://platform.claude.com/docs/en/api/messages/create) |
| 通义千问（北京区） | Qwen3.7 Plus、Qwen3.6 Plus | [兼容接入与地域](https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope)、[思考设置](https://help.aliyun.com/zh/model-studio/deep-thinking)、[参考价格](https://www.alibabacloud.com/help/en/model-studio/model-pricing) |

DeepSeek 的 V4 Flash 旧名仍可选，但官网说明请求实际转到 V4.1 Flash，界面明确提示这一关系，后台保留所选 API 型号名。千问预设采用仍受支持的北京区公共兼容域名；其他地域 Key 不应使用该预设。

默认请求适配：DeepSeek / 千问关闭额外思考，菜单说明该默认值；GPT Sol 使用 low、Luna 使用 none 推理强度，原生 `max_completion_tokens` 与调用上限绑定；Claude 使用 Messages 协议及服务商默认推理设置。本工作台访谈／规划的请求不包含模型工具调用。没有把这些配置自动应用到 Dify 的模型节点，生成应用的模型仍单独选择并确认。

参考价用于预算估算：DeepSeek 按峰值；GPT 按标准处理的长上下文档；千问按北京区最高常规输入档；Claude 按标准文本价。不计活动优惠，缓存写入／第三方工具等额外费用不属于当前纯文本调用预估。不是账单或实际价格保证；用户可在高级设置调整，调整后注明为用户单价。目录是随版本维护的本机配置，没有调用厂商目录来证明账户权限。

## 保存与兼容规则

- 新预设必须有 Key。已有 Key 在同服务来源可继续使用，空输入不会覆盖；跨来源须填写新服务的 Key。
- 已有官方模型按地址／服务商／协议／型号精确识别进入快捷模式；其他配置保留自定义字段，不自动迁移或替换。已有配置只有主动保存才会启用所选预设请求策略。
- 同型号编辑保留自定义名称、用途和用户单价；改型号采用该型号参考价，不能沿用旧型号价格。显式调整价格优先。
- 预设不允许同时覆盖官方地址／协议／API 型号；需要代理请选择自定义。自定义会清除预设绑定；身份或预设策略变化会使旧能力证据失效。
- 选择预设和保存不会伪造可用、连接或能力验证状态。账户权限、余额、网络和实际业务质量仍以实际检查为准。

## API

`GET /api/provider-presets` 返回服务商分组、型号、地址／协议、参考价与核对日期，标记 `account_unverified`。

`POST /api/providers` 快捷请求：`{preset_id:"deepseek-flash",api_key:"用户输入"}`。后台填充字段，默认用途 main、显示名称自动生成。PATCH 可仅提交预设与需要更新的 Key；`preset_id:null` 选择自定义。名称、用途和价格仍可显式覆盖。后台返回只含 `has_api_key`，不返回 Key。

## 证据

完整后台 293 项通过，前端构建通过。9 项独立 QA 浏览器检查覆盖三步表单、必填门禁、各厂商选择、兼容入口、Key 保留／跨服务清空、自定义字段恢复与存储检查。写入响应仅在该 QA 浏览器拦截，不往用户数据库添加伪配置或运行记录。

使用已有授权 Key、临时 light 配置实际验证 DeepSeek 快捷保存、短文本及严格 JSON 对象；共 63 tokens（输入 56、输出 7），按登记峰值价保守估算 USD 0.0000252，非账单。原模型配置逐字段未变，临时配置与复制的加密 Key 已清理。GPT、Claude、千问没有用户凭据，只有官方规则核对及受控请求验证，不声称已真实连通。

证据：`work/provider-preset-ui-result.json`、`work/provider-preset-ui.png`、`work/provider-preset-live-result.json`。本次只优化模型接入，整个 136 项计划仍未全部完成。
