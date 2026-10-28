# 保存流程后的继续引导

218已修复流程页对所有任务固定提示先调用模型的问题。现在已有保存图时提示直接核对节点；计划过期提示复核修改；未保存草稿优先保存；读取中、未核实和空白各有对应状态。用户仍可主动请求重新生成，按钮保留费用说明及原禁用门禁，不自动覆盖草稿或调用模型。

220于2026-10-29部署0.352.0-737bdc8e3d4d8e269d74，使用原stop/start脚本，先核旧351/PID4172/项目Python及快照归属，新PID13540身份确认。类型检查/正式前端构建、六实际页面状态（含草稿跨页原文保持）、实际8765当前r17保存图引导及视觉核对通过；源/快照287文件完全匹配，health与前端200。检查页面仅本机GET，写入/外部请求0。

以217成功后的18Task/全部账本密文资产/原生运行及消费包为基线，部署仅server.pid变化；当前Task仍r17/run_completed/4次已用，未加测试运行或模型/Dify请求。此部署只补已保存流程的正常继续指引，不升级原25质量、Chatflow订单链或全部项目验收。

[部署安全回执](flow-plan-guidance-deployment-20261029.json)。定向命令：

```powershell
cd E:\workSpace\dify-agent\frontend
.\node_modules\.bin\tsc.cmd -b
.\node_modules\.bin\vite.cmd build
cd ..
node tools\check_flow_plan_guidance.cjs "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright" frontend\dist work\NEW-GUIDANCE-CHECK
```

页面检查只读当前公开演示Task，并在浏览器替身中构造六种状态，不保存模拟状态；不是模型语义或平台新验收。已有模板/高级JSON编辑与配置确认、构建流程继续使用原入口。
