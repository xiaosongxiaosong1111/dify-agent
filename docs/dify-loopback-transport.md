# 本机Dify显式直连（0.348，第204）

零HTTP核对发现：即使四类代理环境变量为空，HTTPX默认仍为127.0.0.1:8080选择AsyncHTTPProxy。本轮管理员上下文核原Dify栈和Sierra健康；这证明当前有本机代理路由问题，不能唯一归因旧202的HTTP502。

DifyClient的请求、登录、登录后工作空间核对三处，对localhost（大小写/结尾点）和IP literal loopback采用显式无代理AsyncHTTPTransport；不做DNS解析，10.x私网和远程主机保持原代理。运输仍trust_env=True，保留HTTPS CA环境，不修改系统代理或verify设置；原超时/禁止重定向/认证/原空间/失败暂停合同不变。

17新增及102相关共119定向检查通过：系统代理模拟下本机直连、远端保持代理、三类客户端和TLS环境标志、固定响应登录/访问/工作空间三步；相关认证/失败暂停/就绪回归保持。零HTTP实际构造本机改为AsyncConnectionPool，远端仍AsyncHTTPProxy。真实HTTPS握手、重新登录及C1链未验收，未全量。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_dify_loopback_transport.py backend/tests/test_login.py backend/tests/test_dify_reauth.py backend/tests/test_console_failures.py tools/test_c1_local_readiness.py -q -p no:cacheprovider --basetemp work/pytest-loopback359-final
```

固定快照0.348.0-06fd6ec09994a7bc45a6/287文件已按原PID35976及347快照/执行文件核验后用原stop/start部署，当前PID26424，health及前端200、源码/快照摘要一致。原18Task/预算/密文主Key资产及所有消费回执保持，只更新server.pid；最新基线work/loopback359/post-deploy-data-snapshot.json。[安全结果](dify-loopback-transport-result-20261028.json)。

旧Docker诊断解释修正：此前管道/进程观察来自受限上下文，不能证明引擎当时停止；辅助服务Stopped也不等于引擎停止。确曾执行启动既有服务/Desktop命令并随后核到健康，但启动前未留下管理员上下文证据，不能据此确定502根因。旧202响应/失败状态/计数/费用及冻结文件原样保留，相关文档加解释修正。以后在实际运行权限下检查，区分检查不可访问与服务停机。

本次新增真实Dify/模型HTTP0，未重放357或清除暂停。预留仍573/34、模型保守30/账本0.755473652、资源各12/运行22；未派发5模型槽不自动改授。C1与原Chatflow订单链仍未通过。
