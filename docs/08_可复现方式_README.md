# 可运行作品 / 可复现方式（README）

> 本作品：1D 热传导 AGH 自动求解与四层验证闭环
> 运行底座：Agnes Harness（AGH，官方指定）· 模型：Agnes（官方限定）
> 目标：评委拿到代码后，**一条命令即可复现**数值结果与 AGH 内工具调用证据。

---

## 一、目录结构（提交/开源版）

```
1d-heat-agh/
├─ README.md                    # 本文件
├─ 02_工具层实现/
│  ├─ heat_solver.py            # FTCS / Crank-Nicolson 求解器（自研）
│  ├─ analytical.py             # 解析解（自研）
│  └─ error_metrics.py          # 四层误差验证（自研）
├─ heat-tool-plugin/            # AGH backend plugin（自研）
│  ├─ index.mjs                 # 注册 3 个工具：solve_1d_heat / heat_analytical / heat_error_metrics
│  ├─ heat_tools_cli.py         # Python CLI 入口（子进程桥接 02）+ 磁盘句柄机制
│  ├─ package.json
│  └─ heat_handles/            # 运行期句柄文件（不提交）
├─ 01_任务输入样例.json          # 任务参数样例
├─ 03_接口契约/                 # io_schema.json（工具入参/出参契约）
├─ 05_AGH编排设计/              # 编排 + AGH 来源标注
└─ 06_运行与验证证据_AGH实测_1D热传导闭环.md   # 运行与验证证据
```

---

## 二、前置条件

- Windows 10/11 · Node.js 24.10+ · pnpm 10.34.5 · Python 3.13（`python` 在 PATH）
- AGH 底座：`agnes-harness` 仓库（官方，Apache-2.0），本地构建运行
- Agnes 模型 Key：主办方统一发放，填入 AGH 的 **Provider 配置**（本地注入，**不进代码/仓库**）

> 路径依赖：`heat_tools_cli.py` 默认 `TOOLS_DIR` 指向 `02_工具层实现`。
> 换机/换目录请用环境变量覆盖：
> `set HEAT_TOOLS_DIR=<abs path to 02_工具层实现>`（PowerShell：`$env:HEAT_TOOLS_DIR='...'`）

---

## 三、AGH 内复现（主路径，证明"AGH 是核心底座"）

1. 起 AGH（Windows）：
   ```
   cd <repo>/agnes-harness
   .\start-local-windows.ps1        # 装依赖 + 构建 + 起 Web(4180) + 后端
   ```
2. 配 Agnes Provider：浏览器 `http://127.0.0.1:4180` → 设置 → Provider 选 Agnes，
   填 Base URL 与主办方 Key，test connection，选模型，save。
3. 装并启用工具插件：设置 → 插件管理 → Install from source：
   `file:./examples/packages/heat-tool-plugin` → Inspect → Confirm → Trust → Enable。
   确认状态 `desired=enabled / actual=running / trusted=true`。
4. 在工作台任务区发起任务，发一段话（示例）：
   ```
   按 1d-heat 方法求解 1D 热传导，L=1,T=1,alpha=0.1,A=1,method=FTCS,nx=20,nt=200。
   先调 solve_1d_heat（r 必须 <=0.5），再调 heat_error_metrics(handle=句柄) 做四层验证，
   给出 max_abs_error / l2_error / overall_pass 结论与稳定性判断。
   ```
5. 看 **tool record**：`solve_1d_heat` 返回 `handle=xxx.json`（纯 ASCII 文件名），
   `heat_error_metrics` 据句柄返回四层误差。**这是"AGH 真实调用工具"的证据**，非模型口述数字。

> 拿掉 AGH 主流程无法完成（反向验证 AGH 是核心底座）：
> 本作品数值能力由 AGH plugin 承载，独立跑 02 的 .py 只能出数，不构成作品闭环。

---

## 四、一条命令最小复现（验证数值，无需 AGH）

在 `heat-tool-plugin/` 目录（需先设好 `HEAT_TOOLS_DIR`）：

```
# 1) 求解（FTCS 粗网格，写磁盘句柄，stdout 只回标量+一维）
echo {"command":"solve_slim","args":{"L":1,"T":1,"alpha":0.1,"A":1,"nx":20,"nt":200,"method":"FTCS"}} | python heat_tools_cli.py
# -> {"status":"success","r":0.2,"handle":"<纯文件名>.json","u_final":[...]}

# 2) 用句柄算四层误差（stdout 只回标量）
echo {"command":"metrics_by_handle","args":{"handle":"<上一步的handle>","thresholds":null}} | python heat_tools_cli.py
# -> {"max_abs_error":1.5e-04,"l2_error":8.0e-05,"boundary_ok":true,"trend_ok":true,"overall_pass":true}
```

**可复现硬性标准**：固定输入（01_任务输入样例.json）、固定脚本版本、固定运行命令；
重复运行应得到相同数值（误差到 1e-15 级数值一致），结果可重新生成。

### 期望数值锚点（用于核对复现结果）

| 场景 | 方法 | nx,nt | r | max_abs_error | l2_error | overall_pass |
|---|---|---|---|---|---|---|
| 基线 | FTCS | 20,200 | 0.2 | ≈1.511e-4 | ≈8.021e-5 | true |
| 对比 | CN | 20,200 | 0.2 | ≈7.558e-4 | ≈4.010e-4 | true |
| 异常 | FTCS | 200,2000 | 2.0 | —（unstable，拒绝） | — | false |
| 细网格 | CN | 200,2000 | 2.0 | ≈7.556e-6 | ≈4.101e-5 | true |

---

## 五、第三方组件 / 来源（详见 07 文件第三节）

- 自研：FTCS/CN 求解器、解析解、四层误差验证、heat-tool-plugin（含磁盘句柄机制）。
- 非自研：AGH 底座（官方，Apache-2.0）、Agnes 模型（官方限定，Key 本地配置）、
  Python 3.13 与标准库（math/json/subprocess/uuid）。
- **未使用**任何现成数值求解器库、第三方模型或外部数据。

---

## 六、开源承诺（获奖队 5 个工作日内）

- 开源范围：`02_工具层实现`、`heat-tool-plugin`、`docs`（01/03/05/06）。
- License：MIT。
- 不提交：AGH 的 Agnes Key（本地配置）、`heat_handles/` 运行期句柄文件。

---

## 七、测试样例（对应赛事 4.2「正常 / 边界 / 失败」三类）

**归为一组**：下列 3 条（正常 / 边界 / 失败）构成**同一测试样例组**，
统一输入 schema（01_任务输入样例.json）、统一经 AGH 插件调用、统一四层验证口径。

| 组内用例 | 类型 | 参数 | 期望结果 |
|---|---|---|---|
| T1 | 正常 | FTCS nx=20,nt=200（r=0.2） | success，overall_pass=true，max_abs≈1.511e-4 |
| T2 | 边界 | FTCS nx=200,nt=2000（r=2.0，>0.5） | unstable，拒绝伪收敛并给出下一动作 |
| T3 | 失败 | 非法参数（L<=0 或 nx<2） | rejected，errors 列出缺项/非法项 |

> 三类样例都可通过 `heat_tools_cli.py` 一条命令复现（见第四节最小复现命令）。
> 一键跑全组：把 T1/T2/T3 三条 `solve_slim`/`metrics_by_handle` 调用连跑即可
>（AGH 内分别发三段任务，或 CLI 里循环传入 3 组 args）；结果以上表"期望结果"为验收基准。
