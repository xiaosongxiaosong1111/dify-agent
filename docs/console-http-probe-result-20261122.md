# 第369项：唯一无凭据HTTP核对结果（2026-11-22）

结论：**单次核对已执行，HTTP链仍未通过**。curl退出52（Empty reply from server），HTTP状态000，未收到有效响应头；不登录、不重试、不接续366。这个结果独立于Sierra/HTTPX调用，但不能由此断言366原异常的精确原因。

- 真实直接批准call_19a54287e07f4214acf3a0235a269efc/q0：“允许这1次无凭据HTTP核对”。[固定方案](console-http-probe-plan-20261122.md)已推70406ac，方案Git blob来自0d58fa601493f0b9a4c00013196bddf0525bebb0，SHA256 dab1c84281f239380ee71f53e5a831163f9bfcf4bcc8156fd1d289c5ac7c13f5。
- 原机work/console-http-probe369先exclusive写attempt，随后唯一运行固定curl参数。GET1、登录/模型/Task/App/发布/Key/Service全0；未读或解密data，未跟随重定向，正文NUL丢弃，仅存状态与退出码/时间。完成时间2026-11-22T04:19:43.287697+00:00（北京时间12:19:43）。
- result.json state=stopped，http_status=0（000）、curl_exit=52、management_get_attempted=1、automatic_retry=false；HTTP000不是HTTP状态码，表示没有有效HTTP响应。物理字节是否到达Nginx不能据此确定。
- attempt/result两文件已封存，seal.json SHA256 9bd03c377eeb064b667c0ab23086b76fc315c939ca2ebb49ed29d045f3f6a972；原机该目录已消费，禁止重复执行。同意本诊断不批准下一真实模型批。

## 后续本机只读观察

未追加任何HTTP请求，只读取Docker状态、Nginx语法/选定规则/日志时间窗和工具版本：

- dify-local-nginx-1仍运行，ID 496717ebcc9a5a34697d58517bfcdd82edf5921923d2668e5dc0b5a6385bf161；image sha256:f9ea18bfa4fad859e1ed38259d711da7ccad2c3516e875cec3351a57c859f571。80映射127.0.0.1:8080，443映射127.0.0.1:8443。
- nginx -t实际通过；nginx -T选定规则为listen80/server_name _，未匹配return444/deny规则。access.log/error.log分别指向stdout/stderr；固定本次时间窗未匹配到对应GET访问记录。没有导出完整配置、环境变量或响应头/正文。
- 容器内已存在curl8.14.1；只执行--version，没有容器内HTTP实测。不能据此认定Docker端口转发故障已确诊，也不能称服务恢复。

本新保守管理读取上界已登记1726，其它仍模型57/登录48/资源各30/Service148/模型估算账本3.355473652，实际模型仍36；旧unknown/settled与366预留不动。没有新增模型/运行报价，宿主费用未知，不声明免费。

下一必要核实是对比容器内与Windows的无凭据HTTP链；仅在内部鉴权可达、Windows传输失败的明确组合下，才考虑一个已核验Nginx容器的限定重启及核对。当前没有此新授权，未重启任何容器；[后续方案](console-port-forward-repair-plan-20261122.md)独立申请，不自动借用369或366范围。
