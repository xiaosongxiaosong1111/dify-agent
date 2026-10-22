# 当前App验收归属修复（0.257）

连续交付核对发现：相同任务修订/环境重新导入后，普通样例汇总未检查运行app_id，旧App成功或人工通过可被计入当前App；交付报告成功次数也混算。9个新增隔离用例先复现失败。

修复仅接受明确、非空且等于当前dify_app_id的运行App归属。旧App、缺失或空App记录不计入当前样例；缺少当前App也不从历史猜测。只在当前App内按最后一次记录判定，别的App后续失败不遮盖当前App的匹配证据。报告成功次数使用同一归属判断；旧记录与人工意见保留，不回填App身份、不重新评价或试跑。

## 验证

- `.venv\Scripts\python.exe -m pytest backend/tests/test_acceptance.py backend/tests/test_api.py -q -k "not test_api or report or run_checks_exact_saved_case or manual_review_history"`：24 passed。
- `.venv\Scripts\python.exe -m pytest backend/tests/test_task_next_step.py -q`：28 passed。仅临时存储，相关API检查阻断真实HTTP与模型；未跑全量。
- `node work\current-app-acceptance-257-ui.cjs "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright"`：5项只读页面核对，写入0、pageerror0；静态文件自供，未另起18760。
- 现有r21仍为当前App两个正式样例passed，报告明确成功返回2次；页面能展开保存命中输出与发布workflow_id。累计6/6不变，无新试跑或外部管理读取/模型调用。
- 部署0.257.0-5f628eaefb0caeb3a573；work/workspace257-deployed-check.json证明12任务/用户模型设置/全部密文与主密钥保持，源码与运行快照匹配，仅main.py及acceptance.py变化。前端无改动、未重建。

缺App归属的旧记录会显示当前App尚无匹配记录，不能直接沿用旧通过；只能参考原结果，后续真正运行须另有具体授权。该修复不是自然过期认证、自动语义保留或25场景最终业务证明。Claude网关前次任务超时，按既有约定本轮未为形式重复派发，不声称完成子审查。
