# 本机Dify消费前就绪检查与失败HTTP传播（203）

2026-10-28第204诊断修正：此前Docker不可达观察来自受限上下文，不能证明引擎当时确实停止；com.docker.service停止也不等于引擎停止。管理员上下文现栈健康；已零HTTP复现系统代理把loopback路由到代理的问题并修复，仍不能唯一归因旧502。实际登录502、原失败状态/计数/费用及冻结回执保持。见[dify-loopback-transport.md](dify-loopback-transport.md)。

2026-10-28，第202真实批在Dify登录502停止，模型/管理/资源运行0。离线引擎管道不存在、Desktop进程不在；本次恢复原com.docker.service和原Docker Desktop，未重新登录或重放357。16容器名称和镜像与182恢复一致、创建时间均早于2026-10-27；15运行、原初始化容器正常退出，API/Postgres/Redis/Sandbox/local_sandbox五项健康。没有pull/create/compose up/新卷或新App操作。

## 修复后的开发源码

local_readiness.py只适用于该工作区已知的http://127.0.0.1:8080或localhost:8080以及原dify-local栈；远程目标不借宿主Docker推断。只运行带固定参数的Docker version与只读ps，限制超时和输出，只解析名称/状态/镜像/端口等白名单元数据，不读取容器环境或日志。检查16个必要原服务、正常初始化、5项健康、Dify核心镜像1.17.1及Nginx的8080映射；失败只返回固定安全码，不反射CLI错误/正文，不自动启动或重试。

开发源码execute把本机就绪核对和原Sierra/快照/来源检查放到claim之前；服务未就绪不创建attempt、不登录。就绪只表明本机运行元数据满足此有限检查，不能证明URL、认证或业务正确，也不能取消在途请求。检查不能替代批次授权、真实登录及工作空间证明。

包装器收到非成功HTTP后先halt禁止任何后续出站，再把已读取的原response交给现有SDK。这样登录401/403与500/502/503可得到原login_rejected/login_service_error和HTTP状态，不被包装器RuntimeError遮盖；不记录原响应正文。预期未发布404依旧走既有特殊分支，其他错误不会继续或自动重连。旧202的unclassified回执不回写，不把历史失败改成新分类。

只修改tools/c1-existing357开发源码，新增local_readiness.py使未来完整源码集合为19文件。work/c1-existing357原18文件、plan/manifest/approval/attempt/worker-started和所有旧消费包逐字保持，永久消费，不复制新代码到旧包。当前没有新冻结执行包或批准；未来若要真实核对必须独立方案/身份及明确范围，不能直接使用修复源码或借旧5未派发槽。

## 定向验证与保护

23项隔离检查通过：引擎不可用/超时/格式错/过大输出、容器缺失重复/停止/不健康/启动中、异常初始化/版本/端口、远端不探宿主、本机就绪失败不claim；模拟登录401/403/500/502/503经真实SDK得到安全分类，下一次派发在运输前拒绝。66项原入口/来源/资源门禁仍通过，源码替身登录503整链在login1/read0/model0/其余0即停，实际物理HTTP0。

```powershell
.\.venv\Scripts\python.exe -m pytest tools/test_c1_local_readiness.py -q -p no:cacheprovider --basetemp work/pytest-local358-final
.\.venv\Scripts\python.exe tools/c1-existing357/gates_check.py
```

本机实际只读Docker元数据检查通过，未访问Dify HTTP、登录、模型或运行。服务恢复后Sierra18Task、全部对象/账本/密文资产主Key与357及全部旧消费摘要完全保持；原环境自动登录暂停仍保持，旧服务Key不变。当前产品仍0.347.0-1b052af3a24e6f1d591e/PID35976，不改产品运行快照或跑全量。最新基线work/local-readiness358/post-recovery-data-snapshot.json（与357 post-stop相同），[结构化安全结果](local-dify-readiness-result-20261028.json)。

C1真实主链仍未通过，原Chatflow订单链未验收；服务健康不算恢复登录或业务通过。本次不再制造新付费准备或申请旧批重放。
