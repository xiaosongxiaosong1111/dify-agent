# 新空任务界面主链隔离预检

仅在临时工作区预置一个公开合成模型配置；Task必须由浏览器新建，经正常访谈、来源检查、需求/配置确认、模型流程入口、候选采纳、构建、修改、两版ZIP下载。没有使用approved助手、直写Task、关闭intake_required/plan_review_required或补造已运行记录。

模型固定替身共5次，记录的用量也是合成值；真实HTTP运输及Dify客户端全部拒绝，浏览器只访问临时本机服务。图来自已提交的公开合成静态夹具205本地回放，唯一修改为无命中提示。断言第一轮追问不构建、整理后不自动确认、修改使旧批准失效、422变更候选保留原图并需主动采纳；核两版ZIP摘要、同Task/递增修订、只改一个图字段，平台/业务未验证标志保持。无发布、Key、新平台资源、模型HTTP或Dify运行，不关闭C1真实验收。

命令在项目根执行，output必须是work下尚不存在的目录；使用既有Edge及指定绝对Playwright模块，不装浏览器、不另起18760：

```powershell
.venv\Scripts\python.exe tools\mainline-ui-preflight347\check.py --playwright "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright" --output "E:\workSpace\dify-agent\work\mainline-ui-preflight347\new-run"
```

服务随机本机端口，静态文件由backend从frontend/dist供给；完成/失败都关闭临时服务并清理本工具创建的临时数据库。原工作区仅比较逻辑对象/密文/资产摘要，不解密或输出秘密。结果只写指定work目录，原生产数据、旧批次及费用边界保持；存在生产数据时运行前后必须完全一致。输出不会覆盖旧目录。

此工具是一次完整静态用户链的可复现核对，不验证真实模型建议质量、Dify导入/运行或全25项业务，也不自动发起后续真实批次。
