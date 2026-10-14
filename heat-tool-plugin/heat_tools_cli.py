# -*- coding: utf-8 -*-
"""
heat_tools_cli.py
AGH plugin 调用的统一 Python 入口。

每个 tool 的 execute() 通过子进程调用本脚本，用 JSON 传参、JSON 出参：
    python heat_tools_cli.py <command> <json_args>

命令分两类：
  旧命令(保留,向后兼容,会回传完整时空场 u/exact, 大网格时会超大):
    solve / analytical / error_metrics
  slim 命令(推荐, stdout 只含标量/一维; 大数组写磁盘句柄文件, 防刷屏/防超大 ToolResult):
    solve_slim          求解, stdout 只回 status/r/handle/u_final(一维)/网格
    analytical_slim     stdout 只回最终时刻解析解(一维)
    error_metrics_slim  同参数自行重算 u/exact, stdout 只回误差标量(大数组只在进程内算)
    metrics_by_handle   读磁盘句柄文件里的 u/exact 算误差标量, stdout 只回标量

说明：
    - 本脚本只算不改系统, 无副作用, 只读参数、只输出 JSON。
    - 它把 02 目录加进 sys.path, 直接复用 02 工具层 .py, 不重写求解逻辑。
"""

import json
import math
import os
import sys
import uuid

# 02_工具层实现 用绝对路径指向（不依赖 workspace / 运行终端）
# 若换了机器或目录，改这里；也支持用环境变量 HEAT_TOOLS_DIR 覆盖
TOOLS_DIR = os.environ.get(
    "HEAT_TOOLS_DIR",
    # 本仓库默认指向 <repo>/solver（便携：克隆后即可跑）
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "solver"),
)
if not os.path.isdir(TOOLS_DIR):
    # 回退：相对本脚本 ../02_工具层实现（当 plugin 与 02 平级时）
    TOOLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "02_工具层实现")
sys.path.insert(0, TOOLS_DIR)

import heat_solver
import analytical
import error_metrics

# 句柄目录：大数组(u/exact)落盘处, 与脚本同目录(可写), 不进 stdout
HANDLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "heat_handles")


def _finite_number_grid(u):
    """把可能含 NaN/Inf 的二维数值矩阵转成 JSON 可序列化（用 null 标记）。"""
    out = []
    for row in u:
        r = []
        for v in row:
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                r.append(None)
            else:
                r.append(v)
        out.append(r)
    return out


def _one_dim(grid_row):
    """取一维行并做 null 标记。"""
    out = []
    for v in grid_row:
        out.append(None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v)
    return out


# ---------------------------------------------------------------------------
# 旧命令（保留向后兼容；会回传完整时空场 u/exact，供老流程使用）
# ---------------------------------------------------------------------------

def cmd_solve(args):
    out = heat_solver.solve(args)
    result = {"status": out["status"], "errors": out["errors"], "r": out["r"]}
    if out["u"] is not None:
        nt = len(out["u"]) - 1
        result["u_final"] = _one_dim(out["u"][nt])
        result["x_grid"] = out["x_grid"]
        result["t_grid"] = out["t_grid"]
        if out["status"] == "success":
            result["u"] = _finite_number_grid(out["u"])
            result["exact"] = _finite_number_grid(analytical.compute_exact(args, out["x_grid"], out["t_grid"]))
        else:
            result["u"] = None
            result["exact"] = None
    return result


def cmd_error_metrics(args):
    out = heat_solver.solve(args)
    if out["u"] is None:
        return {"status": out["status"], "errors": out["errors"], "overall_pass": False}
    if out["status"] != "success":
        return {
            "status": out["status"],
            "errors": [f"r={out['r']} > 0.5，FTCS 不稳定，未做迭代；先加大 nt 或换 CrankNicolson"],
            "r": out["r"],
            "overall_pass": False,
        }
    u = out["u"]
    exact = analytical.compute_exact(args, out["x_grid"], out["t_grid"])
    result = error_metrics.validate(args, u, exact, args.get("thresholds"))
    result["status"] = "success"
    result["r"] = out["r"]
    return result


# ---------------------------------------------------------------------------
# slim 命令（stdout 只回标量/一维；大数组走磁盘句柄）
# ---------------------------------------------------------------------------

def cmd_solve_slim(args):
    """求解；完整 u/exact 写磁盘句柄文件, stdout 只回 status/r/handle/u_final(一维)/网格。"""
    out = heat_solver.solve(args)
    result = {"status": out["status"], "errors": out["errors"], "r": out["r"]}
    result["handle"] = None
    if out["u"] is not None:
        nt = len(out["u"]) - 1
        result["u_final"] = _one_dim(out["u"][nt])
        result["x_grid"] = out["x_grid"]
        result["t_grid"] = out["t_grid"]
        if out["status"] == "success":
            exact = analytical.compute_exact(args, out["x_grid"], out["t_grid"])
            os.makedirs(HANDLE_DIR, exist_ok=True)
            handle_path = os.path.join(HANDLE_DIR, f"{uuid.uuid4().hex}.json")
            params = {k: args.get(k) for k in ("L", "T", "alpha", "A", "nx", "nt", "method")}
            with open(handle_path, "w", encoding="utf-8") as fh:
                json.dump({"u": out["u"], "exact": exact, "r": out["r"], "params": params}, fh)
            # handle 只回传纯 ASCII 文件名(不含 CJK 路径), 避免子进程管道编码损坏;
            # metrics_by_handle 用 HANDLE_DIR + 文件名 还原绝对路径。
            result["handle"] = os.path.basename(handle_path)
            result["note"] = "完整 u/exact 已按 handle 落盘; heat_error_metrics 传 handle 取数, 不必回传大数组。"
        else:
            result["note"] = f"r={out['r']} 时 {args.get('method','FTCS')} 不稳定, 未生成 handle; 先加大 nt 或换 CrankNicolson。"
    return result


