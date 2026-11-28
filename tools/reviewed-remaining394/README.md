# reviewed-remaining394

复用已成功首例的独立剩余平台收尾批（仅本机实现、隔离验证、冻结）。本目录不是执行入口：
导入 `tool.py` 无副作用，默认 CLI 只打印帮助；本阶段不真实 prepare/approve/run，不读取真实
Dify Key、不登录、不发布、不派发 Service，也不调用 Sierra 模型。

## 文件

- `tool.py`：固定 Task/环境/旧 App/首例锚点、prepare/approve/run 生命周期、926 文件保护、
  审批与 scope 校验、安全失败报告。
- `boundary.py`：物理边界，只允许固定 Dify origin 与精确操作，记录阶段与实际派发。
- `journey.py`：正常产品 API 全链（重连 1 次、复用首例、原版 6 例 7 轮、修改唯一句、
  新版 6 例 7 轮、双 ZIP）。
- `storage_guard.py`：既有 Task 写保护，锁定预算、策略、其它旧 run 与首例唯一一次诊断追加。
- `checks.py`：公开合成 SQLite + 假 Dify 的定向检查，不接触真实平台。
- `reviewed_diagnostic_redaction.py`：从 393（bfc0c3b）逐字 LF 复制的内存诊断脱敏 helper。
- `README.md`：本说明。

## 固定检查

```text
E:/workSpace/dify-agent/.venv/Scripts/python.exe tools/reviewed-remaining394/checks.py
```

只跑这一条公开定向检查，不跑全量测试。公开合成从“已发布原 App、已有 Key、首例 pass
但未诊断、原策略已启动 1、所选 provider 加密假 Key、旧 3 条 run”的形状开始，走正常产品
API：0 新 Task/模型、1 新 App/发布/Key、13 新 Service/11 启动、原/改各 6 例、14 条原生
轨迹、双 ZIP、14 次假 provider Key 读取；首例除一次 diagnostics 追加外其余字段逐值不变。

## 边界

- 真实 Dify 平台或业务验收未执行；本机隔离通过不等于业务或平台验收通过。
- prepare/approve/run 只接受固定的原项目与固定锚点，不运行旧 391，也不给旧批准换文字/哈希复用。
- 诊断密钥读取仅在内存、仅所选 assistant provider、每次 run 前核对 scope 与密文指纹。
- 公开合成可替换的只是检查内锚点；真实 prepare/live 锚点不能被 review 或 CLI 覆盖。
