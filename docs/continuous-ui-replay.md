# 连续界面回放与运行容量修复

0.262.0已部署，快照0.262.0-dab832fdb2a7f56e9cef。当前真实r5任务已累计2/2且后端can_start=false，旧界面仍允许点击运行；现运行按钮和提交处理都要求当前任务、修订和运行记录对应的预检允许启动。读取中、失败、无效数量或上下文变化时暂不允许；上限未自动调整，后端原有原子检查保持。

单例启动采用limits.can_start，不能用整个计划的limits_allow_requested_runs代替：剩余1次而计划2次时，单例仍可启动。构建、真实任务只读复现/修复/部署检查，以及未知、1次剩余、无效输入的隔离分支通过；没有实际派发运行。

第64项用第63项已存真实访谈草案重建固定响应，第53项不同上下文生成的完整图及第57项保存输出，连续操作需求确认、两例声明、配置、规划、构建下载、模拟导入/发布/Key、两例和交付下载。10项界面检查通过，源13任务全部对象/密文/主密钥保持，临时服务和数据清理。两次固定模型响应、App/发布/Key各1及运行2全部为隔离模拟；真实模型/Dify/源凭据读取0。

这是跨历史响应拼接的界面衔接验证。它没有证明新自然要求经当前真实规划模型得到正确图，也没有新做真实平台浏览器全链或25场景业务签收。访谈首轮“不生成流程”限制保留，配置资源计划明确进入模拟后续规划阶段；未手改已存模型需求或候选。

本机证据命令（work不入Git）：

```powershell
npm.cmd --prefix frontend run build
node work\run-capacity-262-branches.cjs "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
powershell -ExecutionPolicy Bypass -File work\continuous-ui-replay-262\run.ps1
.venv\Scripts\python.exe work\workspace262-check.py after
node work\run-capacity-262-deployed.cjs "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"
```

回放脚本曾修正标签匹配、等待和成果结构断言后通过；所有重跑均为禁出站的临时模拟，无真实批次重试。未跑全量测试。详见[安全结果](continuous-ui-replay-result-20261023.json)。
