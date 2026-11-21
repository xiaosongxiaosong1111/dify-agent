# Windows安装与启动复核（2026-11-21）

BACKLOG364／交付项31。DeepSeek会话3f9585f1-0f7d-4bd6-85d2-3cecb7d6a41a修复，Codex独立复现、核全部差异及验收。

## 结果和改动

缺项目虚拟环境时原start.ps1返回英文错误；当前在Windows PowerShell5.1明确提示“项目 Python 环境缺失。请先运行 .\setup.ps1。”并保持exit1。setup/start/stop的35个自定义消息token改中文，三PS脚本使用UTF8 BOM；start.cmd两个echo改中文并设置本次控制台UTF8。pip/npm及PowerShell引擎自身的输出仍由上游提供。

外部固定检查核三脚本Parser、编码、全部非消息token及插值一致、CMD仅编码命令和两处echo变化。端口8765、进程归属、Python/Node门槛、锁文件、参数、退出码、健康检查和停止逻辑未变；未改依赖或业务功能。DS首次插值顺序核对未过后自行修正，根最终重新检查通过；未添加等价产品测试。

## 实际干净安装

以Git跟踪文件全新解压到仓库外受控目录，无用户数据库/凭据、旧venv/node_modules/dist/runtime。覆盖待验四脚本后按README实际执行setup.ps1，创建独立venv、安装backend/requirements-lock.txt、npm ci并构建前端，exit0。新venv Python3.13.9、Node20.20.2；40个锁定Python包逐一相符，include-system-site-packages=false。依赖来自正常安装，未复制原venv或修改全局Python/Node包。构建的体积提示保留，不据此做无关拆包。

实际脚本8场景通过：缺前端、缺后端中文exit1；无效PID仅清本目录记录；误指原服务PID拒绝停止；8765占用拒绝且原PID不变；新空Store固定快照启动及health/页面200；重复start保持同一所属PID；受控stop后恢复原快照。另缺venv中文exit1通过；既有test_runtime_snapshot.py **6 passed**。未交互双击CMD或覆盖每一种包管理器/网络失败，不称所有系统安装通过。

首轮私有验收壳用嵌套PowerShell原生管道等待后台子进程，临时服务实际健康但验收未结束；先只按CIM/精确Python和项目路径停临时服务、恢复原服务并核数据，再改验收壳为隐藏独立进程/保留句柄读取退出码。空JSON数组计数也在验收壳修正。产品启动停止逻辑不为验收改动；这些失败不冒充通过。最终8场景完成，临时进程已停止，未按端口杀进程。

## 原机与边界

原26Task无执行中/待返回运行后，按保存PID、CIM命令和执行文件核归属，暂借8765运行临时服务，finally恢复原机。当前原机0.410.0-23c94dbe89553f265c3b／298文件／PID28732，health和页面200，源码/快照/执行文件相符。新安装的独立构建为0.410.0-927d5bcdead167690e49，未用空数据或新构建覆盖原机。

原work/install364-verification/before.json、after.json（首轮恢复）、after-final.json（最终）证明十二数据根、26任务及密文/资产、733旧封存和337封存24文件保持。仓库外install364-340f044e2c3b4f22942a54e51365ee99含源码包、setup.log、各场景日志和verification.json；这些不入Git。实际产品模型/Dify HTTP为0；普通公开依赖下载及开发DeepSeek调用另计，不当作供应商免费。

本项只核受支持Windows路径和已有使用合同，不关闭自主售后双版、真实客户权限、订单接口或轻量模型收益。后续质量/用量/费用按BACKLOG365另核。
