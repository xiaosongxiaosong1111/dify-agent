# 366登录不可达：代码与本机核实（第368项，2026-11-22）

结论：现有实现能安全记录并停止本次失败，未找到足以要求修改产品代码的离线实质缺陷；**实际传输失败的细类与根因仍未确定**。这不是自主双版验收通过，也不是HTTP连通恢复证明。

- DeepSeek只读会话b2ba18b4-f43f-4563-a537-3f793821581a正常返回，日志work/mainline367-ds-diagnosis.log。范围为337共享执行器与dify.py/saved_console_reconnect.py/console_failures.py和直接测试；未给它真实回执、凭据、客户资料或data。根已阅读全文并抽查关键路径。
- root核实际环境目标是http://127.0.0.1:8080，非开发DS网关。dify.py:97的显式直连transport使HTTPX不选择继承的环境代理；这不能排除系统层过滤、临时连接中断或其它传输故障。
- dify.py:185的login在POST后才进入应用列表probe；非超时RequestError在此阶段映射login_unreachable，超时/拒绝/5xx/不兼容内容分别有别的固定码。因此本次不是已知HTTP401或账号拒绝，也不是后续管理GET失败；未记录原始子类，不能进一步断言拒连或断流。
- saved_console_reconnect.py:137及console_failures.py:63已有安全分类持久化、原连接绑定和自动登录暂停；新Token只在空间证明后提交。journey只携带正常API状态，未复制安全头码到批摘要，但产品持久化记录可核，不是本次必须新增的一份重复诊断。泛化保存异常文本会带入秘密，不做。
- DS指出崩溃窗口下恢复可记reconnect_interrupted；这是未知结果的保守处理。本次为正常stopped/failed，不能拿假设崩溃作为本次根因，也不为此重构跨事务逻辑。
- 根独立执行现有定向命令：`E:/workSpace/dify-agent/.venv/Scripts/python.exe -m pytest backend/tests/test_console_failures.py::test_login_failure_codes_are_specific_and_never_echo_body backend/tests/test_dify_loopback_transport.py -q --tb=short`，**30 passed**。现有用例使用transport替身/网络前阻断或仅检查客户端路由；真实模型/Dify HTTP为0，日志work/diagnosis368-root-tests.log。没有新测试或产品修改、全量或重新部署。
- 原机Docker/端口在、失败窗日志未匹配登录、独立TCP握手成功的边界见[真实停止记录](autonomous-dual366-live-result-20261122.md)；TCP成功不证明应用层HTTP。原批已经封存，不再登录/读取/续跑。

下一可行动事项是一次**无凭据、无登录的HTTP GET**，区分当前是否能抵达Dify的HTTP鉴权入口；[具体369方案](console-http-probe-plan-20261122.md)与任何后续自主模型整批分开。仅提出，不借用366未派发读取，不预判结果，不新增常驻框架、诊断UI或模板图。其它当前自主质量、迁移和自然到期缺证仍按原矩阵保留。
