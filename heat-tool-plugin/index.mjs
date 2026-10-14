// heat-tool-plugin/index.mjs
// AGH backend plugin: 1D heat-conduction solve / analytical / error-metric tools.
// 每个 tool.execute() 用子进程调 heat_tools_cli.py（它复用 02_工具层实现 的 Python）。
// 无第三方依赖: ctx.extension() 提供 tool 注册 API, child_process 是 Node 内置。
//
// solve_id 句柄机制(防刷屏/防超大 ToolResult):
//   - solve_1d_heat 在进程内 Map 里存完整时空场 u/exact, 只回传小句柄(solve-N) + 标量;
//   - heat_error_metrics 传 solve_id 取数, 模型侧永远不搬运 2D 大数组。
//   - 句柄仅在同一 AGH daemon 进程/会话内有效; 跨会话请改用同参数重跑。

import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const thisDir = dirname(fileURLToPath(import.meta.url))
const CLIPY = join(thisDir, 'heat_tools_cli.py')
const PYBIN = process.env.PY_BIN || 'python'

const Kind = Symbol.for('TypeBox.Kind')

// solve 入参 schema
const solveParams = {
  [Kind]: 'Object',
  type: 'object',
  properties: {
    L: { [Kind]: 'Number', type: 'number', description: '空间域长度 L > 0' },
    T: { [Kind]: 'Number', type: 'number', description: '时间域长度 T > 0' },
    alpha: { [Kind]: 'Number', type: 'number', description: '热扩散系数 alpha > 0' },
    A: { [Kind]: 'Number', type: 'number', description: '初始温度幅值 A > 0' },
    nx: { [Kind]: 'Number', type: 'number', description: '空间网格数 >=2(可选,缺省 20)' },
    nt: { [Kind]: 'Number', type: 'number', description: '时间步数 >=2(可选,缺省 200)' },
    method: { [Kind]: 'String', type: 'string', description: 'FTCS 或 CrankNicolson(可选,缺省 FTCS)' },
  },
  additionalProperties: false,
}

// error_metrics: 优先用 solve_id 取数(推荐,零大数组); 也可同参数重算(兜底,仍不回传大数组)。
const errorParams = {
  [Kind]: 'Object',
  type: 'object',
  properties: {
    solve_id: { [Kind]: 'String', type: 'string', description: 'solve_1d_heat 返回的句柄(推荐传入)' },
    handle: { [Kind]: 'String', type: 'string', description: 'solve_1d_heat 返回的 handle(磁盘句柄,推荐传入);不传则用同参数重算' },
    L: { [Kind]: 'Number', type: 'number' },
    T: { [Kind]: 'Number', type: 'number' },
    alpha: { [Kind]: 'Number', type: 'number' },
    A: { [Kind]: 'Number', type: 'number' },
    nx: { [Kind]: 'Number', type: 'number' },
    nt: { [Kind]: 'Number', type: 'number' },
    method: { [Kind]: 'String', type: 'string' },
    thresholds: {
      [Kind]: 'Object',
      type: 'object',
      description: '可选,收紧阈值 {max_abs_err, l2_err, boundary_tol},缺省 1e-3',
      additionalProperties: false,
    },
  },
  additionalProperties: false,
}

const analyticalParams = solveParams

const meta = {
  isReadOnly: true,
  isDestructive: false,
  isConcurrencySafe: true,
  isOpenWorld: false,
  replay: 'safe',
  costHint: undefined,
  deferLoading: false,
  requiresApproval: 'never',
}

// 进程内句柄表: solve_id -> { params, u, exact, r, status, x_grid, t_grid }
// 大数组不再放 Node 进程内, 而是 CLI 写磁盘 handle 文件; 这里只透传 handle 路径。

// 用一个子进程调 Python CLI。参数走 stdin(JSON),避免 Windows 命令行长度限制(ENAMETOOLONG)。
function runCli(command, argsJson) {
  return new Promise((resolve) => {
    const payload = JSON.stringify({ command, args: JSON.parse(argsJson) })
    const child = spawn(PYBIN, [CLIPY], {
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout: 180_000,
    })
    let out = ''
    let err = ''
    child.stdout.on('data', (d) => (out += d))
    child.stderr.on('data', (d) => (err += d))
    child.on('error', (e) => resolve({ ok: false, error: `启动 Python 失败: ${e.message}(确认装有 python 且 PY_BIN 正确)` }))
    child.stdin.on('error', () => {})
    child.stdin.write(payload)
    child.stdin.end()
    child.on('close', (code) => {
      if (code !== 0) {
        resolve({ ok: false, error: `Python 子进程退出码 ${code}\n${err}`.trim() })
        return
      }
      try {
        resolve({ ok: true, json: JSON.parse(out) })
      } catch {
        resolve({ ok: false, error: `Python 输出非 JSON: ${out.slice(0, 200)}`.trim() })
      }
    })
  })
}

