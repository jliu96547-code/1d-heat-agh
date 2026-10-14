# 运行与验证证据（AGH 实测，1D 热传导闭环）

> 本文件记录 AGH（Agnes Harness）内对 1D 热传导任务的一次完整运行证据。
> 任务规划 → 工具调用（solve_1d_heat / heat_error_metrics）→ 四层验证 → 异常处理，
> 全程为真实工具调用，非仅凭参数推算。数值均可复现。
>
> ⚠️ 证据来源声明（重要，对应赛事 4.2“运行证据”）：
> 本作品提交的“AGH 执行记录 + 工具调用记录”以 **AGH 右上角官方导出按钮**生成的原始记录为准
>（不是由 AI 自行导出的文本）。本文件中的数值为**参考锚点**，
> 用于与官方导出记录逐项核对；两者应一致。
> 官方导出产物（均存于本文件夹根目录，作为“运行证据”提交）：
>   ① `agh-diagnostics-11bcf5c3-*.zip`（AGH 右上角导出，含 conversation+trace+logs）
>   ② `运行证据_AGH官方导出_1d-heat.json`（AGH 官方 session 导出，同会话原始记录）
> 说明：开发阶段可用 Codex/辅助工具写代码、修 bug、整理文档（脚手架），但作品的
> 生成时间：2026-10-14 · 运行底座：Agnes Harness（AGH）· 模型：agnes-3.0-flash
> 工程机制：磁盘句柄（handle）——求解器把完整二维时空场 u/exact 写入本地句柄文件，
> 仅回传纯 ASCII 句柄名；误差工具用句柄名取回数据算误差。模型侧不搬运大数组，
> 规避 AGH 的 E_ENVELOPE 超大 ToolResult 报错。

---

## A. 基线闭环（FTCS 粗网格，nx=20, nt=200）

- 工具链：`solve_1d_heat(nx=20, nt=200, FTCS)` → `heat_error_metrics(handle=dfd72cc9.json)`
- 结果：
  - `status=success`，`r≈0.2`（满足 r≤0.5 稳定）
  - `max_abs_error = 1.511e-4`
  - `l2_error = 8.021e-5`
  - `relative_error = 1.511e-4`
  - `boundary_dev = 1.22e-16`，`boundary_ok=true`
  - `trend_ok=true`，`diverged=false`
  - `overall_pass = true`

## B. 方法对比（FTCS vs CrankNicolson，同网格 nx=20, nt=200）

| 方法 | r | max_abs_error | l2_error | overall_pass |
|---|---|---|---|---|
| FTCS | 0.2 | 1.511e-4 | 8.021e-5 | true |
| CrankNicolson | 0.2 | 7.558e-4 | 4.010e-4 | true |

- 结论：粗网格下 CN 误差反而更大，因空间离散误差主导；"稳定 ≠ 高精度"。
- CN 无条件稳定（Von Neumann 放大因子 |G|≤1，不依赖 r≤0.5）；
  FTCS 有 r≤0.5 的稳定性上限。

## C. 异常处理（FTCS 细网格 nx=200, nt=2000）

- `solve_1d_heat` → `r=2.0` → `status=unstable`
- 工具**拒绝输出伪收敛**：`handle=null`，`u_final` 全 0
- 诊断：Δx=0.005、Δt=0.0005 → r=α·Δt/Δx²=2.0，远超 0.5；需 Δt≤0.5·Δx²/α 才稳
- 下一动作：降步长（nt≥8000）或改 CrankNicolson（同 r=2.0 仍稳定）

## D. 细网格精度验证（CrankNicolson nx=200, nt=2000）

- `solve_1d_heat` → `status=success, r=2.0`（无条件稳定，照常迭代）
- `heat_error_metrics(handle=0eaae47a.json)` →
  - `max_abs_error = 7.556e-6`
  - `l2_error = 4.101e-5`
  - `boundary_ok=true, trend_ok=true, diverged=false, overall_pass=true`
- 误差量级：CN 细网格 `7.556e-6` 比 FTCS 粗网格 `1.511e-4` 小约 **20 倍**，
  O(Δt²)+O(Δx²) 二阶精度在细网格下显现。
- 稳定性对照：同 r=2.0 时 FTCS 发散(unstable)、CN 仍 success，实证 CN 无条件稳定。

### 汇总对比表

| 方法 | nx | nt | Δx | Δt | r | max_abs_error | l2_error | overall_pass | 状态 |
|---|---|---|---|---|---|---|---|---|---|
| FTCS（粗网格） | 20 | 200 | 0.05 | 0.005 | 0.2 | 1.511e-4 | 8.021e-5 | true | success |
| CN（细网格） | 200 | 2000 | 0.005 | 0.0005 | 2.0 | 7.556e-6 | 4.101e-5 | true | success |
| （对照）FTCS 细网格 | 200 | 2000 | 0.005 | 0.0005 | 2.0 | — | — | — | unstable（拒绝） |

