# Sierra AT-18 验收结论记录

日期：2026-10-21（Asia/Shanghai）。范围：BACKLOG 第 24 项「核对 AT-18『用户在 Dify 手动修改后继续』现状并补隔离检查」。需求基线：`docs/requirements-v1.0.md` AT-18「获取／接收最新版本，保留改动再处理新增要求」。

结论：**本项本地隔离检查通过；当前修订的真实 Dify 手改往返及最终业务未验收。** 本次仅补测试与记录，不修改产品实现，不处理其他队列项。

## 现状核对

- `main.capture_dsl_reference` 从本任务及环境匹配的成功导入记录获取比较基线和源 App，可读取草稿或接收 YAML。上传标记为 `uploaded_file`，明确未在线核对归属／最新状态；在线读取失败不回退旧文件。读取前后检查修订与来源环境地址／版本，成功后保存完整引用并使确认、当前成果和 App 绑定失效，保留历史。
- `dsl_roundtrip.merge` 对 base／current／generated 做确定性三方比较，图节点／连接按稳定 ID 合并；手改与生成方案独立变化可共同保留。同处冲突需要显式选择，预览绑定修订、引用及内容摘要；未解决冲突或静态无效不能采用。
- `main.apply_dsl_merge` 保存确认后的最终文件并形成新修订；需求和配置必须重新确认。任务计划仍是生成建议，不是任意 DSL 的完整反解。构建标记 `static_only`，旧运行不能证明当前修订通过。
- 导入入口核对最终文件摘要；在线来源导入前重读草稿，发生变化或读取／解析失败就停止创建。导入使用 `import_new`，不覆盖源应用，成功时保存生成建议基线供下一轮比较。读取检查不能锁住 Dify 编辑，检查之后的新变化仍需再次读取。
- 原有 20 例已覆盖上传与原文保留、代码冲突选择、修改后重确认、无效 YAML／密钥拒绝、未适配结构保留但阻止采用、放弃保护留审计、源变化阻止导入、再次往返基线及文件篡改保护；Chatflow 和原生 Agent 另有受限静态检查。不能从这些局部检查推定全部复杂节点或跨环境往返已适配。

## 新增隔离检查

`backend/tests/test_dsl_roundtrip.py` 新增 12 例：

1. 1 例通过公开本机 API 获取固定草稿、保存新增需求与明确计划标题变更、预览和确认合并、重新打开临时 Store、重新确认与静态构建、模拟导入新应用。核对手改代码／布局和新增标题同时保留，预览与最终文件一致、预览只读、原文件与历史／完整引用保留，派发顺序仅为两次固定读取及一次模拟 `import_new`。
2. 3 例分别验证旧修订、替换引用、生成方案变化后的旧预览拒绝，保持任务及保留文件不变。
3. 3 例移除匹配导入记录，或改变其 App／环境，验证找不到匹配基线时在外部草稿读取前拒绝且不保存引用。
4. 3 例用固定权限错误、超时错误及无效 YAML 模拟导入前重读失败，验证不创建应用、失败运行绑定当前修订、保留当前文件和引用、不丢历史。
5. 2 例在固定导出回调期间通过本地 API 修改需求修订，或直接修改临时环境地址，验证 409 拒绝保存过期引用、不覆盖并发修改。

新增文件级 autouse fixture 阻断同步／异步真实 HTTP transport、Dify 底层请求及默认模型调用，覆盖原有与新增检查。使用 `test_api.client` 临时数据库和数据目录，App／运行及凭据均为合成记录；导出与导入只返回固定数据。沿用准备函数关闭新任务准入／计划复核策略，本次不是从新任务创建开始的完整产品交互验收。新增需求由测试明确保存，不能证明模型会自主正确理解任意新增需求；直接改临时环境的用例仅验证来源检查防线。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_dsl_roundtrip.py -q
```

首轮：`1 failed, 31 passed, 1 warning in 16.73s`。新增并发修订测试在事件循环线程内同步调用 TestClient，触发 `RuntimeError: This method cannot be called from the event loop thread`；改用 `asyncio.to_thread` 发起同一本地 API 请求，产品实现未改。

修正后同一命令退出码 `0`，完整输出（工具分段返回，进度行合并）：

```text
................................                                         [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
32 passed, 1 warning in 15.98s
```

警告来自现有 FastAPI／Starlette TestClient 依赖。没有修改 `.venv`、依赖、`.gitignore` 或仓库设置；没有运行全量测试、重建、Docker、真实 Dify 交互、付费模型调用或推送。

## 修订与未关闭边界

产品代码基线：`05fa1192623f8099673305bcd9652b05fc51ebcf`。验收时测试文件 SHA256：`2d512a6908662e7f6806fea9d84b5e3973fa2ca4c7c1ce0acea068fc023c504e`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，只表示本次本地核对结论已记录。

历史 `docs/dsl-roundtrip-contract.md` 曾记载固定代码技术应用的真实往返证据，本次未重放，不能据此认定当前修订或客户业务通过。实际上传文件的归属及最新性、真实 Dify 草稿读取／导入／发布／试跑、前端体验、模型处理新增语义需求、通用复杂节点反解与跨环境资源映射往返仍需专项验收。本文不代表 AT-18 最终业务通过，也不代表整个 136 项计划完成。