function toToolResult(result, note) {
  return {
    content: [{ type: 'text', text: JSON.stringify(result, null, 2) }],
    structured: result,
  }
}

export const heatToolPlugin = {
  inject: ['extension'],
  apply(ctx) {
    const agnes = ctx.extension()

    agnes.registerTool({
      name: 'solve_1d_heat',
      description:
        '数值求解 1D 热传导方程 du/dt=alpha*d²u/dx²(齐次 Dirichlet 边界、sin 初始条件)。' +
        '输入 L,T,alpha,A 与可选 nx,nt,method;返回 status(success/rejected/unstable)、r(稳定性参数)、' +
        'handle(磁盘句柄,后续 heat_error_metrics 用它取数)、u_final(最终时刻温度场,一维)、x_grid/t_grid。' +
        '完整时空场写磁盘 handle 文件,不回传大数组;FTCS r>0.5 返回 unstable 时 u_final 为 null,须加大 nt 或换 CrankNicolson。',
      parameters: solveParams,
      meta,
      async execute(input) {
        const args = {
          L: input.L ?? 1.0,
          T: input.T ?? 1.0,
          alpha: input.alpha ?? 0.1,
          A: input.A ?? 1.0,
          nx: input.nx ?? 20,
          nt: input.nt ?? 200,
          method: input.method ?? 'FTCS',
        }
        // 让 CLI 只算 u/exact 并存句柄,不回传完整时空场(防刷屏/防超大 ToolResult)
        // CLI 的 solve_slim: stdout 只回标量+一维, 大数组已写磁盘 handle 文件。
        const res = await runCli('solve_slim', JSON.stringify(args))
        if (!res.ok) return toToolResult({ status: 'failed', errors: [res.error] })
        return toToolResult(res.json)
      },
    })

    agnes.registerTool({
      name: 'heat_analytical',
      description:
        '计算 1D 热传导解析解 u_exact(x,t)=A*exp(-alpha*(pi/L)²*t)*sin(pi*x/L) 在最终时刻 t=T 的一维值,作为误差基准参考(不回传完整时空场)。',
      parameters: analyticalParams,
      meta,
      async execute(input) {
        const args = {
          L: input.L ?? 1.0,
          T: input.T ?? 1.0,
          alpha: input.alpha ?? 0.1,
          A: input.A ?? 1.0,
          nx: input.nx ?? 20,
          nt: input.nt ?? 200,
          method: input.method ?? 'FTCS',
        }
        const res = await runCli('analytical_slim', JSON.stringify(args))
        if (!res.ok) return toToolResult({ status: 'failed', errors: [res.error] })
        return toToolResult(res.json)
      },
    })

    agnes.registerTool({
      name: 'heat_error_metrics',
      description:
        '对 1D 热传导数值解做误差统计与四层验证(边界/趋势/误差量级),返回 max_abs_error、l2_error、relative_error、' +
        'boundary_dev、boundary_ok、trend_ok、diverged、overall_pass。推荐传 handle(solve_1d_heat 返回的磁盘句柄)取数; ' +
        '不传 handle 时用同参数 L,T,alpha,A,nx,nt,method 自行重算(兜底)。两种路径都不回传大数组。',
      parameters: errorParams,
      meta,
      async execute(input) {
        // 推荐: 传 solve_1d_heat 返回的 handle(磁盘句柄), CLI 读回 u/exact 算误差, stdout 只回标量。
        if (input.handle) {
          const res = await runCli('metrics_by_handle', JSON.stringify({ handle: input.handle, thresholds: input.thresholds || null }))
          if (!res.ok) return toToolResult({ status: 'failed', errors: [res.error] })
          return toToolResult(res.json)
        }
        // 兜底: 同参数重算(仍用 slim,不回传大数组)
        const args = {
          L: input.L ?? 1.0,
          T: input.T ?? 1.0,
          alpha: input.alpha ?? 0.1,
          A: input.A ?? 1.0,
          nx: input.nx ?? 20,
          nt: input.nt ?? 200,
          method: input.method ?? 'FTCS',
        }
        if (input.thresholds) args.thresholds = input.thresholds
        const res = await runCli('error_metrics_slim', JSON.stringify(args))
        if (!res.ok) return toToolResult({ status: 'failed', errors: [res.error] })
        return toToolResult(res.json)
      },
    })

    agnes.on('session_start', () => {
      agnes.ctx.log.info('heat tools (solve_1d_heat / heat_analytical / heat_error_metrics, handle on disk) available')
    })
  },
}
