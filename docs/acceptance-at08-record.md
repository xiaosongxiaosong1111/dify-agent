# Sierra AT-08 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 16 项「核对 AT-08『资料业务事实矛盾』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 AT-08「保留来源、请用户裁定，不静默选一份」。

结论：**本项本地隔离检查通过；真实业务事实矛盾的识别质量和最终业务验收仍未完成。** 本次只补测试和记录，未修改产品实现、部署或执行其他队列项。

## 现状核对

- `backend/app/conflicts.py` 的 `sources`、`validate_review` 接受本任务当前需求、已解析材料和已确认历史的精确原文。不同材料或同一材料中的不同引文均可组成待裁定分歧；重复同一引文、跨任务 ID、不可读材料和不匹配引文会被拒绝。程序校验来源真实性，不能判断业务事实真伪或语义矛盾。
- `/conflicts/generate` 按 `docs/conflict-contract.md` 生成带来源、问题、推荐理由及体验／费用／人工影响的候选，只保存建议；材料日期、上传顺序和模型推荐均不会直接写回业务规则。契约要求不得自行判真，但真实模型是否遵循、是否遗漏矛盾仍需验证。
- 保存有效清单后显式启用冲突门禁，撤销旧需求／配置确认；未决冲突阻止需求／配置确认、构建、导入和运行。未启用的任务不会自动每轮扫描资料，不能宣称所有矛盾都被发现。
- `/conflicts/decide` 要求当前 revision、清单 token、具体选项及复核／接受替换两项明确确认。决定历史保留原冲突、全部来源、选项、替换前后及源／结果修订；不改写原材料。最后一项裁定后仍需复核处理结果和重新确认需求，旧 token 不可复用。
- 原有检查已覆盖修订变化、资料变化使确认过期、恢复不复活旧确认、多个未决项不得静默丢弃。本次缺口是通过本地上传的纯业务资料之间、单份资料内部矛盾的专门隔离回归。

## 新增隔离检查

`backend/tests/test_conflicts.py` 新增 9 例，业务原文是固定退款政策，均经实际本地材料上传／参考方式接口进入冲突链路：

1. 4 例组合两种上传顺序和用户选择 7／30 天。旧、新日期的两份材料保留精确来源；候选保存后不静默改需求或裁定，未决时所有确认／执行拒绝且任务不变。用户显式选择后只替换目标规则、保留其他需求和两份材料，记录完整裁定及修订，旧 token 拒绝。另行复核和确认需求后重新打开临时 Store，检查决定、确认、报告来源和两份原始文件持久保留。
2. 1 例检查同一材料内两条不同期限原文可保留为两个来源，仍需用户裁定；重复同一引文伪装冲突返回明确错误且任务不变。
3. 3 例拒绝其他任务材料、将另一材料原文放入当前材料 ID、未解析材料；验证具体来源错误和拒绝前后任务完全一致。
4. 1 例固定模型替身检查提示含两份材料 ID、完整原文和未截断标记；推荐新资料的 30 天仍只生成候选，需求和材料不变、确认为空。用户可明确选择非推荐的 7 天，决定历史准确记录，仍需复核，不产生 Dify 应用、成果或运行。

沿用文件级自动 fixture，阻断真实同步／异步 HTTP 和默认 `main.call_model`；需要生成候选时显式安装固定模型替身。TestClient 仅访问进程内接口，Store／材料／模拟凭据仅存临时目录。模拟用量不代表实际账单。旧通用 fixture 关闭新任务准入／流程复核门禁，本项不据此宣称新任务全部门禁或前端交互已端到端验收。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_conflicts.py -q
```

首次执行通过，退出码 `0`。同一次执行的分段输出合并如下：

```text
................................................                         [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
48 passed, 1 warning in 18.24s
```

唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖。

## 修订与未关闭边界

产品代码基线：`8b910782adce36def1b2070a1eecd972580c1d13`。验收时 `backend/tests/test_conflicts.py` SHA256：`a3b9c35bcf0ddc7e52ba3db24d7f68adf6bbe2c640d3c0a9c48e941e23d390fa`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，记录此次本地验收结论，不代表真实业务最终通过。

真实资料的适用范围、事实正确性、模型识别／遗漏和完整替换语义仍需人工裁定及真实场景验收；合法引文不证明事实正确。模型来源每段最多 6000 字、总计最多 24000 字，长材料存在截断风险。未做真实模型、真实 Dify 导入／试跑、前端体验或客户最终验收；没有全量测试、重建、Docker、真实资源操作、修改 `.venv`／`.gitignore`／仓库设置、删除目录或推送，不代表 136 项计划完成。
