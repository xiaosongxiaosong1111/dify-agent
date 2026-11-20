# 模型配置地址与工具测试身份一致性

任务347，交付清单09，FR03/17/43/44/45，AT05/09/16。DeepSeek调查并实施，Codex复现、给具体边界和独立验收。

## 地址校验

模型地址填错端口或IPv6方括号时，现在会在保存前以中文422拒绝，不保存表面可用的坏配置。已经存在的历史坏地址测试会得到受控失败，保留配置等待人工修改，不再因解析异常500。合法http(s)、本机/局域网、IPv4、括号IPv6、自定义端口/路径和原尾斜杠规范保持；这是地址语法核对，不代表实际网络可达或账号可用。共用同一函数的Dify环境地址也采用这项校验。

根独立正常API旧行为：端口abc保存201且文本测试500、65536保存201、缺IPv6括号保存500，最终证据物理transport0；65536未作网络测试。记录work/provider347-invalid-url-proof.json。DeepSeek仅调整providers.checked_url的解析异常与端口范围；没有改地址、模型、Key、协议、价格或预设，不引入真实探测。

## 同一次工具测试使用同一修订的配置和Key

工具测试先核对用户批准的来源和估算范围，再在同一个任务锁临界区读取该配置对应的Key。Key只留进程内存，不写入回执、日志或导出；网络等待在锁外，仍允许编辑期间的旧测试完成。旧结果按原来源保存，不给新配置升级能力，也不恢复旧配置或自动再次派发。缺Key或解密失败保留not_dispatched回执、零派发和清理状态。

DeepSeek发现原工具测试先释放配置锁、后读取Key；Codex用两个本机TestClient和线程加假Key复现了旧地址/旧model混新Key，未实际外送。再内存装载旧固定快照的该模块，两个并发反例真实失败；没有修改旧快照或工作区源码。DeepSeek仅将Key捕获移入同一临界区并沿用原失败/回执路径。

## 已验证与边界

Codex完整复核两处产品差异和两个新测试文件，实际执行：

- test_provider_url_validation.py、test_provider_edit_source.py、test_provider_delete_source.py、test_provider_probe_source.py、test_provider_presets.py：129通过。
- test_provider_tool_probe_identity.py、test_provider_tool_probe.py、test_provider_probe_source.py、test_provider_edit_source.py：70通过。两组有重合，不合并成独立用例数量。
- 共用URL入口的test_environment_edit_source.py：19通过。

覆盖正常API的配置/Key/价格/能力历史保持、合法路由和wire参数、编辑途中一致旧元组与新配置不被旧回执覆盖，以及重复请求ID、缺Key/解密失败清理。物理HTTP均为替身，真实产品模型/Dify0，无新浏览器检查或前端修改。聊天/JSON/工具/图片能力仍分开，未把单次工具请求形状当作真实工具执行或完整业务能力。

实现待提交和原机保护部署，347仍doing；开发网关成功不代表产品账号/当前真实售后双版已通过。
