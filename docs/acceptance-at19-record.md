# AT-19 修改配置或需求：本地核对记录

日期：2026-10-21。对应 `docs/BACKLOG.md` 第 25 项及 `docs/requirements-v1.0.md` 的 AT-19：相关确认与测试失效，重新确认和试跑。

结论：指定单文件验收通过，新增 10 个隔离用例；本次没有修改产品实现。本记录的 `final_acceptance_record` 表示本次本地核对已记录，不代表 AT-19 真实 Dify 或最终业务验收通过。

## 已有实现与核对范围

- `backend/app/main.py` 的 `patch_task` 先校验并在副本上计算变更；有效变化才调用 `invalidate`，先保存版本快照，再递增修订。非法混合修改不部分写入；需求文本去除首尾空白后相同、配置值相同均不触发失效。
- 配置变更保留未改变的需求确认，并附带新修订及 `carried_from_revision`；配置确认撤销。需求变更或需求与配置同时变更撤销两类确认，保留已有流程计划并标为过期。以上变更均清空当前成果与 App 绑定，保留版本、确认与运行历史。
- `backend/app/acceptance.py` 按当前修订及环境筛选样例运行；历史自动通过和人工意见不会计入新修订。`review_run` 拒绝给旧修订运行添加当前意见。报告按当前修订筛选导入证据，下载接口不返回旧成果冒充当前成果。
- 旧修订的确认、构建、导入请求拒绝；运行入口在 App 绑定已清空时优先返回 422「当前版本尚未真实导入。」，重新模拟导入恢复绑定后旧修订试跑返回 409。拒绝不派发适配器、不追加运行记录。
- 需求变化后先重新确认需求，再显式检查并保存计划、确认配置；配置单独变化只需重新确认配置。重新确认、静态构建和模拟导入均不使当前样例通过，须当前修订重新试跑；人工样例还须独立的新人工意见。

## 新增隔离检查

`backend/tests/test_api.py` 新增 10 例：

1. 6 例：配置、需求、同时变化 × 自动／人工判定。通过本机公开 API 准备明确 Workflow 计划、必选样例、两类确认、静态构建、模拟导入和固定响应试跑。核对变更前通过、变更后未运行、旧请求拒绝、重新确认／复核／构建／导入仍未运行，直至新试跑与必要人工复核才恢复已声明样例通过。
2. 2 例：相同配置与首尾空白规范化后的相同需求保持修订、确认、成果和通过证据，不重复派发。
3. 2 例：需求修改与超范围 Temperature／未知配置项混合提交时整次拒绝，原任务、历史、文件和样例结果保持不变。

用例同时核对临时 Store 重开后的持久化状态、旧成果文件保留、版本和确认历史保留、旧运行原样保留、新运行绑定新修订和独立 ID，以及导入／试跑适配器调用顺序。文件级 autouse fixture 在已有同步／异步 HTTP transport 和默认模型阻断之外，增加 Dify 底层 `request` 阻断；仅显式替换的固定适配器返回合成结果。

## 验收命令与真实输出

```powershell
.venv\Scripts\python.exe -m pytest backend/tests/test_api.py -q
```

首次执行退出码 `0`。工具分段返回，以下为原始输出末段（不含此前进度点）：

```text
============================== warnings summary ===============================
.venv\Lib\site-packages\fastapi\testclient.py:1
  E:\workSpace\dify-agent\.venv\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
83 passed, 1 warning in 30.43s
```

警告来自现有 FastAPI／Starlette TestClient 依赖。本次只运行上述命令，没有运行全量测试、重建、Docker、部署、真实 Dify 交互、付费模型调用或推送，也未修改 `.venv`、`.gitignore` 或仓库设置。

## 修订绑定与尚未验收边界

产品代码基线：`cff1b4cd2c4652fd496fa79a0502d8ebc5723d50`。验收时测试文件 SHA256：`08cbcea22bb22429947c525bac1d0622ac04dd3f1a7a0f393ad2d6b8d8fe6901`。相关实现或测试变化后须重新验收。

本次使用临时数据库、明确代码节点 Workflow 计划、合成凭据／App ID 及固定导入／运行响应。沿用已有 `create` 准备函数对旧测试的需求准入与计划复核开关豁免，不是从新任务开始的完整产品交互。导入适配器仅为 `import_new` 的固定替代，并不创建或覆盖真实资源；返回相同合成 App ID 仅用于隔离本地绑定门禁。固定输出没有执行生成代码，更不证明改变后的业务规则正确；通过数只表示这些固定声明检查通过，产物仍为 `static_only`、汇总仍为 `declared_checks_only`。

当前确认／导入／报告接口不会自动把测试替代响应标为 mock；测试本身和本记录明确标记合成来源，不能把其中的「真实导入」字段或报告措辞当成平台证据。全部配置项及材料／消息等其他变更入口、Agent／Chatflow 的完整修改闭环、真实模型对新需求的理解、前端体验、并发变更与真实 Dify 重新发布／试跑／业务交付仍待专项验收。本次只处理队列第 25 项，不表示整个 136 项计划完成。
