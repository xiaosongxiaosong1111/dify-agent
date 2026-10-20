# Sierra AT-03 验收结论记录

日期：2026-10-20（Asia/Shanghai）。范围：BACKLOG 第 11 项「核对 AT-03『文档与参考 DSL 冲突』现状并补隔离检查」。基线：`docs/requirements-v1.0.md` 的 AT-03「指出冲突，确认最终依据」。

结论：**本项本地隔离检查通过；真实混合资料的语义冲突识别及最终业务验收仍未完成。** 本次只补测试和记录，未修改产品实现或部署。

## 现状核对

- `backend/app/main.py` 的材料上传接口解析本地文本文档；`backend/app/reference_dsl.py` 的预览／采纳接口将参考 DSL 结构摘要保存为已解析材料，保留原始 YAML，标记 `local_structure_only`，不执行或导入。
- `backend/app/conflicts.py` 接受本任务已解析材料、当前需求和已确认历史中的精确引文；校验来源、选项和完整替换字段。保存冲突清单使旧确认失效；已启用检查中的未决冲突阻止需求确认、构建和执行。冲突检查是显式启用的，来源合法不证明语义上确有冲突，也不保证自动发现全部冲突。
- `/conflicts/generate` 按契约请求有来源的候选清单，当前来源优先于历史，每源最多 6000 字、合计最多 24000 字，并标记摘录截断。模型候选只保存建议，不自动采纳推荐选项。真实识别质量、长材料覆盖和遗漏仍需验证。
- `/conflicts/decide` 要求当前修订、清单 token、具体选项及两项明确确认，记录原冲突、来源、所选方案、替换前后和修订。裁定后还需复核冲突处理结果并单独确认需求；材料变化使旧复核过期，保留历史决定。
- 原有用例主要引用需求字段，缺少通过实际本地文档上传和参考 DSL 采纳接口进入冲突处理的专门链路。

## 新增隔离检查

`backend/tests/test_conflicts.py` 新增 8 例，使用固定退款政策文档和未执行的 DSL 样例：

1. 2 例分别选择文档的 7 天规则和 DSL 的 30 天规则，覆盖采纳推荐项及主动选择非推荐项。清单读回保留双来源；裁定前需求不改写，确认／构建／导入／运行拒绝且任务不变。裁定精确写回规则、保留其他需求和原材料，旧修订和旧 token 拒绝；另行复核和需求确认后重新打开临时 Store，检查决定、确认、报告来源和原始文件仍在，无应用绑定、成果或运行。
2. 3 例分别引用其他任务的参考 DSL、未解析材料和伪造原文，均返回具体来源错误且任务不变。
3. 2 例在裁定并确认后新增文档或更改参考 DSL 的保留方式，确认修订增加、旧确认失效、历史决定保留；旧裁定／复核及重新确认／构建拒绝，拒绝操作不改写任务。
4. 1 例固定模型替身检查生成提示包含文档及参考 DSL 两个材料 ID 和原文；仅调用替身一次，候选保存为模型建议，需求、材料和应用类型不变，不自动裁定或确认。

文件级自动 fixture 阻断真实同步／异步 HTTP 传输和默认 `main.call_model`；需要模型响应的用例显式安装固定替身。沿用临时 Store 和进程内 TestClient，不接触真实任务、Dify 或付费模型。模拟用量不是供应商账单。旧测试的通用 fixture 关闭新任务准入／流程复核门禁，本项验证冲突处理接口链路，不据此宣称新任务全部门禁已端到端验收。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_conflicts.py -q
```

首次执行通过，退出码 `0`。同一次执行的分段输出合并如下：

```text
.......................................                                  [100%]
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
39 passed, 1 warning in 13.24s
```

唯一警告来自现有 FastAPI／Starlette TestClient 依赖，未修改依赖。

## 修订与未关闭边界

产品代码基线：`b1e9a16942fda19cf6f88fb60f1c6e2811ab9c7d`。验收时 `backend/tests/test_conflicts.py` SHA256：`2e7a8f8240aaec984e36f6232c14c391c3f090d5275faebb8120077eaca92c24`。相关实现或测试变化后须重新验收。本文登记为 acceptance-mapping 的 `final_acceptance_record`，仅记录此次本地结论。

固定文档与 DSL 注释证明来源和裁定机制，不证明模型能理解任意节点执行语义、识别所有跨材料冲突、判断事实正确或完整读取截断材料。未做前端体验、真实模型、Dify 导入／试跑和最终客户业务验收，不代表 AT-03 真实业务通过或 136 项计划完成。未运行全量测试、重建、Docker、真实资源操作、修改 `.venv`／`.gitignore`／仓库设置、删除目录或推送。队列仅更新第 11 项。
