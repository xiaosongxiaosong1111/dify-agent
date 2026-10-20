# Sierra AT-17 验收结论记录

日期：2026-10-21（Asia/Shanghai）。范围：BACKLOG 第 23 项「核对 AT-17『切换到客户环境』现状并补隔离检查」。需求基线：`docs/requirements-v1.0.md` AT-17「重新核对版本、认证和资源映射」。

结论：**本项本地隔离检查通过；真实客户环境认证、版本和资源映射未验收。** 本次仅补测试与记录，不修改产品实现、不处理其他队列项。

## 现状核对

- `main.patch_task` 切换目标环境后提升任务修订，保留未变化的需求确认，清除配置确认、当前成果与 Dify App 绑定；旧运行与历史版本保留。旧修订来源核对与配置确认返回 409，当前修订因未生成成果返回 404，未重新确认时不能续聊。
- `main.patch_environment` 修改地址或登记版本会使关联任务失效；地址改变还清除未重新提供的凭据。新建客户连接的能力为 `untested`、没有运行 Key。修改运行 Key／App ID 保留任务和导入绑定，但旧自定义参数会话来源不能继续使用。
- `conversation_source_read`／`conversation_inputs.custom_input_source` 核对当前修订、环境 ID、地址／版本摘要、App、成果及私有运行凭据密文摘要。缺失环境、未适配的登记版本及旧绑定均不能成为可信来源；核对不解密、不联网、不登记预算、不修改记录。
- `locally_matched` 仅代表本机来源一致。即使环境能力是 `untested`／`failed`，本机绑定仍可一致，`platform_checked`／`business_verified` 均保持 false；没有进行实际版本探测、认证或资源核验。
- 环境切换会保留原配置（包括知识库 ID），不会自动完成资源映射。本次合成旧知识库 ID 只用来验证配置保留和确认失效，不能证明该库存在、适用于客户环境或映射已完成。

## 新增隔离检查

`backend/tests/test_conversation_source_read.py` 新增 13 例：

1. 3 例通过公开本机 API 切换目标环境、修改地址、修改登记版本，核对修订与确认失效、成果／App 清空、需求／配置／历史保留、旧来源拒绝、未确认续聊拒绝和地址改变后的凭据清空。
2. 6 例直接修改临时 Store 的地址、版本、环境 ID、缺失环境、运行来源环境或私有证明环境，保持当前修订与成果，单独验证来源绑定防线；核对失败不解密、不登记预算、不派发、不泄露原会话内容或凭据、不改任务与证明。
3. 2 例通过公开本机 API 改运行 Key／App ID，验证任务与历史保留、来源核对明确失败、续聊在预算登记前拒绝。
4. 2 例区分本机匹配与真实认证／版本探测／资源映射，能力未测或失败不能被改写成平台／业务通过。

新增文件级 autouse fixture 阻断同步／异步真实 HTTP transport、默认模型调用及 Dify 请求。准备函数使用临时 Store／数据目录、加密的虚构凭据及固定聊天响应；App ID、会话 ID 和旧运行均为合成数据。沿用的准备函数关闭新任务准入／计划复核策略，因此本次不是从新建任务到真实平台的完整交互验收。直接改 Store 的用例刻意绕过 API 失效机制，只隔离验证来源检查，不能作为实际迁移流程证据。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_conversation_source_read.py -q
```

首轮：`3 failed, 24 passed, 1 warning in 9.71s`。新增三个环境变更用例误将当前修订无成果的返回码写成 422，实际接口返回 404「当前版本尚未生成文件，请确认方案后生成。」；修正为精确状态码及中文提示断言，产品实现未改。

修正后同一命令退出码 `0`，完整输出（工具分段返回，进度行合并）：

```text
...........................                                              [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
27 passed, 1 warning in 9.43s
```

警告来自现有 FastAPI／Starlette TestClient 依赖。没有修改 `.venv`、依赖、`.gitignore` 或仓库设置；没有运行全量测试、重建、Docker、真实 Dify 交互、付费模型调用或推送。

## 修订与未关闭边界

产品代码基线：`28575b146647a4243428742f3f442a1c4549eeee`。验收时测试文件 SHA256：`cbe38cbb6440f73821d87a81b82046a2f18ff1e64374f3c5907e7cf5f599cdf1`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，仅表示本次本地核对结论已有记录。

真实公司到客户环境的版本探测、认证／角色权限与授权过期、模型／知识库／插件等资源逐项映射和可用性、迁移后真实导入／续聊及业务验收仍待完成；本次仅核对 Chatflow 自定义开始参数会话来源和上述本机失效路径，不代表所有应用类型或通用跨环境迁移已验收。前端切换体验也未验证。不代表 AT-17 最终业务通过或整个 136 项计划完成。