---

## 日志归档（对应 log_field_template.json）

```json
[
  {
    "timestamp": "2026-10-14T20:30:00+08:00",
    "task_id": "task_1dheat_01",
    "stage": "solve",
    "status": "success",
    "input_params": { "L": 1.0, "T": 1.0, "alpha": 0.1, "A": 1.0, "nx": 20, "nt": 200, "method": "FTCS" },
    "failure_reason": null,
    "retried": false,
    "final_conclusion": "FTCS r=0.2 稳定；max_abs=1.511e-4，l2=8.021e-5，overall_pass=true"
  },
  {
    "timestamp": "2026-10-14T20:45:00+08:00",
    "task_id": "task_1dheat_02",
    "stage": "diagnose",
    "status": "unstable",
    "input_params": { "L": 1.0, "T": 1.0, "alpha": 0.1, "A": 1.0, "nx": 200, "nt": 2000, "method": "FTCS" },
    "failure_reason": "r=2.0 > 0.5，FTCS 显式格式发散，未做迭代",
    "retried": true,
    "final_conclusion": "拒绝伪收敛；下一动作：降步长 nt>=8000 或改 CrankNicolson"
  },
  {
    "timestamp": "2026-10-14T20:50:00+08:00",
    "task_id": "task_1dheat_03",
    "stage": "verify",
    "status": "success",
    "input_params": { "L": 1.0, "T": 1.0, "alpha": 0.1, "A": 1.0, "nx": 200, "nt": 2000, "method": "CrankNicolson" },
    "failure_reason": null,
    "retried": false,
    "final_conclusion": "CN r=2.0 无条件稳定；max_abs=7.556e-6，l2=4.101e-5，overall_pass=true"
  }
]
```

---

## 答辩摘要（一段，可直接引用）

> 本作品以 Agnes Harness（AGH）为运行底座，AGH 连接自研的 1D 热传导工具侧，
> 完成"任务规划→工具调用→结果验证→异常处理"完整闭环。给定 L=1、T=1、α=0.1、A=1，
> 用 FTCS 在 nx=20/nt=200（r=0.2）求解，四层验证给出 max_abs=1.511e-4、l2=8.021e-5、
> 边界偏差 1.22e-16，overall_pass=true。方法对比显示 Crank-Nicolson 无条件稳定
> （Von Neumann 放大因子 |G|≤1）；细网格 nx=200/nt=2000（r=2.0）下 CN 二阶精度
> 使误差降至 7.556e-6，比 FTCS 粗网格小约 20 倍；同参数 FTCS 则因 r=2.0>0.5 发散，
> 工具如实拒绝伪收敛并给出降步长/换方法的下一动作。工程上采用磁盘句柄机制，
> 求解器把 ~15MB 的完整时空场落盘、仅回传纯 ASCII 句柄名，误差工具据句柄取数验证，
> 使模型侧永不搬运大数组，规避 AGH 的超大 ToolResult 报错，兼顾可演示性与可复现性。

---

## 可复现命令（评委一条命令跑通）

---

## 官方导出操作指引（对应赛事 4.2“运行证据”，务必照做）

1. 在 AGH 工作台（http://127.0.0.1:4180）完成提示词 1/2/3 三段任务。
2. **点击右上角官方导出按钮**（红框小图标），导出本次会话的
   “AGH 执行记录 + 工具调用记录”原始文件（这就是合规的运行证据）。
4. 导出文件与本 `06` 文件一同提交；`06` 里的数值供核对，以官方导出为准。
5. 若官方导出含 Agnes 调用记录、工具入参/出参、设备/工具链，
   正好对应 4.2 要求的“AGH 执行记录 + ≥1 个工具 + 设备调用链 + Agnes 调用 + 关键配置”。
3. **合规红线**：运行证据必须是 AGH 官方导出（上述 ①② 两个文件），
   不要让 AI 用文字自行“写一份运行记录”冒充 AGH 记录——那不算 AGH 原始记录，不合规。
   （开发辅助写代码/整理文档不属“运行证据”，不影响合规；但口径上运行证据只认官方导出。）

```
cd <repo>/agnes-harness
python examples/packages/heat-tool-plugin/heat_tools_cli.py solve_slim <args.json>
# args.json 形如 {"command":"solve_slim","args":{"L":1,"T":1,"alpha":0.1,"A":1,"nx":20,"nt":200,"method":"FTCS"}}
# 得到 handle 文件名后：
python examples/packages/heat-tool-plugin/heat_tools_cli.py metrics_by_handle <{"command":"metrics_by_handle","args":{"handle":"<文件名>.json"}}.json>
```
说明：HEAT_TOOLS_DIR 指向 02_工具层实现；HEAT_TOOLS_DIR 默认绝对路径已写入 CLI，
换机可用环境变量 HEAT_TOOLS_DIR 覆盖。
