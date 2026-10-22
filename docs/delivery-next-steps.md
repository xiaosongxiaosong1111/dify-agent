# 交付说明按保存进度给出待办（0.259）

当前真实r21已发布、配对Key已保存且两条正式样例通过，但下载报告的固定待办仍要求配置Key和执行样例。该问题由临时任务API用例先复现失败。

待办现在只根据当前修订/环境/App的保存证据给出：匹配导入不重复要求导入；匹配发布成功回执不重复发布；当前连接确有配对加密Key时不再要求创建或复制登记；必选样例通过则指向输出与未覆盖场景。未知/执行中发布或运行明确核对原记录、禁止直接重发。没有App归属、错误目标或旧修订不沿用；Chatflow/Agent保留其类型的发布核对路径。模拟依赖只有已声明时才列替换待办。

报告没有访问Dify实时状态，没有派发、改变策略或推断平台仍保持原状态；外部编辑/撤销、完整业务覆盖和供应商账单仍须核对。保存事实不构成新增模型/资源/运行批准。

## 验证

- `.venv\Scripts\python.exe -m pytest backend/tests/test_delivery_next_steps.py backend/tests/test_execution_report.py -q`：16 passed。
- `.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q -k report`：4 passed，90 deselected。合计20项定向检查，不跑全量；API用例临时存储、阻断真实HTTP/模型，报告无凭据且原任务不变。
- 部署0.259.0-efd0c39b6427b9b8ba06，work/workspace259-deployed-check.json证明12任务/模型配置/全部密文及主密钥保持、源码匹配快照，只变main.py与delivery_next_steps.py。无前端改动，不重建。
- 真实本机只读r21报告核对6项通过（work/delivery-next-steps-259-live.json）：已有发布不重发、已有Key不重建、正式样例2/2、完整业务待确认、无实时平台读取、旧固定Key指令移除。累计仍6/6，0新增外部请求。

不把本次修复称完整从新需求出发的连续界面、自然过期认证、自动语义保留或25场景最终业务通过。Claude前次超时按约定未形式重派。
