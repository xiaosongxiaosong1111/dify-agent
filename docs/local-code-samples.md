# 根Python节点的本机受限样例（0.343，第183）

流程页新增“本机受限Python样例”。选择当前已保存的根Workflow Python代码节点，逐字核对代码，明确填写参数JSON，先准备方案，再核对隔离/输入并单次执行。输入键须与节点别名完全一致，不读取真实上游、不补默认值，不执行嵌套/JavaScript/引用DSL或过期计划。

执行和返回单独保存为本机样例回执，不改任务需求/配置确认、成果、原Dify试跑次数或账本。通过仅指实际返回顶层字段和基本JSON类型符合声明，不判定业务准确、JSON Schema深层约束或完整流程正确；目标Dify Sandbox仍需独立真实范围。

## 首批范围

- 同步main及明确入口；32KiB代码/4096 AST节点；纯计算、字面常量、常见字符串/数组/字典方法及有限math/json接口。系统/文件/网络导入、反射、私有或未开放属性、str.format/format_map、模式匹配、类/装饰器/异步/动态入口及裸捕获终止信号拒绝，不改代码后勉强执行。可用f-string表达已开放的普通数据计算。
- JSON对象输入原文最多64KiB，拒绝重复键、非有限数、小数往返损失/下溢和超过32层；保留原文摘要及Python可表示的大整数。返回最多32KiB，按原JSON文字显示，不经浏览器数值重解析。输出仅核完全相同顶层字段、string/number/boolean/object及对应数组；bool不算number，复杂children约束明确拒绝。
- 固定本机已安装的公开langgenius/dify-api:1.17.1镜像ID/仓库摘要ceede5b9，不自动拉取或替换。只使用其系统Python运行独立worker，覆盖应用启动入口，不启动另一个Dify应用。[1.17.1镜像源码](https://github.com/langgenius/dify/blob/1.17.1/api/Dockerfile)。
- 一次只执行一个本机样例，临时容器按服务端UUID命名/标签及固定镜像归属；无网络/宿主文件挂载/端口发布，非root65534、只读根文件系统、移除全部capabilities、no-new-privileges，核默认seccomp；128MiB且无额外swap、1 CPU、32进程、计算壁钟3秒/CPU硬限4秒，宿主start等待8秒，打印4KiB，控制CLI另有有界超时。准备和清理不计作“计算8秒内全部完成”。[Docker运行参数](https://docs.docker.com/engine/containers/run/)。
- Docker CLI只连本机指定管道/套接字，使用新建空认证/代理配置；不读取原Dify容器环境，不继承用户Docker登录或代理到计算容器。用户代码只经容器stdin进入，宿主不exec用户代码；worker有Linux/UID/显式marker检查。容器创建后再核实际隔离参数，结束仅按UUID标签/名称/镜像核归属清自己的资源。

## 来源、失败与恢复

准备绑定Task修订/完整保存计划、节点代码、输入原文及JSON摘要、worker/镜像/资源边界。代码、输入、工作区草稿或新任务选择改变会清旧确认，服务器执行前重核；方案过期或已使用不重发。同一页提交后响应丢失，明确“只读核对本机样例回执”，已知proposal ID必须匹配，不能拿另一份同代码同输入的准备回执替代。没有自动重试。

运行期间原Task写操作由后台忙门禁阻止，暂停后的在途结果仍保留为旧来源。进程中断转unknown，不自动新建容器或重执行；异常正文不作为错误回显，只保留类别。输入/代码本体不复制到准备记录，返回属于用户选择的本机样例结果。

容器清理未确认时保持unknown，显示预期容器名，不能把未知改成通过；首批需要操作者按归属核对残留。已完成的执行与清理是分别记录的事实。后续显式归属核对/清理和旧修订历史入口仍需补，不能为了再次执行清空旧未知记录。

## 验证与部署

新103/原入口契约25后端，共128通过；10个真实本机临时容器场景含JSON/math/大整数/错误/输出/超时/未知清理，所有测试资源最终按归属清理。界面10通过，其中3次真实本机计算，包含响应丢失后只读恢复、错误代码/边界回执拒绝、旧确认/新选择/未保存稿保护；原工作区恢复UI10回归及最终构建通过，未全量。

首次CPU硬限与壁钟同为3秒，硬终止抢先，已改壁钟3/CPU4并真实核对结构化timeout；旧失败保留。后续属性白名单拒绝反射/格式化/帧访问与模式匹配，流式请求先检查140KB上界再继续读；无不受限宿主回退。既有大包构建提示保留。

0.343.0-acc2b737f71b060f9344固定快照283文件匹配源码，原start/stop、所属PID和新运行身份核验，health及前端200。原16及180允许连接诊断状态、全部密文/主Key/资产和124/180消费包保持；本项Dify/模型HTTP0，不重放180。work/code-sample344保留定向测试、真实容器、截图、部署和保护回执，不提交生产数据或供应商原文。

定向命令：

```
.venv\Scripts\python.exe -m pytest backend\tests\test_code_samples.py backend\tests\test_code_sample_transport.py backend\tests\test_code_entry_contract.py -q -p no:cacheprovider
.venv\Scripts\python.exe work\code-sample344\integration_check.py
.venv\Scripts\python.exe work\code-sample344\ui_check.py
npm --prefix frontend run build
```

真实本机容器验证仅公开合成计算。此处没有取得新的Dify Sandbox/业务成绩，旧次数/费用边界不因本项功能而扩大。
