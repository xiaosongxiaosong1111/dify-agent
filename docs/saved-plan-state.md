# 当前保存方案与历史规划记录（0.351，第215）

0.351已把“当前保存图”与“历史暂停规划”分开展示：本机只读精确比较当前流程和保留候选，区分一致/不同/未保存/过期/未核实；历史paused、旧费用和停止信息不改判，相同内容不等于采纳来源、确认或平台通过。23新增/25相关共48后端、8实际构建页面场景及生产当前r13真实接口/页面通过，前端构建和视觉复核过；原归属脚本部署351/287文件/PID4172，原18/六费用条目/密文资产及全部消费包保持，模型Dify0。

实际问题：214正常采用第二模型候选并构建r13后，顶部仍显示输入r12的旧规划“已暂停、尚未应用、原方案保持”，容易诱发重复生成。现在先显示当前已保存内容关系，旧状态明确标历史；停止原因/变化摘要仍可查看，原规划记录不改为成功。

新GET /api/tasks/{task_id}/planning/{run_id}/saved-state仅在本机读取已保存数据，绑定Task/规划记录/当前及输入修订，不解密、不出站、不改Task或费用；只返回比较标志，不返回计划原文。用Python有限JSON精确比较，键顺序忽略、数组及精确大整数/布尔类型保持，不能由浏览器精度舍入误判相等。此接口不检查图业务正确性，也不证明来源或实际采纳动作。

页面严格校验归属/版本/标志，过期响应、错误、异常契约均显示未核实，不自动重试；切换任务或修订取消旧读取。内容相同但plan_stale=true仍提示过期。8页面覆盖一致、不同、过期、未保存、HTTP失败、错修订、错任务、伪平台标志；实际新服务读取当前r13/历史r12返回same且历史仍paused。原18所有对象/密文资产和已消费包保护通过，仅server.pid更新。[安全结果](saved-plan-state-result-20261028.json)。

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/test_saved_plan_state.py backend/tests/test_retained_plan.py -q -p no:cacheprovider --basetemp work/pytest-saved-plan367-final
node tools/check_saved_plan_state.cjs "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright" work/saved-plan367/ui-info.json
```

初次新增API测试误用了没有正式plan的已有fixture，修正为明确相同的公开对象后48过，产品未放松校验；视觉复核把当前比较移到历史记录前并改为纵向，最终构建8场景重跑通过。817KB主包既有体积提示保留，不顺带拆包。当前修改版仍只静态交付，原版真实两例已过，C1及全25业务未因此关闭。
