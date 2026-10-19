# HTTP 执行设置（0.39.0）

0.44追加：URL、请求方法、普通headers/params可直接在节点卡填写；原生body单独JSON编辑，无效编辑保留文字并交后台拒绝，不暗中沿用旧值。全为草稿，后续保存／确认／生成仍需主动操作；15项受控页面与构建通过，没有接口请求或原用户任务改变。认证与请求体后续契约见 http-auth-references.md / http-body-contract.md。

目标 Dify 1.17.1；依据本机安装的 graphon HttpRequestNodeData、HttpRequestNodeTimeout、RetryConfig、HttpRequestNode._get_request_timeout 与 _run，以及目标 tag 的重试面板。此处仅无认证 HTTP，不执行请求、不接受密钥。

## 明确配置

流程页逐 HTTP 节点填写草稿，保存计划后仍须当前修订配置确认才能构建。首次未指定重试时生成 `retry_enabled:false,max_retries:0,retry_interval:0`，不再固定启用 3 次重试。已生成成果和 Dify 应用不自动改写；重新生成会采用新默认，需要重新核对配置／导入／运行。

`timeout` 可缺省或 null，继承目标环境；自定义仅 `connect/read/write`，单位秒。连接 0—10、读写 0—600 严格整数，0/null/缺失字段在 Dify 继承对应环境值，不表示无限等待。`max_connect_timeout/max_read_timeout/max_write_timeout` 是平台上限元数据，不能替代请求阶段的实际超时。旧计划若把这些字段当设置会明确拒绝，用户可以主动改为继承环境或重新填写，不自动猜测转换。

`ssl_verify` 缺省 true，仅接受 bool。显式 false 可保存，会说明证书身份校验关闭；不会暗中替用户开启或关闭。

`retry_config` 若指定，须完整 `retry_enabled` bool、`max_retries` 0—10 严格整数（启用时至少 1）、`retry_interval` 0—5000 严格整数毫秒。次数不含首次请求；已关闭时保留原来休眠的次数／间隔，不推断仍会重试。界面用户主动关闭时将活动配置设为 false/0/0。

启用重试明确提示幂等性、重复提交和费用。重试与单阶段超时不是整次工作流请求次数／时间／费用的硬上限。目标 Dify 的节点引擎控制重试，HTTP executor 本身 max_retries=0，避免额外编造嵌套重试。当前错误分支、默认结果尚未适配，计划或保留校验不接受它们，不能删除后报通过。

## 节点成功不等于业务成功

原生 HTTP 节点只有配置了重试或错误策略时，非成功 HTTP 响应才进入对应失败处理；没有这些策略可将非 2xx 响应作为成功节点返回 status_code/body。网络错误仍可失败。因此关闭重试并不保证错误状态导致流程失败；用户须在条件节点明确检查 HTTP 状态与业务字段。本次只说明原生行为，没有擅自增加业务分支。

## 手改与验收摘要

保留合并校验实际 timeout、ssl_verify、retry_config；上限元数据只从临时校验投影中移除，原始 DSL 完整保留。未知配置、无效值或未适配错误策略明确拒绝。没有重新编译替换手改政策，也没有试跑证明业务副作用安全。

最终保留文件的验收语义摘要增加证书校验与重试设置。轻量建议范围升级 scope_version=4；旧启用策略必须重新核对出站范围，旧客户端不能沿用确认。此版本未实际调用模型。

## 验证边界

HTTP 策略与相关计划／保留／路由专项 116 项通过，前端构建及 9 项受控页面通过；本机 Dify 原生实体解析实际 connect=5/read=30/write=40、SSL false、2 次／1500ms 重试配置通过，发出的 HTTP 请求数为 0。完整回归结果记录在开发状态。本次不代表接口可达、重复请求安全或完整业务执行通过。
