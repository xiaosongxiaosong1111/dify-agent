# Sierra AT-04 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 12 项「核对 AT-04『参考程度未明确』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 FR-07 和 AT-04「询问借鉴／保留／复现，并记录选择」。

结论：**本项本地隔离检查通过；三种参考程度的真实界面与业务修改链路仍待验收。** 本次只补测试和记录，未修改产品实现或部署。

## 现状核对

- `frontend/src/ReferenceDslPanel.tsx` 的参考方式初始为空，提供借鉴、保留指定部分、严格复现三种选项；须主动选择并确认摘要限制，保留模式还须填写具体内容，才能加入材料。此次只核对源代码，没有运行前端验收。
- `backend/app/reference_dsl.py` 的预览只保存结构摘要，标记 `local_structure_only`，不改变任务或执行原文。采纳要求当前任务修订、最新预览 ID／token、显式参考方式与限制确认；保留项为空时拒绝。采纳保存原始 YAML、方式和保留项，并记录预览原修订及采纳后修订，使旧需求／配置确认失效。
- `backend/app/main.py` 的普通材料上传不默认选择参考方式；`backend/app/intake.py` 返回材料缺口及借鉴／保留／复现追问，未选择阻止需求确认和自动规划。材料方式变更增加任务修订，使旧确认和成果失效。
- 保存保留／复现选择不等于实现保留／复现。自动规划和基础构建接口均明确拒绝这两种材料模式，不自动改为借鉴；实际 DSL 修改保留入口是另外的用途，本项不验证该链路。

## 新增隔离检查

`backend/tests/test_reference_dsl.py` 新增 11 例：

1. 4 例分别遗漏参考方式、传入 null、空串和非法值，确认 422 拒绝，任务、预览和材料文件不变，之后仍可主动选择借鉴。
2. 1 例核对保留项为空或仅空白时拒绝，预览不被消耗，不新增材料文件。
3. 3 例分别选择借鉴、保留、复现，重新打开临时 Store 后核对任务和预览中的选择、保留项、原始文件、摘要校验值和修订记录；报告明确未运行，应用类型和需求不变，无应用绑定、成果或运行。
4. 1 例通过普通上传入口加入参考 YAML，核对未选方式的材料缺口和追问，确认／规划／构建拒绝；非法改选不改变任务，主动改选借鉴后缺口消除并可单独确认需求。
5. 2 例在借鉴已确认并产生静态成果后，分别改为保留和复现，核对旧修订确认拒绝、当前确认及成果失效；即使重新确认，自动规划／构建仍给出明确能力限制，任务和选择不被自动改写。

新增文件级自动 fixture 阻断真实同步／异步 HTTP 传输和默认 `main.call_model`；现有模型上下文用例显式安装固定响应替身。沿用临时 Store 和进程内 TestClient，不接触真实任务、Dify 或付费模型。通用 `approved` fixture 关闭新任务准入／流程复核门禁；本项验证参考程度接口行为，不据此宣称新任务全部门禁已端到端验收。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_reference_dsl.py -q
```

首次执行通过，退出码 `0`。同一次执行的分段输出合并如下：

```text
.........................................                                [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
41 passed, 1 warning in 11.79s
```

唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖。

## 修订与未关闭边界

产品代码基线：`1ea9722efcf6076952d052175c48c9db807b167c`。验收时 `backend/tests/test_reference_dsl.py` SHA256：`58db308989561dee654930a6509aef7e654edb33a8b3c46ef286f1e43841d077`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，仅记录此次本地结论。

结构摘要、方式持久化和能力限制拒绝不证明指定内容已保留、严格复现成功或业务语义正确。普通材料改选接口目前没有客户端修订字段，本次只核对其现有失效行为，不声称并发旧页面改选已获保护。三种参考程度的真实前端体验、模型讨论质量、真实 Dify 导入／试跑及最终客户业务验收仍未完成；不代表 AT-04 真实业务通过或 136 项计划完成。

未运行全量测试、重建、Docker、真实资源操作，未修改 `.venv`／`.gitignore`／仓库设置，未删除目录或推送。队列仅更新第 12 项。
