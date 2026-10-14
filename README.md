# 1D 热传导 AGH 自动求解与四层验证闭环

> 2026 年江苏省 AI+科学与工程创新实践黑客松（高校组）参赛作品。
> 运行底座：Agnes Harness（AGH，官方指定）· 模型：Agnes（官方限定）。
> 队名：穿着拖鞋闯天地 · 成员：李兆益（会计，跑完全程）、尹宁（计算机，确认成果）。

本作品把「1D 热传导求解 + 解析解基准 + 四层误差验证 + 异常处理」做成一个
**可执行、可验证、可复现** 的 AI 科学工程闭环，全部跑在 AGH 上。

## 目录结构

```
1d-heat-agh/
├─ solver/                  # 自研工具层（被 AGH 插件经子进程调用）
│  ├─ heat_solver.py        #   FTCS / Crank-Nicolson 求解器（自研）
│  ├─ analytical.py         #   解析解（自研）
│  └─ error_metrics.py      #   四层误差验证（自研）
├─ heat-tool-plugin/        # AGH backend plugin（自研）
│  ├─ index.mjs             #   注册 3 个工具：solve_1d_heat / heat_analytical / heat_error_metrics
│  ├─ heat_tools_cli.py     #   Python CLI 入口 + 磁盘句柄(handle)机制
│  └─ package.json
├─ docs/                    # 文档与证据
│  ├─ 01_任务输入样例.json
│  ├─ 03_io_schema.json
│  ├─ 06_运行与验证证据_AGH实测.md
│  ├─ 07_成员分工与独立完成声明.md
│  └─ 08_可复现方式_README.md
├─ README.md
└─ LICENSE                  # MIT
```

## 一条命令最小复现（无需 AGH）

前置：Python 3.10+（`python` 在 PATH）。仓库内运行期产物 `heat_handles/` 由 `.gitignore` 排除。

```bash
cd heat-tool-plugin
# 1) 求解（FTCS 粗网格）：stdout 只回标量 + 一维，完整时空场写磁盘句柄
echo '{"command":"solve_slim","args":{"L":1,"T":1,"alpha":0.1,"A":1,"nx":20,"nt":200,"method":"FTCS"}}' | python heat_tools_cli.py
# -> {"status":"success","r":0.2,"handle":"<纯文件名>.json", ...}

# 2) 用句柄算四层误差：stdout 只回标量
echo '{"command":"metrics_by_handle","args":{"handle":"<上一步的handle>","thresholds":null}}' | python heat_tools_cli.py
# -> {"max_abs_error":1.5e-04,"l2_error":8.0e-05,"boundary_ok":true,"trend_ok":true,"overall_pass":true}
```

### 期望数值锚点（核对复现结果）

| 用例 | 类型 | 方法/网格 | r | 期望 |
|---|---|---|---|---|
| T1 | 正常 | FTCS nx=20,nt=200 | 0.2 | overall_pass=true，max_abs≈1.511e-4 |
| T2 | 边界 | FTCS nx=200,nt=2000 | 2.0 | unstable（拒绝伪收敛） |
| T3 | 失败 | 非法参数（L≤0 / nx<2） | — | rejected + errors |

## AGH 内复现（主路径，证明 AGH 是核心底座）

1. 克隆 AGH（官方 `github.com/AgnesAI-Labs/agnes-harness`），Windows 用 `start-local-windows.ps1` 起本地实例（Web 4180）。
2. Web → 设置 → Provider：选 Agnes，填主办方发放的 Key，test connection，选模型。
3. Web → 插件管理 → Install from source：`file:<本仓>/heat-tool-plugin` → Inspect → Confirm → Trust → Enable。
4. 工作台发起任务：`按 1d-heat 方法求解 1D 热传导 L=1,T=1,alpha=0.1,A=1,method=FTCS,nx=20,nt=200`，
   看 tool record 中 `solve_1d_heat` / `heat_error_metrics` 被真实调用、`overall_pass=true`。

## 第三方组件 / 来源（规则九）

- 自研：`solver/`（FTCS/CN 求解器、解析解、四层验证）、`heat-tool-plugin/`（含磁盘句柄机制）。
- 非自研：AGH 底座（官方，Apache-2.0）、Agnes 模型（官方限定，Key 本地配置，不入仓库）、Python 标准库。
- 未使用任何现成数值库、第三方模型或外部数据。

## License
MIT。AGH 底座本身 Apache-2.0，不受本仓 License 约束。
