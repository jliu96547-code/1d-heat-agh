# -*- coding: utf-8 -*-
"""
02_工具层实现 / analytical.py
解析解计算工具（平台无关，可独立运行）。
被 AGH 调用，用于提供验证基准。
"""

import math


def u_exact(x, t, alpha, A, L):
    """
    解析解：u_exact(x,t) = A * exp(-alpha*(pi/L)^2*t) * sin(pi*x/L)
    边界 x=0 或 x=L 时 sin 项为 0，与齐次 Dirichlet 边界一致。
    """
    decay = math.exp(-alpha * (math.pi / L) ** 2 * t)
    return A * decay * math.sin(math.pi * x / L)


def compute_exact(params, x_grid, t_grid):
    """
    在给定网格上计算解析解。
    返回二维数组 exact[i][j] = u_exact(x_grid[j], t_grid[i])
    （与 heat_solver.solve 的 u[i][j] 布局一致：i 为时间，j 为空间）
    """
    alpha = params["alpha"]
    A = params["A"]
    L = params["L"]
    nt = len(t_grid) - 1
    nx = len(x_grid) - 1
    exact = [[0.0] * (nx + 1) for _ in range(nt + 1)]
    for i in range(nt + 1):
        for j in range(nx + 1):
            exact[i][j] = u_exact(x_grid[j], t_grid[i], alpha, A, L)
    return exact
