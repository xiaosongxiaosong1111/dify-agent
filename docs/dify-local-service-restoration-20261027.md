# 既有Dify基础服务恢复（第182，2026-10-27）

第180一次性真实批首次登录502后已停止，本次仅沿用户此前明确要求启动本机Dify的授权恢复既有本机服务，不重放登录或后续阶段。

先确认原Docker CLI/安装位置和desktop-linux context，无现有Desktop进程，服务Stopped。只启动既有com.docker.service和E:\workSpace\DockerDesktop\Docker Desktop.exe，窗口隐藏；未执行pull/create/compose up或新建卷、容器及Dify资源。

启动后原dify-local的16个容器均可核对，创建时间全早于本次操作：15个运行，原init_permissions为两周前正常退出的初始化容器；API/Sandbox/Postgres/Redis/local_sandbox五项健康，镜像Dify 1.17.1，原Nginx在127.0.0.1:8080监听。特权辅助服务启动WSL引擎后可再次Stopped，不能只据该Windows服务状态判定引擎未运行；本次以Docker引擎管道、原容器及健康元数据为准。[结构化证据](dify-local-service-restoration-20261027.json)。

未读取完整容器环境/凭据、未修改用户模型和登录、未进入Dify Console/Service API；新增Dify HTTP/登录/模型/运行均0。所有Sierra原16任务、180允许诊断状态、密文/主Key/资产及180批准/消费回执逐项保持。Sierra继续运行0.342.0-a531de7dd66e803432c8，没有另行部署。

原180的登录1/管理0/资源运行0失败和管理429/登录29预留保持，不归还/借用，不因恢复服务就重试。尚未取得恢复后的登录或Sandbox业务成绩，也不证明502唯一根因。

T078原先因Docker未运行无法验证独立隔离代码样例；引擎恢复后可继续受限本机执行器开发，不调用Dify或宿主exec。既有公开Dify API镜像的ID/仓库摘要及入口已只读核对，未执行镜像。实际样例执行必须放入独立后续开发项，使用无网络/无宿主挂载/只读及资源/耗时界限、明确来源与输入输出，不能拿容器健康当代码结果。