def cmd_analytical_slim(args):
    out = heat_solver.solve(args)
    if out["u"] is None:
        return {"status": out["status"], "errors": out["errors"]}
    exact = analytical.compute_exact(args, out["x_grid"], out["t_grid"])
    nt = len(out["t_grid"]) - 1
    return {
        "status": "success",
        "exact_final": _one_dim(exact[nt]),
        "x_grid": out["x_grid"],
        "r": out["r"],
    }


def cmd_error_metrics_slim(args):
    """同参数自行重算 u/exact(只在进程内), stdout 只回误差标量, 不回传大数组。"""
    out = heat_solver.solve(args)
    if out["u"] is None:
        return {"status": out["status"], "errors": out["errors"], "overall_pass": False}
    if out["status"] != "success":
        return {
            "status": out["status"],
            "errors": [f"r={out['r']}，{args.get('method','FTCS')} 不稳定，未做迭代；先加大 nt 或换 CrankNicolson"],
            "r": out["r"],
            "overall_pass": False,
        }
    u = out["u"]
    exact = analytical.compute_exact(args, out["x_grid"], out["t_grid"])
    result = error_metrics.validate(args, u, exact, args.get("thresholds"))
    result["status"] = "success"
    result["r"] = out["r"]
    return result


def cmd_metrics_by_handle(args):
    """args={handle, thresholds}：读磁盘句柄里的 u/exact 算误差标量, stdout 只回标量。"""
    handle = args.get("handle")
    # handle 可为纯文件名(ASCII), 也可为绝对路径; 统一在 HANDLE_DIR 下还原
    handle_path = handle
    if handle and os.path.basename(handle) == handle and not os.path.isabs(handle):
        handle_path = os.path.join(HANDLE_DIR, handle)
    if not handle or not os.path.isfile(handle_path):
        return {
            "status": "rejected",
            "errors": [f"handle 无效或文件不存在: {handle_path}(句柄仅限同一 AGH 会话/同机有效; 否则请改用同参数重跑 solve_1d_heat)"],
            "overall_pass": False,
        }
    with open(handle_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    u = data.get("u")
    exact = data.get("exact")
    params = data.get("params", {})
    if u is None or exact is None:
        return {"status": "rejected", "errors": ["handle 对应的数值解缺失"], "overall_pass": False}
    thresholds = args.get("thresholds") or params.get("thresholds")
    result = error_metrics.validate(params, u, exact, thresholds)
    result["status"] = "success"
    result["r"] = data.get("r")
    result["handle"] = handle
    return result


def main():
    # 参数来源：优先 stdin（避免 Windows 命令行长度限制），兼容 argv 传参。
    command = None
    args = None
    if len(sys.argv) >= 2 and sys.argv[1] in (
        "solve", "analytical", "error_metrics",
        "solve_slim", "analytical_slim", "error_metrics_slim", "metrics_by_handle",
    ):
        command = sys.argv[1]
        if len(sys.argv) >= 3 and sys.argv[2]:
            try:
                args = json.loads(sys.argv[2])
            except Exception:
                args = None
        else:
            data = sys.stdin.read().strip()
            if data:
                args = json.loads(data)
    else:
        data = sys.stdin.read().strip()
        if not data:
            print(json.dumps({"status": "rejected", "errors": ["usage: cmd via argv or {command,args} via stdin"]}))
            return
        payload = json.loads(data)
        command = payload.get("command")
        args = payload.get("args", {})

    if command == "solve":
        print(json.dumps(cmd_solve(args), ensure_ascii=False, default=str))
    elif command == "solve_slim":
        print(json.dumps(cmd_solve_slim(args), ensure_ascii=False, default=str))
    elif command == "analytical":
        out = heat_solver.solve(args)
        if out["u"] is not None:
            resp = {
                "exact": _finite_number_grid(analytical.compute_exact(args, out["x_grid"], out["t_grid"])),
                "status": "success",
            }
            if out["status"] != "success":
                resp["status"] = out["status"]
                resp["r"] = out["r"]
            print(json.dumps(resp, ensure_ascii=False, default=str))
        else:
            print(json.dumps({"status": out["status"], "errors": out["errors"]}, ensure_ascii=False))
    elif command == "analytical_slim":
        print(json.dumps(cmd_analytical_slim(args), ensure_ascii=False, default=str))
    elif command == "error_metrics":
        print(json.dumps(cmd_error_metrics(args), ensure_ascii=False, default=str))
    elif command == "error_metrics_slim":
        print(json.dumps(cmd_error_metrics_slim(args), ensure_ascii=False, default=str))
    elif command == "metrics_by_handle":
        print(json.dumps(cmd_metrics_by_handle(args), ensure_ascii=False, default=str))
    else:
        print(json.dumps({"status": "rejected", "errors": [f"未知 command {command}"]}))


if __name__ == "__main__":
    main()
