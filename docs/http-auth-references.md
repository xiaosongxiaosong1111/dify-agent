# HTTP 空秘密变量引用（0.41.0）

Sierra 生成认证节点与空秘密环境变量，用户在导入后的 Dify 工作流环境变量中补齐实际凭据，再发布／试跑。Sierra 没有该接口密钥输入框，不接收或保存密钥；DSL 中只有变量名称、用途说明、空值和 `{{#env.NAME#}}` 引用。未补齐凭据不能运行，静态通过不代表已交付或接口认证正确。

## 计划契约

HTTP config 可指定 `authentication`，必须恰好四项：

```json
{"type":"bearer","secret_variable":"SERVICE_AUTH","description":"客服查询接口认证，导入后由用户在 Dify 填写。","header":"Authorization"}
```

缺省/null 表示无认证；支持 bearer、basic、custom。变量名 1—64 位字母数字下划线，不以数字开头；用途说明 1—2000 字，不填写实际凭据。Bearer/Basic 的 header 必须为 Authorization。Custom 明确填写合法单一请求头名称，不支持 Cookie、Set-Cookie、Proxy-Authorization、Host、Content-Length；普通 headers 不能重复认证头。接口需要 OAuth、Cookie、签名或查询参数秘密时尚未适配，不能改为无认证后算完成。

Bearer 在 Dify 变量中填 token 本身，平台添加前缀；Basic 在 Dify 变量中填写 `username:password` 原文，平台编码；Custom 填入接口要求的值。此说明不是邀请在 Sierra 的用途／需求里写入凭据。JSON 多出的 value/password/api_key 等字段、明文或拼接引用一律拒绝，不静默过滤后继续。

同名表示共用一份凭据，多节点用途说明必须相同，否则拒绝；不同名称独立声明。ID按变量名确定，导出 value_type=secret、value=''、selector=['env',name]，不会编造实际值或存入浏览器。仅顶层HTTP节点适用，迭代／循环内部HTTP仍未适配。

## 原文件安全读取与手改保留

原生 authorization.type=api-key 的 api_key 字段仅在**实际 HTTP 节点的授权配置路径**，完整引用合法已声明空secret变量时允许。其他节点／配置／独立字典中的同名 api_key 字段仍被拒绝。声明必须是合法UUID、唯一名称、空字符串（掩码、null、非空值均拒绝）、有限用途说明和正确selector；认证config仅type/api_key/header。引用非secret、未声明变量、拼接文本、未知字段、普通headers重复认证均拒绝。

只投影为计划进行静态校验，原声明／授权／变量ID／说明／布局保留原文，不重新编译或删除认证。读取新文件仍执行2MB、无重复键／无共享锚点、有限结构、疑似明文值检查。Dify `include_secret=false` 导出会清空 SecretVariable 值，实际填写的凭据不进入 Sierra。

验收语义摘要保留授权引用，并列使用的秘密变量名称／用途／未验证就绪标识，不发送变量值。轻量建议范围升级 scope_version=5，旧启用策略必须重新确认，未确认不派发或改用主模型。本次未调用付费模型。

## 原生证据及局限

本机 Dify 1.17.1 VariableFactory／SecretVariable、Executor.__init__、授权头组装与日志渲染已只读核对。新内存原语检查三类开发假凭据的模板转换和授权日志遮蔽通过；空值在请求前抛 AuthorizationConfigError。测试IO对象禁止所有访问，HTTP请求0、整工作流运行0、生成代码执行0；不读取本机真实接口密钥，不接触客户数据。这只证明这几项原语，不保证远端服务器会接受凭据，或第三方响应／所有平台日志不会返回敏感资料。

受控页面13项通过，三类认证输入、主动切换、原HTTP策略回归均在本地草稿，原用户任务未改变；后台完整结果见开发状态。
