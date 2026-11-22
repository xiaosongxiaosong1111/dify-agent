# 第370项：本机HTTP对比与限定Nginx恢复方案（2026-11-22）

状态：**拟议新范围，未批准、未执行**。369无凭据GET返回curl52/HTTP000，Nginx对应时间窗无访问记录；需要对比当前容器内外HTTP路径，不能直接假定密码错误或Docker转发已确诊。本方案不是366续跑，不调用模型或登录。

## 范围与身份

- 仅现有容器dify-local-nginx-1，ID `496717ebcc9a5a34697d58517bfcdd82edf5921923d2668e5dc0b5a6385bf161`、image `sha256:f9ea18bfa4fad859e1ed38259d711da7ccad2c3516e875cec3351a57c859f571`；容器80→宿主127.0.0.1:8080。执行前重核ID/image/running/端口、nginx -t，任一不符停止，不替换目标。
- 最多新增4次无凭据管理GET：管理预留1726→1730。最多限定重启同一Nginx容器1次，可能短暂中断Dify网页/API访问。API/数据库/其它容器及Docker Desktop不重启，不重建/删除容器或网络，不修改卷、镜像、端口、环境变量、账号与凭据。
- 登录/产品模型/Task/App/发布/Key/Service/新库新增全0，其它保守上界仍57模型/48登录/资源各30/Service148/模型估算账本3.355473652。无新增模型或运行报价，宿主费用未知，不承诺免费或账单硬限；旧366/369及全部旧槽和费用保持不退借。
- 每个GET连接3秒/总10秒；从首GET前开始的GET/重启窗口最多120秒，不含前置本机哈希和最终封存。每次操作前核剩余窗口，至少足够该操作最大超时才派发，否则停止。重启命令外层最多30秒，只有退出0且30秒内完成才继续；非0/超时/状态不明均停止，不重复重启或继续GET。

## 唯一顺序及分支

1. 先在原机work/console-port-forward370下exclusive记录实际新直接批准ref和方案摘要/容器身份/attempt，已有attempt拒绝。以只读hash捕获原机十二数据根、旧758/366封存/369封存；不解密凭据。保存Nginx三份实际配置SHA256，不输出配置正文。
2. 第1 GET：用现有容器curl访问`http://127.0.0.1:80/console/api/apps?page=1&limit=1`。只有curl0且HTTP401/403视为内部鉴权入口可达；否则记录并停止，**不重启、不追加后续GET**。
3. 第2 GET：Windows原机固定目标`http://127.0.0.1:8080/console/api/apps?page=1&limit=1`。若curl0/HTTP401或403，两端可达，结束，无重启。其它已知HTTP状态（包括3xx/5xx）或未知输出立即停止，不用重启猜测上游问题。
4. 唯一限定恢复例外：内部已401/403，而Windows第2 GET为HTTP000且curl退出**7、52或56**之一，才允许在再次核同一容器身份后执行一次`docker restart --timeout 10 496717ebcc9a5a34697d58517bfcdd82edf5921923d2668e5dc0b5a6385bf161`，本机docker restart --help已只读核支持--timeout，外层30秒超时且必须退出0。Windows超时28或其它技术异常不进入此例外。
5. 重启后重核同ID/image/端口/running、nginx -t和三配置SHA未变；不符合即停。第3 GET核内部，仍须curl0/401或403；通过才第4 GET核Windows。第4 GET须curl0/401或403才记**当前无凭据HTTP鉴权入口可达**，否则停止。无第二次重启、不增加GET、不登录或自动续下一真实批。
6. 仅读窗口内Nginx access/error日志，按固定GET路径/诊断User-Agent与执行时间窗统计匹配状态或未匹配；不输出其它请求、正文、头或日志原文，不新增HTTP。日志读取失败只记不可用、不重试，不把无记录当确定网络根因。所有分支追加本机结果并封存；对比十二根与所有旧封存，若用户并发改动则记录差异、不回滚、不覆盖用户状态。没有任何结果可证明366原故障根因、凭据/空间有效、自然到期续接或自主模型质量。

## 固定保护清单

- 生产数据根E:/workSpace/dify-agent/data，另11根按`work/autonomous-dual366/plan.json`的isolated_paths逐项读取；该plan原始SHA256必须为a0dbdd41423f9a3076958201f1d8ae911324e63b04abdae77b0efa2cd7ce3dff。只为前后摘要读取本机任务/环境记录与密文字节，不输出记录正文、不解密秘密字段；捕获本次当前基线（包含366合法失败标记），不拿旧批准前的环境摘要当新基线。
- 旧758文件按该plan.protected_files逐项核；366的`work/autonomous-dual366/seal-after-stop.json`索引26文件且索引SHA必须bb6ab4daf437039b71b844748d881752030db17ef9f07cf5602b24cfc6856803；369的`work/console-http-probe369/seal.json`索引2文件且索引SHA必须9bd03c377eeb064b667c0ab23086b76fc315c939ca2ebb49ed29d045f3f6a972。两索引本身也保护，合计788文件，不改写/重新封旧包。
- Nginx实际配置固定为`/etc/nginx/nginx.conf`、`/etc/nginx/conf.d/default.conf`、`/etc/nginx/proxy.conf`，只用容器sha256sum读取摘要，前后核相同，不输出配置正文。身份/文件缺失或摘要变化停止，不写入或修复配置。

## 固定GET参数

Windows使用现有C:/Windows/System32/curl.exe；内部使用`docker exec <上述固定ID> curl`。每次仅一URL，首个curl参数均`-q`，共同参数为：

```json
["-q", "--request", "GET", "--noproxy", "*", "--proto", "=http", "--connect-timeout", "3", "--max-time", "10", "--max-redirs", "0", "--header", "Authorization:", "--header", "Cookie:", "--header", "Proxy-Authorization:", "--user-agent", "Sierra-local-connectivity-diagnostic", "--write-out", "http_status=%{http_code} curl_exit=%{exitcode}"]
```

以上每项是一个完整参数，通过参数数组调用，不经shell拼接。Windows另加`--output NUL`、内部另加`--output /dev/null`，最后传本步骤唯一固定URL。禁用curl配置、代理、认证与Cookie，无重定向/重试；响应正文/头不入日志，只存状态、退出码、时间和分支。容器curl8.14.1见369结果；Windows8.10.1已在[369方案](console-http-probe-plan-20261122.md)的本机工具核对中记录，均只读确认，未为此发HTTP。

这是一段由根操作固定本机命令的运维诊断，不新增产品执行框架或更改产品代码。根逐步判断并记录每个GET计数；任何未知异常停止。对第2 GET三种明确失败的限定重启是本方案**新申请**的完整例外，不能推广到旧消费批。

## 批准边界

当前仅提出新完整范围，尚未执行。AGENTS.md委托限于“within existing explicit resource and cost bounds”，旧366/369已消费，不能自动跨批借其读取；新增4GET及限定重启1需要这次明确批准。申请直接答复“允许最多4次核对及最多1次限定Nginx重启”后才唯一执行；不将答复扩大为新模型、登录、资源、无限重启或后续自主批。修改目标/重启条件/次数时重新审查，不自行放宽。

## 本机方案复核

DeepSeek只读复核返回，根采纳端口措辞、重启退出0条件、日志证据与具体保护路径/时间窗口澄清；根另据本机docker restart --help将原不匹配的--time改为实际支持的--timeout（仍10秒，不扩大范围）。未修改产品代码/新增后台框架，未做内部HTTP或重启实测。根已逐项核查最终版，独立实际核788旧文件/新封存摘要，370仍无attempt；不把方案审查当恢复通过。
