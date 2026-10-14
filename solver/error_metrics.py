# -*- coding: utf-8 -*-
"""
02_工具层实现 / error_metrics.py
误差统计与验证工具（平台无关，可独立运行）。
被 AGH 调用，输出定量误差指标与四层验证结论。
"""

import math


def max_abs_error(u, exact):
    """最大绝对误差。u / exact 布局：[i][j]，i 时间，j 空间。"""
    m = 0.0
    for i in range(len(u)):
        for j in range(len(u[i])):
            d = abs(u[i][j] - exact[i][j])
            if d > m:
                m = d
    return m


def l2_error(u, exact):
    """L2 误差（离散，未乘 dx*dt 的加权范数形式；可按需归一化）。"""
    s = 0.0
    n = 0
    for i in range(len(u)):
        for j in range(len(u[i])):
            s += (u[i][j] - exact[i][j]) ** 2
            n += 1
    return math.sqrt(s / n)


def relative_error(u, exact, A_upper):
    """相对误差 = 最大绝对误差 / 解析解幅值上界。A_upper 取初始幅值 A。"""
    return max_abs_error(u, exact) / A_upper


def boundary_check(u, tol=1e-8):
    """检查两端边界是否接近 0。返回 (是否通过, 最大边界偏差)。"""
    nx = len(u[0]) - 1
    worst = 0.0
    for i in range(len(u)):
        worst = max(worst, abs(u[i][0]), abs(u[i][nx]))
    return (worst < tol), worst


def trend_check(u):
    """
    物理趋势检查：初始单模态温度场幅值应随时间单调衰减。
    返回 (是否通过, 是否出现发散/NaN/Inf)。
    幅值取内部最大 |u|，应随时间不增。
    """
    nx = len(u[0]) - 1
    amplitudes = []
    for i in range(len(u)):
        amp = 0.0
        for j in range(1, nx):
            amp = max(amp, abs(u[i][j]))
        amplitudes.append(amp)
    # 检查发散/NaN/Inf
    diverged = any(math.isnan(a) or math.isinf(a) for a in amplitudes)
    # 检查单调性（允许极小数值噪声）
    monotone = True
    for k in range(1, len(amplitudes)):
        if amplitudes[k] > amplitudes[k - 1] + 1e-9:
            monotone = False
    return monotone, diverged


def validate(params, u, exact, thresholds=None):
    """
    汇总四层验证，输出定量指标与"是否通过"。
    thresholds: dict，可覆盖默认阈值；缺省见 06_日志归档与验证/阈值与验证标准.txt
    返回 dict，字段见 03_接口契约/io_schema.json 的 validation_result。
    """
    A = params.get("A", 1.0)
    # 默认阈值取"粗网格友好"档（1e-3），tool 调用方可传 thresholds 收紧到 1e-4/1e-5 做严格版
    defaults = {"boundary_tol": 1e-8, "max_abs_err": 1e-3, "l2_err": 1e-3}
    th = {**defaults, **(thresholds or {})}
    max_abs = max_abs_error(u, exact)
    l2 = l2_error(u, exact)
    rel = relative_error(u, exact, A)
    b_ok, b_dev = boundary_check(u, tol=th.get("boundary_tol", 1e-8))
    trend_ok, diverged = trend_check(u)

    # 阈值：基准误差按"量级目标"而非拍死；默认给收敛性目标（1e-3 粗网格档，可收紧）
    max_abs_thresh = th.get("max_abs_err", 1e-3)
    l2_thresh = th.get("l2_err", 1e-3)

    pass_max = max_abs < max_abs_thresh
    pass_l2 = l2 < l2_thresh
    overall = b_ok and trend_ok and (not diverged) and pass_max and pass_l2

    return {
        "max_abs_error": max_abs,
        "l2_error": l2,
        "relative_error": rel,
        "boundary_dev": b_dev,
        "boundary_ok": b_ok,
        "trend_ok": trend_ok,
        "diverged": diverged,
        "pass_max_abs": pass_max,
        "pass_l2": pass_l2,
        "overall_pass": overall,
    }
