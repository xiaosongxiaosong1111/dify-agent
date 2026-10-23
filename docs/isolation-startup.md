# 隔离验证先检查运行依赖（2026-10-23）

第61项的辅助queue.py遮蔽Python标准库，uvicorn导入阶段失败，尚未调用模型。已将冲突辅助文件改名为update-backlog.py；原冻结server、manifest及失败receipt保持，不重放原批。

新增本机启动预检在任何一次性真实回执创建前执行：检查批目录同名queue.py/queue包以及queue的标准库来源，随后在独立临时数据目录完整导入httpx、uvicorn、fastapi、app.main，通过ASGI核对health、meta和空任务列表；真实HTTP、模型及Dify禁止。检查完清理临时数据。

正向完整启动通过，注入同名queue.py时在模块执行前拒绝；原13任务及全部对象/密文/主密钥/旧文件、原失败receipt摘要保持，0真实请求。见[结果](isolation-startup-result-20261023.json)，本机脚本work/isolation-startup-preflight-261.py。

后续新执行器必须把这道检查接在真实回执之前，不能只在早期预演后再添加影响导入的辅助文件。真实回执产生后若有未处理异常，也须独立安全记录终态；不能让preflight回执被误读为仍在运行。这是验证工具修复，不是全新自然需求已通过真实模型或产品新功能。
