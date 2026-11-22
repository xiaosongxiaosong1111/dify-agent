# 第369项：单次无凭据HTTP连通核对方案（2026-11-22）

状态：**新范围未批准，未执行**。目的仅为核对366首次登录失败后，当前本机HTTP链能否抵达Dify鉴权入口；不发送账号、密码、Cookie、Token或模型Key，不登录，不重放366。原始原因无法由这次新观察回推。

## 单次范围

- 固定目标：`http://127.0.0.1:8080/console/api/apps?page=1&limit=1`，现有Dify 1.17.1适配器的应用列表入口，发送1个无凭据GET。
- 新管理读取上界仅1，总预留1725→1726；登录仍48、产品模型57、资源各30、Service148、模型估算账本3.355473652全不变。原366未派发128读取及其它槽/费用保持，不自动改授或退借。
- 新Task/App/发布/Key/模型/Service/登录均0。无新增模型或运行报价，宿主费用未知；不声称管理读取免费或账单硬限。总超时10秒、连接超时3秒，单次，不重试、不追随重定向、不触发后续真实批。
- 采用本机已存在C:/Windows/System32/curl.exe 8.10.1。已仅读本机help核对所需参数；没有为检查help发出HTTP或读取配置/凭据。

## 固定执行命令（获准后唯一运行）

在原机E:/workSpace/dify-agent由根执行：

```powershell
curl.exe -q --request GET --noproxy "*" --proto "=http" --connect-timeout 3 --max-time 10 --max-redirs 0 --header "Authorization:" --header "Cookie:" --header "Proxy-Authorization:" --user-agent "Sierra-local-connectivity-diagnostic" --output NUL --write-out "http_status=%{http_code} curl_exit=%{exitcode}" "http://127.0.0.1:8080/console/api/apps?page=1&limit=1"
```

- `-q`必须是首参数，忽略用户curl配置；显式绕过代理，空凭据头不发送值。无`--location`、`--retry`、cookie文件、认证或证书资料；只接触固定IPv4 loopback目标，不解析外部主机名。
- 响应正文丢弃到NUL，不导出头、Cookie、应用列表或其它正文，只保存HTTP状态/curl退出码及本机时间。HTTP401/403只证明到达鉴权入口，不判断密码或空间；其它HTTP状态按实际记录。000/非零curl退出码只按错误类别记录，不宣称必然是远端停机。
- 获准前无attempt。获实际新直接答复后，在新独立work/console-http-probe369下exclusive写入一次attempt，绑定方案SHA和实际新call_ID/q0；已有attempt拒绝执行。无论结果成功/失败均封存，不重试，不改专用连接/自动登录暂停状态，不读或解密data。
- 这是根的单次运维诊断命令，不新增产品源码或执行框架；根记录结果、更新CHANGELOG/README/HANDOFF并提交推送。所有原26任务、十二根、旧封存和账本保持。

## 与用户授权的关系

旧366已经异常停止，禁止在其128读取余槽里继续；本次新增1读取是独立范围。按AGENTS.md“within existing explicit resource and cost bounds”需要明确批准。申请仅此一GET，不申请下一轮模型/资源/登录，不把本次同意当作后续自主批批准。用户可选择“允许这1次无凭据HTTP核对”或暂不执行。
