# 定时入口草稿（0.113）

Workflow唯一入口可为start或trigger-schedule，不能共存。首批visual配置支持小时／日／周／月及UTC／Asia/Shanghai；用户须明确时间／日期／时区，Sierra不采用电脑时区或原生默认值，不计算下一次触发时间。其他时区／任意Cron／多触发／Webhook／插件触发尚未适配，不能省略后声称完成。Chatflow／Agent类型不会改变，容器触发拒绝。

格式与原生1.17.1一致：hourly on_minute真正整数0—59；其他频次time为1—12时HH:MM AM/PM；weekly需不重复sun…sat数组；monthly需不重复1—31整数／last。布尔、文字数值、旧额外字段和未支持模式不转或丢弃，切配置只改用户编辑的字段。短月、月末、重复／错过及并发语义需实际验收。

编译以真正入口计算路径／支配关系，不虚构start或timer.query；业务输入输出必须另有明确来源。生成、保留原ID/布局/说明/配置及静态检查，不等于调度已运行。未知版本、重试／执行设置与非空Cron字段拒绝，不能删行为后通过。

Sierra真实导入和普通run入口暂时阻止定时成果，包括确认保留后的最终artifact，不只看IR。当前支持生成／校验／下载，以及已有发布图只读观察、平台来源证据和人工接受的单触发器启停方案；定时发布闭环仍未完成，DSL说明及报告保留限制。目标Dify发布信号会同步创建/更新/删除WorkflowSchedulePlan及AppTrigger持久记录，真实启停操作需用户接受具体资源方案；定时发布与自然事件业务验收仍需实现和验证，不复用旧技术应用授权，不覆盖旧应用。普通手动Workflow调用不证明定时成功。

规则与时间／日期／频次／时区进入最终验收语义；轻量scope15，旧14需新确认，未发新的实际模型数据。目标规则依据本机tag1.17.1原生entities、trigger_schedule_node、schedule_service.visual_to_cron及发布信号handler；尚未执行真实触发。34新增／142相关、完整2278通过139.03秒，8页面／视觉／构建及4目标纯schema通过，真实写0／任务不变，已部署0.113；详见development-status.md。T115仍未完整交付。
