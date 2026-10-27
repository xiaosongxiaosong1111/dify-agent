# 第192修复后新350：已重连和导入，发布前停止

直接人类批准call_2025a29d3fcf463dab94fc76b4a4130f question0明确改授189零派发范围，绑定86d8e6a方案及33870609/91cbcedd。新350只消费一次，旧348/180均未重放。完整安全计数和回执哈希见同名JSON。

## 已实际完成

- 保存的加密资料自动重连原空间成功：登录1、应用列表/空间身份读取通过，新管理令牌/CSRF按批准加密提交。
- 新本机任务db13bc92-3b25-4249-abfc-4c4b384a1d17，r6，名称“Sierra公开批量修复后收尾验收”；正常新Task准入/代理逐项复核/需求与配置确认/计划/样例/限制/静态构建均通过，未绕门禁或使用模型。
- 实际新建App并导入成功：1cb02319-d42f-46b5-a1dd-34be136f83d6。草稿核心图在发布准备/确认的只读核对中匹配冻结公开图。
- 准备返回ready，但发布前执行器保护拒绝；实际只有读取6、登录1、导入1，发布POST0、Key0、Service运行0、模型HTTP0。整批立即停止，没有阶段重试或追加查询。

本机publication 1e5eeaee-aa6b-4ce7-8e4d-e3961f528010已记录write_attempted=true/state=unknown，Task仍imported。执行器计数证明其拒绝发生在真实发布POST前；**不据此修改旧unknown、把它升级为成功或解除现有App的一次派发锁**。平台是否后来被外部操作改变也没有追加查询。

## 阻断原因和193离线修复

Dify固定标签1.17.1/8387590的api/controllers/console/app/workflow.py中PublishedWorkflowApi.get明确：未发布返回None（HTTP200/null）。产品workflow_publication.remote已接受该合同，因而准备成功；公开执行器Boundary却只在404时设置unpublished，最后admit发布时拒绝。这是我方执行器多加的错误限制，不是Dify发布接口返回失败、账号错误或需求本身不能构建。

193先用200/null复现“未发布标记仍false”，然后仅改源程序：只在尚未见过发布身份且发布次数0时接受严格JSON null或兼容404；非空图清除旧“未发布”状态并核图/ID；已有发布后再消失、空对象/数组/假值等仍拒绝。原生POST发布成功的result/created_at合同也按同一标签核对，没有据此放宽保护。

未读流替身默认改为原生200/null，保留404兼容模式。27项定向检查通过（原响应顺序/SDK Cookie、原生null与404的正常API全链、8类失败停止、已发布不覆盖/坏结构不当空）；没有新真实HTTP、产品源码变化或部署，不跑全量，不改任何已消费包。[检查结果](unpublished-null-guard-result-20261027.json)。

## 数据、资源和交付

原16个Task/旧账本与对象逐项保持，现共17Task。除获批且已核原空间的新console_token/csrf外，全部原密文不变，尤其原售后运行Key、加密邮箱密码；原文件/主Key保持，新增资产仅此Task目录。旧124/180/348完整冻结和消费回执及本350保持。停止基线为work/batch-platform350/post-stop-data-snapshot.json。

管理/登录预留461/31不退借，实际累计运行仍16/正式passed14；App现9、首次发布8、运行Key8，不能再统称“资源各8”或“各9”。保守资源各10/运行18保持；本批Task与App已经消耗，不能描述为零派发改授。Sierra模型实际20/保守24、tokens2287和旧unknown/估算保持，没有真实试跑或账单证据。

仅从本机已保存r6下载交付包并核同版DSL/报告/README摘要，未新增平台请求：work/batch-platform350/imported-unpublished-r6-delivery.zip，20002字节，SHA256 3c9d1bb9bf1a3d802ea47b1b8bb2f09320a84da4a166901bbbd506236b2b160f。manifest的platform_checked/business_verified保持false；此包是已有导入阶段的保存成果，不是发布/试跑完成证明。

## 后续边界

本批明确异常即停，已结束，不能因源修复再执行350或继续其中的发布/Key/运行。当前产品对已有write_attempted发布记录保留一次性锁；新App不能直接重新准备发布。下一步先针对**现有Task/App的可信未派发证据和独立恢复记录**做安全恢复评审；原unknown及其来源保留。尚无已验证的恢复实现或新冻结授权，不申请重放，也不以再造一批Task/App绕开它。

C2真实Sandbox仍未取得结果；C1新真实售后整链及C3原25项最终结论仍未闭合。原静态/技术证据继续有效，不把本次导入或27项隔离检查算成业务完成。
