# -*- coding: utf-8 -*-
"""
02_工具层实现 / heat_solver.py
一维热传导方程数值求解工具（平台无关，可独立运行）。

控制方程：
    du/dt = alpha * d^2u/dx^2
边界条件：
    u(0,t)=0, u(L,t)=0
初始条件：
    u(x,0)= A*sin(pi*x/L)
解析解：
    u_exact(x,t)= A*exp(-alpha*(pi/L)^2*t)*sin(pi*x/L)

本模块提供两种数值方法：
    - FTCS 显式差分（最小闭环必须项）
    - Crank-Nicolson 隐式差分（技术深度增强，可选）

注意：本模块是"被 AGH 调用的工具侧资源"，不主导流程。
调用方式（示意）：
    out = solve(params)   # 返回 dict，含时间序列温度场、执行状态、稳定性信息
"""

import math


def _validate(params):
    """参数合法性检查。返回 (errors: list[str])"""
    errs = []
    L = params.get("L")
    T = params.get("T")
    alpha = params.get("alpha")
    A = params.get("A")
    nx = params.get("nx")
    nt = params.get("nt")

    for name, val in (("L", L), ("T", T), ("alpha", alpha), ("A", A)):
        if val is None:
            errs.append(f"缺少参数 {name}")
        elif val <= 0:
            errs.append(f"参数 {name}={val} 非法（须 >0；alpha 必须大于 0）")
    for name, val in (("nx", nx), ("nt", nt)):
        if val is None:
            errs.append(f"缺少参数 {name}")
        elif int(val) < 2:
            errs.append(f"参数 {name}={val} 非法（须 >=2 的整数）")
    return errs


def stability_ratio(params):
    """FTCS 稳定性参数 r = alpha*dt/dx^2。r<=0.5 稳定。"""
    L = params["L"]
    T = params["T"]
    alpha = params["alpha"]
    nx = int(params["nx"])
    nt = int(params["nt"])
    dx = L / nx
    dt = T / nt
    r = alpha * dt / (dx * dx)
    return r


def solve(params):
    """
    数值求解 1D 热传导方程。
    返回 dict：
        status: "success" / "rejected" / "unstable"
        errors: 参数错误列表（若有）
        r: 稳定性参数
        x_grid: 空间网格
        t_grid: 时间网格
        u: 二维数组 u[i][j] = u(x_i, t_j)
    """
    errors = _validate(params)
    if errors:
        return {"status": "rejected", "errors": errors, "r": None,
                "x_grid": None, "t_grid": None, "u": None}

    L = params["L"]
    T = params["T"]
    alpha = params["alpha"]
    A = params["A"]
    nx = int(params["nx"])
    nt = int(params["nt"])
    method = params.get("method", "FTCS")

    dx = L / nx
    dt = T / nt
    x_grid = [i * dx for i in range(nx + 1)]
    t_grid = [j * dt for j in range(nt + 1)]

    # 初始条件（内部节点 1..nx-1，边界为 0）
    def ic(x):
        return A * math.sin(math.pi * x / L)

    u = [[0.0] * (nx + 1) for _ in range(nt + 1)]
    for j in range(nx + 1):
        u[0][j] = ic(x_grid[j])

    r = alpha * dt / (dx * dx)
    status = "success"

    if method == "FTCS":
        if r > 0.5:
            # 稳定性不满足：不做迭代，标记为不稳定（由 AGH 决定重试/降级）
            status = "unstable"
        else:
            for i in range(1, nt + 1):
                for j in range(1, nx):
                    u[i][j] = u[i - 1][j] + r * (
                        u[i - 1][j + 1] - 2 * u[i - 1][j] + u[i - 1][j - 1]
                    )
                # 边界强制为 0
                u[i][0] = 0.0
                u[i][nx] = 0.0

    elif method == "CrankNicolson":
        # 三对角隐式格式，Thomas 算法求解。
        # 内部节点 1..nx-1 共 nx-1 个未知数；边界为 0。
        a_coeff = -r / 2.0
        b_coeff = 1.0 + r
        c_coeff = -r / 2.0
        a_list = [a_coeff] * (nx - 1)   # 下对角
        b_list = [b_coeff] * (nx - 1)   # 主对角
        c_list = [c_coeff] * (nx - 1)   # 上对角
        for i in range(1, nt + 1):
            rhs = [0.0] * (nx - 1)
            for j in range(1, nx):
                # CN 右端: u^i + (r/2)*(拉普拉斯 u^i), 系数 +r/2(非 -r/2)
                r_coeff = r / 2.0
                rhs[j - 1] = u[i - 1][j] + r_coeff * (
                    u[i - 1][j + 1] - 2 * u[i - 1][j] + u[i - 1][j - 1]
                )
            interior = _thomas(a_list, b_list, c_list, rhs, nx - 1)
            u[i] = [0.0] + interior + [0.0]
    else:
        return {"status": "rejected",
                "errors": [f"未知方法 {method}，仅支持 FTCS / CrankNicolson"],
                "r": r, "x_grid": x_grid, "t_grid": t_grid, "u": None}

    return {"status": status, "errors": [], "r": r,
            "x_grid": x_grid, "t_grid": t_grid, "u": u}


def _thomas(a, b, c, d, n):
    """Thomas 算法求解三对角线性方程组。n 为未知数个数（内部节点）。"""
    cp = [0.0] * n
    dp = [0.0] * n
    cp[0] = c[0] / b[0]
    dp[0] = d[0] / b[0]
    for i in range(1, n):
        denom = b[i] - a[i] * cp[i - 1]
        cp[i] = c[i] / denom if i < n - 1 else 0.0
        dp[i] = (d[i] - a[i] * dp[i - 1]) / denom
    x = [0.0] * n
    x[n - 1] = dp[n - 1]
    for i in range(n - 2, -1, -1):
        x[i] = dp[i] - cp[i] * x[i + 1]
    return x
