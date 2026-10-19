# 定时运行来源证据（0.116）

用户明确App UUID、当前定时artifact与修订后主动采集一次：只读当前发布图、最近20条App日志，最多3条triggered_from=schedule的运行详情，最多5个GET／60秒，不重试或发起运行。进入界面只读本机历史。手动app-run、缺运行、Webhook／插件等不当定时来源。空列表不能排除排队、未完成或更早事件，截断和后续页显式标记。

源规则来自Dify1.17.1：异步调度执行器使用InvokeFrom.SERVICE_API，同时triggered_from=SCHEDULE，完成后写WorkflowAppLog。InvokeFrom.TRIGGER的路径会跳过AppLog，但不能混同这条异步执行路径。普通workflow-runs列表query只支持debugging/app-run，不用于获取schedule；workflow-app-logs没有该来源过滤。

log.run.id与详情id关联，log/detail/published版本文字及三个核心图指纹和平台status一致，才标匹配当前核心图的调度平台成功。详情没有triggered_from或workflow_id，不能伪造相同发布ID证明。失败／运行中／停止／部分成功、未知及源不一致不当验收通过；平台成功仍不证明业务输出正确。

只保存UUID、来源、状态、一致性布尔、指纹和采集时间；不保存原图、输入输出、错误原文、身份或邮箱。本次凭据冻结且请求前后核对artifact／环境／修订／凭据；变化或失败不保存半条报告，也不调用模型。历史与Task、预算／正式run分离，最多展示最近10条并标历史。

14新增／80相关通过11.30秒；6受控页面／视觉通过、四次读取仅fixture，实际写0／Task不变。构建主497.97KB／证据4.15KB／观察4.70KB。完整2329通过144.54秒，已部署0.116；详见development-status.md。尚未真实读取新的定时运行，更没有触发资源操作；T115启用／发布与自然事件验收仍缺，原import/run拦截保持，真实资源方案仍需独立批准。
