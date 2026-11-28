# 第392项：已冻结run入口的限定核对（2026-11-28）

DeepSeek find正常返回0，会话4f3cd25c-6e51-4ee1-a02d-0b4e185fdbda；只读必要调用链，未改代码、读生产数据或执行命令。根审完完整报告与必要源码，并独立验证。源仍f9aa9f0，390 canonical及plan1abf2fad/manifest505eee5f保持。

## 结论

没有发现编译预检会提前初始化生产Store、manager仍绑定旧Store、transport恢复不闭合或正常入口必然停止的确定性错误。报告指出的两项条件性边界分别处理：

- 其它任务有待恢复状态时，TestClient lifespan可能触发全库恢复写入；既有Guard会拒绝。根检查已有完整冻结对象快照和准入比对，再用实际211个对象元数据仅在内存、新临时目录与只读适配器执行真正lifespan；不复制生产对象到磁盘、不解密、HTTP禁止、直接数据库连接禁止。21次读取，写入/秘密/HTTP/直接连接尝试全部0，12根909前后相同。因此本批当前状态没有该触发条件；不能保证未来任意运行中状态都可以直接复用。
- 在建立live-output/attempt/worker的文件系统异常窗口，可能保留不完整消费标记。按已批准一次消费规则保持封存，不能按建议删除标记或自动重放；未观察到本机触发，不据此修改冻结包。实际发生时保留现存证据并停止。

这是一项源码和隔离启动验证，不是完整tool.run或真实Dify通过。根没有添加覆盖率用例或新审批框架，也没有放宽旧数据保护。仅在当前状态核验后进入已经直接批准的391。

## 证据

- `work/reviewed-run392-ds-find.log`：完整DS报告；两个问题明确标注条件性/未实证，根未将其全部当已证实bug。
- `work/reviewed-run392-root-startup-proof.json`及log：根独立真实lifespan/内存元数据结果；私有脚本sierra-delegation/verify-reviewed-run392-startup.py。
- `work/reviewed-run391-preflight.json`：冻结源、运行快照与12根909仍相同，canonical无approval/attempt/worker/live-output。

本机原Docker Desktop服务停止导致8080无监听；根核已有CLI/服务路径E:\workSpace\DockerDesktop，按原安装隐藏启动服务。原16容器自动恢复，未创建/重建/改配置或卷；API镜像langgenius/dify-api:1.17.1、项目dify-local/原目录E:\workSpace\dify\docker，Docker health healthy、8080监听。没有额外Dify HTTP探针或登录。
