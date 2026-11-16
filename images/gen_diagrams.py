# -*- coding: utf-8 -*-
"""
医疗健康数据平台与疾病统计分析 —— 报告插图批量生成脚本
======================================================
一次性生成报告所需的全部架构图 / 流程图 / E-R 图 / 大屏线框图 /
部署拓扑图 / 甘特图，输出到 code/images/ 目录（PNG, 300dpi, 中文标签）。

用法：
    python gen_diagrams.py                # 生成全部
    python gen_diagrams.py --only er_diagram,gantt_plan   # 只生成部分
    python gen_diagrams.py --list         # 列出可生成的图名

可幂等重跑（每次覆盖同名文件）。
"""
import os
import sys
import argparse
import numpy as np

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.patches import (FancyBboxPatch, FancyArrowPatch, Rectangle,
                                Circle, Wedge, Polygon)
from matplotlib.lines import Line2D

# ---------------------------------------------------------------------------
# 路径与字体
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = BASE_DIR
os.makedirs(OUT_DIR, exist_ok=True)

DPI = 300

_FONT_CANDIDATES = [
    r"C:/Windows/Fonts/simhei.ttf",
    r"C:/Windows/Fonts/msyh.ttc",
    r"C:/Windows/Fonts/msyhbd.ttc",
    r"C:/Windows/Fonts/simsun.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
_available = []
for _f in _FONT_CANDIDATES:
    if os.path.exists(_f):
        try:
            fm.fontManager.addfont(_f)
            _available.append(_f)
        except Exception:
            pass

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "WenQuanYi Zen Hei", "SimSun"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["savefig.dpi"] = DPI

# ---------------------------------------------------------------------------
# 统一配色
# ---------------------------------------------------------------------------
C_PRIMARY = "#1f6feb"   # 主色（蓝）
C_AUX     = "#2f9e6e"   # 辅助（绿）
C_ACCENT  = "#e8833a"   # 强调（橙）
C_NEUTRAL = "#6b7280"   # 中性（灰）
C_BG      = "#f7f9fc"   # 浅色背景
C_TEXT    = "#1f2937"   # 深色文字
C_WHITE   = "#ffffff"

FILL_BLUE   = "#e8f0fe"
FILL_GREEN  = "#e8f5ef"
FILL_ORANGE = "#fdf0e6"
FILL_GRAY   = "#eef2f7"
FILL_PURPLE = "#f0ecfb"
C_PURPLE    = "#7c5cf0"


# ===========================================================================
# 基础绘图工具
# ===========================================================================
def canvas(w_in, h_in, dpi=DPI):
    """创建一个 0..100 的横向坐标系（纵轴按图幅比例自动换算，保证数据单位等宽）。"""
    fig = plt.figure(figsize=(w_in, h_in), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    W = 100.0
    H = 100.0 * h_in / w_in
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    fig.patch.set_facecolor(C_BG)
    ax.set_facecolor(C_BG)
    return fig, ax, W, H


def rbox(ax, x, y, w, h, fc=FILL_BLUE, ec=C_PRIMARY, lw=1.5, radius=None,
         z=3, alpha=1.0, ls="solid"):
    """圆角矩形（(x,y) 为左下角）。"""
    if radius is None:
        radius = min(w, h) * 0.14
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={radius}",
                       linewidth=lw, edgecolor=ec, facecolor=fc,
                       mutation_aspect=1.0, zorder=z, alpha=alpha,
                       linestyle=ls)
    ax.add_patch(p)
    return p


def text(ax, x, y, s, fs=10, color=C_TEXT, ha="center", va="center",
         bold=False, z=6, **kw):
    return ax.text(x, y, s, fontsize=fs, color=color, ha=ha, va=va,
                   weight="bold" if bold else "normal", zorder=z, **kw)


def label_box(ax, x, y, s, fc=FILL_BLUE, ec=C_PRIMARY, fs=10, color=C_TEXT,
              bold=False, pad=0.35, z=5, lw=1.4):
    """带底色的文字标签块（用于层名等）。"""
    return ax.text(x, y, s, fontsize=fs, color=color, ha="center", va="center",
                   weight="bold" if bold else "normal", zorder=z,
                   bbox=dict(boxstyle=f"round,pad={pad}", fc=fc, ec=ec, lw=lw))


def node(ax, x, y, w, h, label, fc=FILL_BLUE, ec=C_PRIMARY, fs=9.5,
         color=C_TEXT, bold=True, lw=1.5, radius=None, z=3):
    """一个带文字的圆角节点（(x,y) 左下角）。"""
    rbox(ax, x, y, w, h, fc=fc, ec=ec, lw=lw, radius=radius, z=z)
    text(ax, x + w / 2, y + h / 2, label, fs=fs, color=color, bold=bold,
         z=z + 1, linespacing=1.45)
    return (x, y, w, h)


def arrow(ax, p1, p2, lab="", color=C_NEUTRAL, lw=1.8, fs=8.5, rad=0.0,
          tpos=0.5, tdx=0.0, tdy=0.0, style="-|>", ls="solid", z=4,
          lfc=None, tcolor=None, lw_text=1.2, box=True):
    """带可选标注的箭头。"""
    a = FancyArrowPatch(p1, p2, arrowstyle=style, mutation_scale=15,
                        linewidth=lw, color=color,
                        connectionstyle=f"arc3,rad={rad}",
                        linestyle=ls, zorder=z, shrinkA=1, shrinkB=1,
                        joinstyle="round")
    ax.add_patch(a)
    if lab:
        mx = p1[0] + (p2[0] - p1[0]) * tpos + tdx
        my = p1[1] + (p2[1] - p1[1]) * tpos + tdy
        bbox = dict(boxstyle="round,pad=0.22", fc=(lfc or C_BG),
                    ec="none", alpha=0.92) if box else None
        ax.text(mx, my, lab, fontsize=fs, color=(tcolor or color), ha="center",
                va="center", zorder=z + 2, bbox=bbox, linespacing=1.3)
    return a


def rel(ax, p1, p2, lab="", c1="1", c2="N", color=C_NEUTRAL, lw=1.2,
        fs=7.6, rad=0.0, z=2):
    """E-R 关系连线 + 基数标注。"""
    a = FancyArrowPatch(p1, p2, arrowstyle="-", color=color, lw=lw,
                        connectionstyle=f"arc3,rad={rad}", zorder=z)
    ax.add_patch(a)
    if lab:
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        ax.text(mx, my, lab, fontsize=fs, color=C_TEXT, ha="center", va="center",
                zorder=z + 3,
                bbox=dict(boxstyle="round,pad=0.2", fc=C_BG, ec=color, lw=0.7))
    for t, pt, o in ((c1, p1, p2), (c2, p2, p1)):
        if not t:
            continue
        # 放在靠近端点处
        dx, dy = o[0] - pt[0], o[1] - pt[1]
        L = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        px = pt[0] + dx / L * 3.2
        py = pt[1] + dy / L * 3.2
        ax.text(px, py, t, fontsize=fs, color=C_TEXT, ha="center", va="center",
                zorder=z + 4,
                bbox=dict(boxstyle="circle,pad=0.16", fc=C_WHITE, ec=color, lw=0.8))


def path_rel(ax, pts, lab="", c1="", c2="", color=C_NEUTRAL, lw=1.2, fs=7.6,
             z=2, lab_at=None):
    """折线式 E-R 关系（用于绕开实体框的走线）。"""
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    ax.plot(xs, ys, color=color, lw=lw, zorder=z, solid_joinstyle="round",
            solid_capstyle="round")
    if lab:
        lx, ly = lab_at if lab_at else (xs[len(xs) // 2], ys[len(ys) // 2])
        ax.text(lx, ly, lab, fontsize=fs, color=C_TEXT, ha="center", va="center",
                zorder=z + 3,
                bbox=dict(boxstyle="round,pad=0.2", fc=C_BG, ec=color, lw=0.7))
    for t, pt, o in ((c1, pts[0], pts[1]), (c2, pts[-1], pts[-2])):
        if not t:
            continue
        dx, dy = o[0] - pt[0], o[1] - pt[1]
        L = max((dx * dx + dy * dy) ** 0.5, 1e-6)
        ax.text(pt[0] + dx / L * 2.0, pt[1] + dy / L * 2.0, t, fontsize=fs,
                color=C_TEXT, ha="center", va="center", zorder=z + 4,
                bbox=dict(boxstyle="circle,pad=0.16", fc=C_WHITE, ec=color, lw=0.8))


def entity(ax, x, y_top, w, title, fields, hrow=2.05, th=2.9, fs=7.4,
           tfs=8.6, hcolor=C_PRIMARY, fcolor=C_TEXT, z=3):
    """E-R 实体表框：标题栏 + 字段行。返回几何锚点信息。"""
    n = len(fields)
    h = th + n * hrow
    y0 = y_top - h
    ax.add_patch(FancyBboxPatch((x, y0), w, h,
                                boxstyle="round,pad=0,rounding_size=0.55",
                                fc=C_WHITE, ec=C_NEUTRAL, lw=1.1, zorder=z))
    ax.add_patch(Rectangle((x + 0.22, y_top - th), w - 0.44, th - 0.12,
                           fc=hcolor, ec="none", zorder=z + 1))
    ax.text(x + w / 2, y_top - th / 2 - 0.05, title, ha="center", va="center",
            fontsize=tfs, color=C_WHITE, weight="bold", zorder=z + 2)
    for i, f in enumerate(fields):
        ty = y_top - th - (i + 0.5) * hrow
        ax.plot([x, x + w], [y_top - th - i * hrow] * 2, color="#e5e9f0",
                lw=0.6, zorder=z + 1)
        col = C_PRIMARY if f.startswith(("PK", "FK")) else fcolor
        ax.text(x + 0.55, ty, f, ha="left", va="center", fontsize=fs,
                color=col, zorder=z + 2,
                weight="bold" if f.startswith("PK") else "normal")
    return dict(x=x, y0=y0, w=w, h=h, top=y_top, bottom=y0,
                cx=x + w / 2, cy=y_top - h / 2,
                left=(x, y_top - h / 2), right=(x + w, y_top - h / 2),
                topmid=(x + w / 2, y_top), botmid=(x + w / 2, y0))


# --- 小图表（用于大屏线框图） ---------------------------------------------
def mini_bars(ax, x, y, w, h, color=C_PRIMARY, n=6, seed=1, z=5, gap=0.35):
    rng = np.random.default_rng(seed)
    vals = rng.uniform(0.35, 1.0, n)
    bw = w / n * (1 - gap)
    for i, v in enumerate(vals):
        cx = x + (i + 0.5) * w / n
        ax.add_patch(Rectangle((cx - bw / 2, y), bw, h * v, fc=color, ec="none",
                               alpha=0.85, zorder=z))


def mini_bars2(ax, x, y, w, h, colors, n=6, seed=1, z=5, gap=0.35):
    rng = np.random.default_rng(seed)
    vals = rng.uniform(0.35, 1.0, n)
    bw = w / n * (1 - gap)
    for i, v in enumerate(vals):
        cx = x + (i + 0.5) * w / n
        ax.add_patch(Rectangle((cx - bw / 2, y), bw, h * v, fc=colors[i % len(colors)],
                               ec="none", alpha=0.9, zorder=z))


def mini_hbar(ax, x, y, w, h, color=C_AUX, n=6, seed=3, z=5, gap=0.4):
    rng = np.random.default_rng(seed)
    vals = np.sort(rng.uniform(0.3, 1.0, n))
    bh = h / n * (1 - gap)
    for i, v in enumerate(vals):
        cy = y + (i + 0.5) * h / n
        ax.add_patch(Rectangle((x, cy - bh / 2), w * v, bh, fc=color, ec="none",
                               alpha=0.85, zorder=z))
    ax.plot([x, x], [y, y + h], color=C_NEUTRAL, lw=0.6, zorder=z)
    ax.plot([x, x + w], [y, y], color=C_NEUTRAL, lw=0.6, zorder=z)


def mini_line(ax, x, y, w, h, color=C_ACCENT, seed=2, z=5, fill=True, n=24):
    xs = np.linspace(x, x + w, n)
    if seed == 2:      # 24 小时门急诊高峰
        t = np.linspace(0, 1, n)
        base = 0.28 + 0.62 * np.exp(-((t - 0.42) ** 2) / 0.012) \
               + 0.34 * np.exp(-((t - 0.72) ** 2) / 0.02)
        ys = base
    else:
        rng = np.random.default_rng(seed)
        ys = 0.3 + 0.45 * np.abs(np.sin(np.linspace(0, 3.2, n))) + 0.08 * rng.random(n)
    ys = y + h * np.clip(ys, 0.02, 0.98)
    if fill:
        ax.add_patch(Polygon(list(zip(xs, ys)) + [(x + w, y), (x, y)],
                             closed=True, fc=color, alpha=0.13, zorder=z - 1))
    ax.plot(xs, ys, color=color, lw=1.8, zorder=z, solid_capstyle="round")
    ax.plot([x, x], [y, y + h], color=C_NEUTRAL, lw=0.6, zorder=z)
    ax.plot([x, x + w], [y, y], color=C_NEUTRAL, lw=0.6, zorder=z)


def mini_pie(ax, cx, cy, r, colors, seed=4, z=5):
    rng = np.random.default_rng(seed)
    vals = rng.uniform(1, 3.2, len(colors))
    vals = vals / vals.sum() * 360
    start = 90
    for v, c in zip(vals, colors):
        ax.add_patch(Wedge((cx, cy), r, start - v, start, fc=c, ec=C_WHITE,
                           lw=0.9, zorder=z))
        start -= v


def mini_hist(ax, x, y, w, h, color=C_PURPLE, seed=7, z=5, n=10):
    rng = np.random.default_rng(seed)
    v = rng.normal(0.5, 0.22, 4000)
    v = v[(v > 0) & (v < 1)]
    cnt, edges = np.histogram(v, bins=n, range=(0, 1))
    cnt = cnt / cnt.max()
    bw = w / n * 0.86
    for i, c in enumerate(cnt):
        cx = x + (i + 0.5) * w / n
        ax.add_patch(Rectangle((cx - bw / 2, y), bw, h * c, fc=color, ec="none",
                               alpha=0.85, zorder=z))
    ax.plot([x, x], [y, y + h], color=C_NEUTRAL, lw=0.6, zorder=z)
    ax.plot([x, x + w], [y, y], color=C_NEUTRAL, lw=0.6, zorder=z)


def panel(ax, x, y, w, h, title, fc=C_WHITE, ec="#d8dee9", tfs=10.5, z=3,
          tcolor=C_TEXT):
    rbox(ax, x, y, w, h, fc=fc, ec=ec, lw=1.2, radius=1.0, z=z)
    ax.plot([x + 0.4, x + w - 0.4], [y + h - 3.0] * 2, color="#e5e9f0",
            lw=1.0, zorder=z + 1)
    ax.add_patch(Circle((x + 1.5, y + h - 1.5), 0.42, fc=C_PRIMARY, ec="none",
                        zorder=z + 2))
    text(ax, x + 2.6, y + h - 1.55, title, fs=tfs, color=tcolor, bold=True,
         ha="left", va="center", z=z + 2)
    return (x, y, w, h)


def save(fig, name):
    path = os.path.join(OUT_DIR, name)
    fig.savefig(path, dpi=DPI, facecolor=C_BG, bbox_inches=None)
    plt.close(fig)
    print(f"[OK] {name}")
    return path


# ===========================================================================
# 1. 系统总体架构图
# ===========================================================================
def gen_arch_overall():
    w_in, h_in = 14.0, 12.6
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.6, "医疗健康数据平台 · 系统总体架构",
         fs=20, color=C_TEXT, bold=True)
    text(ax, W / 2, H - 5.1,
         "数据源 → 采集 → 缓冲 → 存储 → 计算 → 服务 → 应用  七层体系",
         fs=10.5, color=C_NEUTRAL)

    top = H - 7.2
    bottom = 2.0
    gap = 1.9
    n_layer = 7
    hl = (top - bottom - gap * (n_layer - 1)) / n_layer

    layers = [
        dict(name="数据源层", fill=FILL_GRAY, edge=C_NEUTRAL, tab=C_NEUTRAL, items=[
            "医院 HIS 业务库\n挂号 / 门诊病历 / 处方 / 住院 / 药品",
            "外部爬虫数据\n国家卫健委疫情通报 / 公开疾病统计",
        ]),
        dict(name="数据采集层", fill=FILL_BLUE, edge=C_PRIMARY, tab=C_PRIMARY, items=[
            "Python 模拟数据生成器\n(10 万级挂号记录)",
            "Scrapy / Requests\n爬虫采集",
            "Flume / Sqoop\n(可选，增量采集)",
        ]),
        dict(name="消息缓冲层", fill=FILL_ORANGE, edge=C_ACCENT, tab=C_ACCENT, items=[
            "Kafka 主题\nmed_registration",
            "Kafka 主题\nmed_visit",
            "Kafka 主题\nmed_prescription",
        ]),
        dict(name="数据存储层", fill=FILL_GREEN, edge=C_AUX, tab=C_AUX, items=[
            "HDFS\n分布式文件存储 (原始/ODS 文件)",
            "Hive 数仓\nODS / DWD / DWS / ADS 分层",
        ]),
        dict(name="计算层", fill=FILL_BLUE, edge=C_PRIMARY, tab=C_PRIMARY, items=[
            "离线计算\nSpark SQL / PySpark",
            "实时计算\nSpark Streaming",
            "机器学习\nSpark MLlib",
        ]),
        dict(name="数据服务层", fill=FILL_GREEN, edge=C_AUX, tab=C_AUX, items=[
            "结果落库\nMySQL (ads_* 结果表)",
            "结果落库\nHive ADS 表",
        ]),
        dict(name="应用展示层", fill=FILL_ORANGE, edge=C_ACCENT, tab=C_ACCENT, items=[
            "Flask + Bootstrap + ECharts\n可视化大屏",
            "报表导出\n(Excel / PDF)",
        ]),
    ]

    rects = []
    y_cursor = top
    for ly in layers:
        y0 = y_cursor - hl
        rbox(ax, 2, y0, 96, hl, fc=ly["fill"], ec=ly["edge"], lw=1.6, radius=1.1, z=2)
        # 左侧层名色块
        node(ax, 3.4, y0 + 0.9, 14.5, hl - 1.8, ly["name"], fc=ly["tab"],
             ec=ly["tab"], fs=11.5, color=C_WHITE, bold=True, radius=1.0, z=4)
        # 右侧条目
        items = ly["items"]
        n = len(items)
        cw = (79.0 - (n - 1) * 1.6) / n
        for i, it in enumerate(items):
            cx = 19.5 + i * (cw + 1.6)
            node(ax, cx, y0 + 0.9, cw, hl - 1.8, it, fc=C_WHITE, ec=ly["edge"],
                 fs=8.8, color=C_TEXT, bold=False, lw=1.2, radius=0.8, z=4)
        rects.append((y0, y0 + hl))
        y_cursor = y0 - gap

    # 传输内容箭头（自下而上：数据源 → 应用）
    trans = [
        "抽取 / 抓取", "JSON 消息", "消费落盘 (ORC / Parquet)",
        "Hive 表 / 宽表读取", "指标结果聚合", "REST API / JSON",
    ]
    for i in range(n_layer - 1):
        y_lo = rects[i][1]          # 下层顶部
        y_hi = rects[i + 1][0]      # 上层底部
        arrow(ax, (44, y_lo + 0.15), (44, y_hi - 0.15),
              lab=trans[i], color=layers[i + 1]["tab"], lw=2.0, fs=8.6,
              tdx=14.5, box=False, tcolor=layers[i + 1]["tab"])
    return save(fig, "arch_overall.png")


# ===========================================================================
# 2. Lambda 架构图
# ===========================================================================
def gen_arch_lambda():
    w_in, h_in = 14.0, 10.2
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.6, "Lambda 架构：批处理层 + 速度层 双链路",
         fs=19, color=C_TEXT, bold=True)

    # 数据源
    node(ax, 30, H - 10.5, 40, 5.4,
         "数据源：HIS 业务库 / 卫健委爬虫 / Python 模拟生成器",
         fc=FILL_GRAY, ec=C_NEUTRAL, fs=10, bold=False, z=4)

    # 两个大层
    grp_top, grp_bot = H - 16.0, 15.0
    # 批处理层
    rbox(ax, 3, grp_bot, 45.5, grp_top - grp_bot, fc=FILL_BLUE, ec=C_PRIMARY,
         lw=1.6, radius=1.2, z=2)
    label_box(ax, 25.75, grp_top - 2.2, "批处理层 Batch Layer", fc=C_PRIMARY,
              ec=C_PRIMARY, fs=12, color=C_WHITE, z=5)
    batch = [
        ("HDFS\n全量数据存储（不可变）", C_AUX, FILL_GREEN),
        ("Hive 数仓\nODS → DWD → DWS", C_AUX, FILL_GREEN),
        ("Spark 离线计算\nSpark SQL 全量重算", C_PRIMARY, C_WHITE),
        ("批视图 Batch View\n历史全量指标（准、延时高）", C_PRIMARY, FILL_BLUE),
    ]
    by = grp_top - 5.0
    bh = (by - grp_bot - 1.2) / len(batch) - 1.5
    for txt_, ec, fc in batch:
        node(ax, 5.0, by - bh, 41.5, bh, txt_, fc=fc, ec=ec, fs=9.6,
             bold=False, z=4, radius=0.8)
        by -= bh + 1.5
    # 速度层
    rbox(ax, 51.5, grp_bot, 45.5, grp_top - grp_bot, fc=FILL_ORANGE,
         ec=C_ACCENT, lw=1.6, radius=1.2, z=2)
    label_box(ax, 74.25, grp_top - 2.2, "速度层 Speed Layer", fc=C_ACCENT,
              ec=C_ACCENT, fs=12, color=C_WHITE, z=5)
    speed = [
        ("Kafka 消息队列\nmed_registration / med_visit / med_prescription", C_ACCENT, FILL_ORANGE),
        ("Spark Streaming\n窗口 60s 实时计算", C_ACCENT, C_WHITE),
        ("实时视图 Speed View\n增量指标（快、延时低）", C_ACCENT, FILL_ORANGE),
    ]
    sy = grp_top - 5.0
    sh = (sy - grp_bot - 1.2) / len(speed) - 1.5
    for txt_, ec, fc in speed:
        node(ax, 53.5, sy - sh, 41.5, sh, txt_, fc=fc, ec=ec, fs=9.6,
             bold=False, z=4, radius=0.8)
        sy -= sh + 1.5

    # 数据源分流箭头
    arrow(ax, (42, H - 10.5), (25.75, grp_top - 0.4), color=C_PRIMARY, lw=2.0,
          lab="全量 / 离线导入", fs=8.6, tdx=-3, tdy=1.2, tcolor=C_PRIMARY)
    arrow(ax, (58, H - 10.5), (74.25, grp_top - 0.4), color=C_ACCENT, lw=2.0,
          lab="实时写入", fs=8.6, tdx=5, tdy=1.2, tcolor=C_ACCENT)

    # 服务层
    node(ax, 20, 8.0, 60, 6.0,
         "服务层 Serving Layer\nMySQL 结果库（ads_*）+ 批视图 ∪ 实时视图 查询合并",
         fc=FILL_GREEN, ec=C_AUX, fs=10, bold=False, z=4)
    arrow(ax, (25.75, grp_bot + 0.2), (35, 14.2), color=C_PRIMARY, lw=2.0,
          lab="批视图", fs=8.6, tdx=-4, tcolor=C_PRIMARY)
    arrow(ax, (74.25, grp_bot + 0.2), (65, 14.2), color=C_ACCENT, lw=2.0,
          lab="实时视图", fs=8.6, tdx=4, tcolor=C_ACCENT)

    # 应用层
    node(ax, 32, 1.2, 36, 5.0,
         "应用展示层：Flask + Bootstrap + ECharts 可视化大屏",
         fc=FILL_ORANGE, ec=C_ACCENT, fs=9.8, bold=False, z=4)
    arrow(ax, (50, 8.0), (50, 6.4), color=C_AUX, lw=2.0)

    return save(fig, "arch_lambda.png")


# ===========================================================================
# 3. Hive 数仓分层图
# ===========================================================================
def gen_hive_layers():
    w_in, h_in = 13.6, 10.4
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.6, "Hive 数据仓库分层设计（ODS → DWD → DWS → ADS）",
         fs=18, color=C_TEXT, bold=True)

    top = H - 10.0
    bot = 6.4
    gap = 2.4
    n = 4
    band = (top - bot - gap * (n - 1)) / n

    spec = [
        dict(name="ADS 应用层", fill=FILL_ORANGE, edge=C_ACCENT, tab=C_ACCENT,
             key="面向业务指标的结果表，直供 MySQL / ECharts 大屏",
             tabs=["ads_disease_distribution", "ads_visit_peak", "ads_dept_workload",
                   "ads_drug_consumption", "ads_los_analysis", "ads_overview_kpi",
                   "ads_infectious_monitor"]),
        dict(name="DWS 轻度汇总层", fill=FILL_PURPLE, edge=C_PURPLE, tab=C_PURPLE,
             key="按 科室 / 疾病 / 时间 轻度聚合，构建汇总宽表",
             tabs=["dws_dept_workload", "dws_disease_stat", "dws_visit_hour",
                   "dws_drug_use"]),
        dict(name="DWD 明细层", fill=FILL_BLUE, edge=C_PRIMARY, tab=C_PRIMARY,
             key="数据清洗（去重 / 空值 / 异常）+ 脱敏 + 维度退化 + 口径统一",
             tabs=["dwd_registration_detail", "dwd_visit_detail",
                   "dwd_prescription_detail", "dwd_admission_detail"]),
        dict(name="ODS 原始层", fill=FILL_GREEN, edge=C_AUX, tab=C_AUX,
             key="贴源存储，结构与源系统一致；保留原始字段，另存已脱敏快照",
             tabs=["ods_registration", "ods_visit", "ods_prescription",
                   "ods_drug", "ods_admission"]),
    ]

    y_cursor = top
    for sp in spec:
        y0 = y_cursor - band
        rbox(ax, 2, y0, 96, band, fc=sp["fill"], ec=sp["edge"], lw=1.6,
             radius=1.1, z=2)
        node(ax, 3.4, y0 + 0.9, 15.5, band - 1.8, sp["name"], fc=sp["tab"],
             ec=sp["tab"], fs=11.0, color=C_WHITE, bold=True, radius=0.9, z=4)
        text(ax, 20.0, y0 + band - 2.6, sp["key"], fs=9.4, color=C_TEXT,
             ha="left", va="center", bold=False)
        tabs = sp["tabs"]
        nn = len(tabs)
        cw = (76.0 - (nn - 1) * 1.3) / nn
        for i, tb in enumerate(tabs):
            cx = 20.0 + i * (cw + 1.3)
            node(ax, cx, y0 + 0.9, cw, band - 5.6, tb, fc=C_WHITE, ec=sp["edge"],
                 fs=8.0, color=C_TEXT, bold=False, lw=1.1, radius=0.6, z=4)
        y_cursor = y0 - gap

    # 层间箭头（自下而上）：ODS→DWD→DWS→ADS
    up_labels = [
        "清洗 / 脱敏后明细", "按维度轻度汇总", "生成业务指标结果",
    ]
    bands = []
    y_cursor = top
    for sp in spec:
        bands.append((y_cursor - band, y_cursor))
        y_cursor -= band + gap
    # bands 顺序为 ADS→DWS→DWD→ODS，自下而上的第 i 段对应 up_labels[n-2-i]
    for i in range(n - 1):
        y_lo = bands[i + 1][1]
        y_hi = bands[i][0]
        arrow(ax, (49, y_lo - 0.15), (49, y_hi + 0.15), lab=up_labels[n - 2 - i],
              color=spec[i]["tab"], lw=2.0, fs=8.6, tdx=18, box=False,
              tcolor=spec[i]["tab"])

    # 输入（底部 → ODS） / 输出（ADS → 顶部）
    node(ax, 30, 0.8, 40, 3.8, "输入：Kafka / HDFS 原始数据", fc=FILL_GRAY,
         ec=C_NEUTRAL, fs=9.2, bold=False, z=4)
    arrow(ax, (50, 4.7), (50, bot - 0.15), color=C_NEUTRAL, lw=1.8)
    node(ax, 34, H - 8.9, 44, 3.8, "输出：MySQL 结果表 / ECharts 大屏",
         fc=FILL_GRAY, ec=C_NEUTRAL, fs=9.2, bold=False, z=4)
    arrow(ax, (56, top + 0.15), (56, H - 9.05), color=C_NEUTRAL, lw=1.8)
    return save(fig, "hive_layers.png")


# ===========================================================================
# 4. 数据流转流程图（横向泳道）
# ===========================================================================
def gen_flow_data():
    w_in, h_in = 15.0, 9.6
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.4, "数据流转流程图（横向泳道）",
         fs=18, color=C_TEXT, bold=True)
    text(ax, W / 2, H - 4.8,
         "数据生成/爬取 → 脱敏 → Kafka → HDFS → Hive ODS→DWD→DWS→ADS → MySQL → Flask / ECharts",
         fs=10, color=C_NEUTRAL)

    lanes = [
        ("采集层", FILL_BLUE, C_PRIMARY),
        ("缓冲层", FILL_ORANGE, C_ACCENT),
        ("存储层", FILL_GREEN, C_AUX),
        ("数仓层", FILL_PURPLE, C_PURPLE),
        ("服务层", FILL_GREEN, C_AUX),
        ("展示层", FILL_ORANGE, C_ACCENT),
    ]
    top = H - 7.2
    bot = 2.0
    gap = 1.0
    n = len(lanes)
    lh = (top - bot - gap * (n - 1)) / n

    lane_rect = []
    y_cursor = top
    for name, fc, ec in lanes:
        y0 = y_cursor - lh
        rbox(ax, 2, y0, 96, lh, fc=fc, ec=ec, lw=1.3, radius=0.8, z=2)
        node(ax, 3.0, y0 + 0.7, 11.5, lh - 1.4, name, fc=ec, ec=ec, fs=10.5,
             color=C_WHITE, bold=True, radius=0.7, z=4)
        lane_rect.append((y0, y_cursor))
        y_cursor = y0 - gap

    ycs = [ (a+b)/2 for a,b in lane_rect ]

    # 各泳道节点
    n1 = node(ax, 16.5, ycs[0] - lh*0.36, 22, lh*0.72,
              "Python 模拟生成器\n(挂号/就诊/处方 明细)", fc=C_WHITE, ec=C_PRIMARY,
              fs=8.6, bold=False, z=4)
    n2 = node(ax, 41.0, ycs[0] - lh*0.36, 19, lh*0.72,
              "Scrapy / Requests\n爬虫采集", fc=C_WHITE, ec=C_PRIMARY,
              fs=8.6, bold=False, z=4)
    n3 = node(ax, 63.0, ycs[0] - lh*0.36, 22, lh*0.72,
              "数据脱敏\n掩码 / 哈希加盐 / 泛化", fc=C_WHITE, ec=C_PRIMARY,
              fs=8.6, bold=False, z=4)

    kafka = node(ax, 16.5, ycs[1] - lh*0.36, 68.5, lh*0.72,
                 "Kafka 消息队列   |   med_registration  ·  med_visit  ·  med_prescription",
                 fc=C_WHITE, ec=C_ACCENT, fs=9.4, bold=False, z=4)

    hdfs = node(ax, 16.5, ycs[2] - lh*0.36, 40, lh*0.72,
                "HDFS 原始文件 / 贴源落地 (ORC)", fc=C_WHITE, ec=C_AUX,
                fs=9.0, bold=False, z=4)
    text(ax, 80, ycs[2], "（分区：dt=yyyyMMdd）", fs=8.4, color=C_NEUTRAL)

    hive_tabs = ["Hive ODS", "Hive DWD", "Hive DWS", "Hive ADS"]
    hx = 16.5
    hw = 19.0
    hive_nodes = []
    for i, t in enumerate(hive_tabs):
        c = node(ax, hx, ycs[3] - lh*0.36, hw, lh*0.72, t, fc=C_WHITE,
                 ec=C_PURPLE, fs=9.2, bold=True, z=4)
        hive_nodes.append(c)
        hx += hw + 0.8

    mysql = node(ax, 16.5, ycs[4] - lh*0.36, 34, lh*0.72,
                 "MySQL 结果库  ads_* 指标表", fc=C_WHITE, ec=C_AUX,
                 fs=9.2, bold=False, z=4)
    check = node(ax, 53.5, ycs[4] - lh*0.36, 41.5, lh*0.72,
                 "结果校验 / 指标口径统一", fc=C_WHITE, ec=C_AUX,
                 fs=9.2, bold=False, z=4)
    dash = node(ax, 16.5, ycs[5] - lh*0.36, 48, lh*0.72,
                "Flask + Bootstrap + ECharts 可视化大屏", fc=C_WHITE, ec=C_ACCENT,
                fs=9.4, bold=False, z=4)
    report = node(ax, 67.5, ycs[5] - lh*0.36, 27.5, lh*0.72,
                  "报表导出 Excel / PDF", fc=C_WHITE, ec=C_ACCENT,
                  fs=9.2, bold=False, z=4)

    # 箭头
    arrow(ax, (38.5, ycs[0]), (41.0, ycs[0]), color=C_PRIMARY, lw=1.6)
    arrow(ax, (60.0, ycs[0]), (63.0, ycs[0]), color=C_PRIMARY, lw=1.6)
    arrow(ax, (74.0, lane_rect[0][0] - 0.1), (74.0, ycs[1] + lh*0.36),
          color=C_ACCENT, lw=2.0)
    # Kafka → HDFS
    arrow(ax, (36.5, lane_rect[1][0] - 0.1), (36.5, ycs[2] + lh*0.36),
          color=C_AUX, lw=2.0, lab="消费落盘", fs=8.4, tdx=6, tcolor=C_AUX)
    # HDFS → ODS
    arrow(ax, (30, lane_rect[2][0] - 0.1), (26, ycs[3] + lh*0.36),
          color=C_PURPLE, lw=2.0, lab="加载", fs=8.4, tdx=-4, tcolor=C_PURPLE)
    # 数仓内 ODS→DWD→DWS→ADS
    for i in range(3):
        x1 = 16.5 + (i + 1) * hw + i * 0.8
        arrow(ax, (x1 + 0.1, ycs[3]), (x1 + 0.7, ycs[3]), color=C_PURPLE, lw=2.0)
    # ADS → MySQL
    arrow(ax, (16.5 + 3 * (hw + 0.8) + hw / 2, lane_rect[3][0] - 0.1),
          (33, ycs[4] + lh*0.36), color=C_AUX, lw=2.0, lab="结果落库", fs=8.4,
          tdx=-5, tcolor=C_AUX)
    # MySQL → 结果校验
    arrow(ax, (50.5, ycs[4]), (53.5, ycs[4]), color=C_AUX, lw=1.8)
    # MySQL → 大屏（服务层 → 展示层）
    arrow(ax, (33, lane_rect[4][0] - 0.1), (33, ycs[5] + lh*0.36),
          color=C_ACCENT, lw=2.0, lab="REST API / JSON", fs=8.4, tdx=9,
          tcolor=C_ACCENT)
    # 大屏 → 报表导出
    arrow(ax, (64.5, ycs[5]), (67.5, ycs[5]), color=C_ACCENT, lw=1.8,
          lab="导出", fs=8.2, tdy=1.6, tcolor=C_ACCENT)
    return save(fig, "flow_data.png")


# ===========================================================================
# 5. 数据脱敏流程图
# ===========================================================================
def gen_flow_desensitize():
    w_in, h_in = 14.2, 7.9
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.4, "数据脱敏流程（字段级）", fs=18, color=C_TEXT,
         bold=True)
    text(ax, W / 2, H - 4.8,
         "原始字段 → 规则匹配 → 脱敏后字段 → 审计日志",
         fs=10, color=C_NEUTRAL)

    # 表头
    col_x = [2.5, 27.0, 54.0, 78.5]
    col_w = [23.0, 25.5, 23.0, 19.5]
    heads = ["原始字段（示例）", "脱敏规则", "脱敏后字段", "审计日志"]
    head_colors = [C_NEUTRAL, C_ACCENT, C_AUX, C_PURPLE]
    hy = H - 10.5
    hh = 4.2
    for cx, cw, hd, hc in zip(col_x, col_w, heads, head_colors):
        node(ax, cx, hy, cw, hh, hd, fc=hc, ec=hc, fs=10.5, color=C_WHITE,
             bold=True, radius=0.8, z=5)

    rows = [
        ("姓名：张伟", "保留姓氏，名字掩码（张*）", "张*", "记录"),
        ("身份证：110101199001011234", "保留前 6 后 4，中间掩码", "110101********1234", "记录"),
        ("手机号：13812345678", "中间 4 位掩码", "138****5678", "记录"),
        ("地址：北京市朝阳区建国路12号", "泛化到区县，去门牌", "北京市朝阳区", "记录"),
        ("病历号：MZ20250101001", "SHA-256 哈希加盐（不可逆）", "3f2a…9c7d", "记录"),
        ("邮箱：zhangwei@example.com", "掩码 @ 前用户名", "z***@example.com", "记录"),
    ]
    ry = hy - 1.4
    rh = 4.4
    rgap = 1.0
    for i, (a, b, c, _) in enumerate(rows):
        y0 = ry - rh
        for cx, cw, val, hc, is_rule in zip(
                col_x, col_w, [a, b, c, "时间 / 操作人 / 规则 / 结果"],
                head_colors, [False, True, False, False]):
            fc = FILL_ORANGE if is_rule else C_WHITE
            node(ax, cx, y0, cw, rh, val, fc=fc, ec=hc, fs=8.4, bold=False,
                 lw=1.1, radius=0.6, z=4)
        # 箭头 列1→列2→列3
        arrow(ax, (col_x[0] + col_w[0] + 0.2, y0 + rh / 2),
              (col_x[1] - 0.2, y0 + rh / 2), color=C_ACCENT, lw=1.6, z=5)
        arrow(ax, (col_x[1] + col_w[1] + 0.2, y0 + rh / 2),
              (col_x[2] - 0.2, y0 + rh / 2), color=C_AUX, lw=1.6, z=5)
        ry = y0 - rgap

    # 列3 → 审计日志（整体箭头）
    arrow(ax, (col_x[2] + col_w[2] + 0.3, (hy + ry) / 2),
          (col_x[3] - 0.3, (hy + ry) / 2), color=C_PURPLE, lw=2.6, z=5,
          style="-|>")
    text(ax, (col_x[2] + col_w[2] + col_x[3]) / 2, ry - 1.6,
         "写入审计日志", fs=8.6, color=C_PURPLE)

    # 底部补充说明
    yb = 1.6
    rbox(ax, 2.5, yb, 95.5, 4.0, fc=FILL_GRAY, ec=C_NEUTRAL, lw=1.2, radius=0.8, z=2)
    text(ax, 50, yb + 2.0,
         "说明：仅脱敏后的 DWD / DWS / ADS 数据对外服务；原始明文仅存于受控 ODS 快照，访问需授权并留痕。"
         "哈希加盐值统一为 MED_PLATFORM_2026_JLAU。",
         fs=8.8, color=C_TEXT)
    return save(fig, "flow_desensitize.png")


# ===========================================================================
# 6. 数据库 E-R 图
# ===========================================================================
def gen_er_diagram():
    w_in, h_in = 15.0, 11.0
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.4, "医疗健康数据平台 · 数据库 E-R 图",
         fs=19, color=C_TEXT, bold=True)
    text(ax, W / 2, H - 4.7,
         "核心业务实体关系（PK 主键 / FK 外键，连线标注 1:1 / 1:N / N:M）",
         fs=10, color=C_NEUTRAL)

    # 实体定义
    e_patient = entity(ax, 3.0, H - 8.0, 20.5, "patient 患者", [
        "PK patient_id", "name 姓名(脱敏)", "gender 性别",
        "birth_date 出生日期", "id_card 身份证(脱敏)",
        "phone 手机号(脱敏)", "address 地址(脱敏)",
    ], hcolor=C_PRIMARY)
    e_dept = entity(ax, 39.5, H - 8.0, 20.5, "department 科室", [
        "PK dept_id", "dept_name 科室名称", "dept_type 科室类型",
        "location 位置", "leader 负责人",
    ], hcolor=C_AUX)
    e_drug = entity(ax, 76.0, H - 8.0, 20.5, "drug 药品", [
        "PK drug_id", "drug_name 药品名称", "drug_type 药品类型",
        "spec 规格", "unit_price 单价", "manufacturer 生产厂家",
    ], hcolor=C_ACCENT)

    e_doctor = entity(ax, 3.0, H - 34.0, 20.5, "doctor 医生", [
        "PK doctor_id", "FK dept_id", "doctor_name 姓名",
        "title 职称", "specialty 专长", "reg_price 挂号费",
    ], hcolor=C_PRIMARY)

    e_reg = entity(ax, 39.5, H - 34.0, 20.5, "registration 挂号", [
        "PK reg_id", "FK patient_id", "FK doctor_id", "FK dept_id",
        "reg_time 挂号时间", "reg_type 挂号类型", "fee 费用", "status 状态",
    ], hcolor=C_PRIMARY)

    e_visit = entity(ax, 76.0, H - 34.0, 20.5, "visit 就诊病历", [
        "PK visit_id", "FK reg_id", "FK disease_id",
        "visit_time 就诊时间", "chief_complaint 主诉",
        "diagnosis 诊断", "is_infectious 是否传染病",
    ], hcolor=C_PRIMARY)

    e_adm = entity(ax, 3.0, 20.0, 20.5, "admission 住院", [
        "PK adm_id", "FK patient_id", "FK dept_id",
        "admit_time 入院时间", "discharge_time 出院时间",
        "los_days 住院天数", "bed_no 床位号",
    ], hcolor=C_AUX)

    e_disease = entity(ax, 39.5, 20.0, 20.5, "disease 疾病字典", [
        "PK disease_id", "disease_name 疾病名称",
        "disease_code ICD 编码", "category 疾病类别",
        "is_infectious 是否传染病",
    ], hcolor=C_PURPLE)

    e_presc = entity(ax, 76.0, 20.0, 20.5, "prescription 处方明细", [
        "PK presc_id", "FK visit_id", "FK drug_id",
        "quantity 数量", "dosage 用法用量",
        "days 用药天数", "amount 金额",
    ], hcolor=C_ACCENT)

    # ---- 关系连线 ----
    # patient 1:N registration（挂号）
    rel(ax, e_patient["right"], e_reg["left"], "挂号", "1", "N",
        color=C_PRIMARY, rad=0.08)
    # department 1:N registration（受理）
    rel(ax, e_dept["botmid"], (e_reg["cx"], e_reg["top"]), "受理", "1", "N",
        color=C_AUX, rad=0.0)
    # doctor 1:N registration（接诊）
    rel(ax, e_doctor["right"], e_reg["left"], "接诊", "1", "N",
        color=C_PRIMARY, rad=-0.12)
    # department 1:N doctor（所属，走中间走廊）
    path_rel(ax, [(e_dept["left"][0], e_dept["left"][1]), (33.0, e_dept["left"][1]),
                  (33.0, e_doctor["cy"]), e_doctor["right"]],
             lab="所属", c1="1", c2="N", color=C_AUX,
             lab_at=(36.4, 61.0))
    # registration 1:1 visit（就诊）
    rel(ax, e_reg["right"], e_visit["left"], "就诊", "1", "1",
        color=C_PRIMARY, rad=0.0)
    # visit N:1 disease（诊断）
    rel(ax, (e_visit["cx"], e_visit["bottom"]), (e_disease["cx"], e_disease["top"]),
        "诊断", "N", "1", color=C_PURPLE, rad=0.0)
    # visit 1:N prescription（开方）
    rel(ax, e_visit["botmid"], (e_presc["cx"], e_presc["top"]), "开方", "1", "N",
        color=C_ACCENT, rad=0.0)
    # drug 1:N prescription（包含，走右侧外圈）
    path_rel(ax, [e_drug["right"], (98.4, e_drug["right"][1]),
                  (98.4, e_presc["right"][1]), e_presc["right"]],
             lab="包含", c1="1", c2="N", color=C_ACCENT, lab_at=(97.8, 36.0))
    # patient 1:N admission（住院，走左侧外圈）
    path_rel(ax, [e_patient["left"], (1.2, e_patient["left"][1]),
                  (1.2, e_adm["right"][1]), e_adm["left"]],
             lab="住院", c1="1", c2="N", color=C_AUX, lab_at=(1.6, 36.0))
    # department 1:N admission（住院科室，走中间走廊）
    path_rel(ax, [(e_dept["left"][0], e_dept["cy"] - 4.0), (36.0, e_dept["cy"] - 4.0),
                  (36.0, e_adm["right"][1]), e_adm["right"]],
             c1="1", c2="N", color=C_AUX)
    # doctor 1:N admission（主管）
    rel(ax, (e_doctor["cx"], e_doctor["bottom"]), (e_adm["cx"], e_adm["top"]),
        "主管", "1", "N", color=C_NEUTRAL, rad=0.0)

    text(ax, W / 2, 0.8, "注：矩形为实体表（PK 主键 / FK 外键），连线上的数字表示基数（1 / N）。",
         fs=8.6, color=C_NEUTRAL)
    return save(fig, "er_diagram.png")


# ===========================================================================
# 7. 应用层结果表 E-R 图
# ===========================================================================
def gen_er_diagram_ads():
    w_in, h_in = 15.0, 10.2
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.4, "应用层（ADS）结果表 E-R 图", fs=19,
         color=C_TEXT, bold=True)
    text(ax, W / 2, H - 4.7,
         "以 stat_date（日期）/ dept（科室）/ disease（疾病）为公共维度组织，均直供大屏与报表",
         fs=9.8, color=C_NEUTRAL)

    # 中心维度
    hub = node(ax, 39.0, H / 2 - 6.0, 22.0, 12.0,
               "公共维度\n──────\nstat_date  统计日期\ndept_id / dept_name  科室\ndisease_id / disease_name  疾病",
               fc=FILL_PURPLE, ec=C_PURPLE, fs=8.6, bold=False, z=5)
    hub_c = (39.0 + 11.0, H / 2)

    # 7 张结果表（环绕）
    tables = [
        ("ads_overview_kpi 总览 KPI", ["stat_date", "total_visit 总就诊",
         "outpatient_cnt 门诊量", "admission_cnt 住院人次",
         "avg_los 平均住院日", "total_revenue 总收入"], 3.0, H - 9.0, C_PRIMARY, FILL_BLUE),
        ("ads_disease_distribution 疾病分布", ["stat_date", "disease_name",
         "disease_category", "case_cnt 病例数", "ratio 占比",
         "is_infectious"], 39.5, H - 9.0, C_AUX, FILL_GREEN),
        ("ads_visit_peak 就诊高峰", ["stat_date", "hour_of_day 0-23",
         "visit_cnt 就诊量", "reg_cnt 挂号量"], 76.0, H - 9.0, C_ACCENT, FILL_ORANGE),
        ("ads_dept_workload 科室工作量", ["stat_date", "dept_id / dept_name",
         "reg_cnt 挂号量", "visit_cnt 就诊量", "admission_cnt 住院量",
         "doctor_cnt 医生数"], 3.0, 41.0, C_AUX, FILL_GREEN),
        ("ads_drug_consumption 药品消耗", ["stat_date", "drug_id / drug_name",
         "total_qty 总消耗量", "total_amount 总金额"], 76.0, 44.0, C_ACCENT, FILL_ORANGE),
        ("ads_los_analysis 住院天数分析", ["stat_date", "dept_name",
         "avg_los 平均住院日", "min_los / max_los", "bed_turnover 床位周转"], 3.0, 23.5, C_PRIMARY, FILL_BLUE),
        ("ads_infectious_monitor 传染病监测", ["stat_date", "disease_name",
         "new_case 新增", "cumulative_case 累计", "alert_level 预警级别"], 76.0, 30.5, C_PURPLE, FILL_PURPLE),
    ]

    ents = []
    for title, fields, x, ytop, ec, fc in tables:
        e = entity(ax, x, ytop, 21.0, title, fields, hcolor=ec, fs=7.8, tfs=8.2,
                   hrow=1.95, th=2.9)
        ents.append((e, ec))
        rel(ax, (e["cx"], e["cy"]), hub_c, "", "", "",
            color=ec, lw=1.1, rad=0.06)
    # 中心框文字盖在连线之上
    rbox(ax, 39.0, H / 2 - 6.0, 22.0, 12.0, fc=FILL_PURPLE, ec=C_PURPLE,
         lw=1.6, radius=1.0, z=6)
    text(ax, 50.0, H / 2 + 0.6, "公共维度", fs=11, color=C_TEXT, bold=True, z=7)
    ax.plot([40.5, 59.5], [H / 2 - 1.2] * 2, color=C_PURPLE, lw=1.0, zorder=7)
    text(ax, 50.0, H / 2 - 3.0,
         "stat_date  统计日期\ndept_id / dept_name  科室\ndisease_id / disease_name  疾病",
         fs=8.4, color=C_TEXT, z=7, linespacing=1.6)
    return save(fig, "er_diagram_ads.png")


# ===========================================================================
# 8. 可视化大屏线框图（Mockup）
# ===========================================================================
def gen_dash_mockup():
    w_in, h_in = 16.0, 9.4
    fig, ax, W, H = canvas(w_in, h_in)

    # 背景
    rbox(ax, 0.5, 0.5, 99, H - 1.0, fc="#0f1b2d", ec="#0f1b2d", lw=1.0,
         radius=1.2, z=1)
    ax.text(W / 2, H - 2.3, "医疗健康数据平台 · 疾病统计分析可视化大屏",
            fontsize=15, color="#e6f0ff", ha="center", va="center", weight="bold",
            zorder=6)
    ax.add_patch(Rectangle((0.5, H - 3.6), 99, 0.35, fc=C_PRIMARY, ec="none",
                           zorder=5))

    # 筛选栏
    fy = H - 6.15
    flabels = ["时间范围：2025-01 ~ 2026-09", "科室：全部科室", "疾病类别：全部", "刷新：每 5 分钟"]
    fx = 3.0
    fw = 22.5
    for t in flabels:
        rbox(ax, fx, fy, fw, 2.4, fc="#1c2f4a", ec="#2b4666", lw=1.0, radius=0.6, z=3)
        text(ax, fx + fw / 2, fy + 1.2, t, fs=8.6, color="#cfe1ff", z=4)
        fx += fw + 1.3

    # KPI 卡片
    ky = H - 13.95
    kh = 6.6
    kpis = [("总就诊人次", "120,000", "+8.4%", C_PRIMARY),
            ("门诊量", "115,200", "+7.1%", C_AUX),
            ("住院人次", "14,000", "+3.2%", C_ACCENT),
            ("平均住院日", "7.6 天", "-0.4 天", C_PURPLE)]
    kw = (96.0 - 3 * 1.5) / 4
    kx = 2.0
    for name, val, delta, col in kpis:
        rbox(ax, kx, ky, kw, kh, fc="#152740", ec=col, lw=1.6, radius=0.8, z=3)
        ax.add_patch(Rectangle((kx, ky), 0.6, kh, fc=col, ec="none", zorder=4))
        text(ax, kx + 2.2, ky + kh - 1.7, name, fs=9.0, color="#9fb6d4",
             ha="left", z=5)
        text(ax, kx + 2.2, ky + 2.4, val, fs=15, color="#ffffff", ha="left",
             bold=True, z=5)
        text(ax, kx + kw - 2.0, ky + 2.4, delta, fs=9.0, color=col, ha="right",
             bold=True, z=5)
        kx += kw + 1.5

    # 中间三块
    my = H - 35.65
    mh = 20.3
    mw = (96.0 - 2 * 1.6) / 3
    mx = 2.0
    # 疾病分布
    p, y, w, h = panel(ax, mx, my, mw, mh, "疾病分布（柱状 + 饼图）",
                       fc="#132238", ec="#26405f", tcolor="#dce9ff", z=3)
    mini_bars(ax, mx + 1.6, my + 1.6, w * 0.52, h - 5.4, color=C_PRIMARY, n=6, seed=11)
    mini_pie(ax, mx + w * 0.78, my + h / 2 - 0.6, h * 0.28,
             [C_PRIMARY, C_AUX, C_ACCENT, C_PURPLE], seed=12)
    # 就诊高峰
    mx += mw + 1.6
    panel(ax, mx, my, mw, mh, "就诊高峰（24 小时折线）",
          fc="#132238", ec="#26405f", tcolor="#dce9ff", z=3)
    mini_line(ax, mx + 1.6, my + 1.6, w - 3.2, h - 5.4, color=C_ACCENT, seed=2)
    text(ax, mx + 1.8, my + 1.0, "0时", fs=7.0, color="#7f97b5", ha="left")
    text(ax, mx + w - 1.8, my + 1.0, "23时", fs=7.0, color="#7f97b5", ha="right")
    # 科室工作量
    mx += mw + 1.6
    panel(ax, mx, my, mw, mh, "科室工作量（横向条形）",
          fc="#132238", ec="#26405f", tcolor="#dce9ff", z=3)
    mini_hbar(ax, mx + 1.6, my + 1.6, w - 3.4, h - 5.4, color=C_AUX, n=6, seed=13)

    # 底部三块
    by = 1.6
    bh = 20.3
    bmw = (96.0 - 2 * 1.6) / 3
    bx = 2.0
    panel(ax, bx, by, bmw, bh, "药品消耗 TOP10（横向条形）",
          fc="#132238", ec="#26405f", tcolor="#dce9ff", z=3)
    mini_hbar(ax, bx + 1.6, by + 1.6, bmw - 3.4, bh - 5.4, color=C_ACCENT, n=8, seed=14)
    bx += bmw + 1.6
    panel(ax, bx, by, bmw, bh, "住院天数分布（直方图）",
          fc="#132238", ec="#26405f", tcolor="#dce9ff", z=3)
    mini_hist(ax, bx + 1.6, by + 1.6, bmw - 3.4, bh - 5.4, color=C_PURPLE, seed=7)
    bx += bmw + 1.6
    panel(ax, bx, by, bmw, bh, "传染病监测（折线）",
          fc="#132238", ec="#26405f", tcolor="#dce9ff", z=3)
    mini_line(ax, bx + 1.6, by + 1.6, bmw - 3.4, bh - 5.4, color=C_AUX, seed=21)
    return save(fig, "dash_mockup.png")


# ===========================================================================
# 9. 部署拓扑图
# ===========================================================================
def gen_deploy_topology():
    w_in, h_in = 14.6, 9.2
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.4, "系统部署拓扑图", fs=19, color=C_TEXT, bold=True)
    text(ax, W / 2, H - 4.7,
         "Windows 主机（开发 / 展示）  ←→  VMware 虚拟机 CentOS（单节点大数据集群）",
         fs=10, color=C_NEUTRAL)

    top = H - 7.4
    bot = 7.5
    # Windows 主机
    rbox(ax, 2, bot, 44, top - bot, fc=FILL_BLUE, ec=C_PRIMARY, lw=1.6,
         radius=1.2, z=2)
    label_box(ax, 24, top - 2.3, "Windows 主机（开发 / 展示）", fc=C_PRIMARY,
              ec=C_PRIMARY, fs=11.5, color=C_WHITE, z=5)
    win_items = [
        "PyCharm / VS Code\n代码开发与调试",
        "Anaconda · Python 3.11\npandas / matplotlib",
        "MySQL 8.0\n端口 3306（结果库）",
        "Flask Web 服务\n端口 5000",
        "浏览器 Chrome\nECharts 可视化大屏",
    ]
    wy = top - 5.0
    wh = (wy - bot - 0.8) / len(win_items) - 1.1
    for t in win_items:
        node(ax, 3.6, wy - wh, 40.8, wh, t, fc=C_WHITE, ec=C_PRIMARY, fs=8.8,
             bold=False, z=4, radius=0.7)
        wy -= wh + 1.1

    # CentOS 集群
    rbox(ax, 54, bot, 44, top - bot, fc=FILL_ORANGE, ec=C_ACCENT, lw=1.6,
         radius=1.2, z=2)
    label_box(ax, 76, top - 2.3, "VMware 虚拟机 CentOS 7（单节点）", fc=C_ACCENT,
              ec=C_ACCENT, fs=11.5, color=C_WHITE, z=5)
    cen_items = [
        "JDK 1.8\nJava 运行环境",
        "Hadoop 3.x\nHDFS :9870 / :9000 · YARN :8088",
        "Hive 3.x\nHiveServer2 :10000 · Metastore :9083",
        "ZooKeeper 3.x\n端口 2181",
        "Kafka 3.x\n端口 9092",
        "Spark 3.x\nMaster :7077 · UI :8080",
    ]
    cy = top - 5.0
    ch = (cy - bot - 0.8) / len(cen_items) - 1.0
    for t in cen_items:
        node(ax, 55.6, cy - ch, 40.8, ch, t, fc=C_WHITE, ec=C_ACCENT, fs=8.6,
             bold=False, z=4, radius=0.7)
        cy -= ch + 1.0

    # 连接线
    arrow(ax, (46.2, top - 9), (53.8, top - 9), color=C_AUX, lw=2.4,
          style="<|-|>")
    text(ax, 50, top - 7.6, "final shell\nSSH :22", fs=8.6, color=C_AUX,
         bold=True, linespacing=1.4)
    text(ax, 50, top - 12.4, "本地 localhost\n数据同步", fs=8.2, color=C_NEUTRAL)

    # 底部说明
    rbox(ax, 2, 1.2, 96, 5.2, fc=FILL_GRAY, ec=C_NEUTRAL, lw=1.2, radius=0.8, z=2)
    text(ax, 50, 3.8,
         "虚拟机建议配置：4 核 CPU / 8 GB 内存 / 60 GB 磁盘；大数据组件以单节点伪分布式运行，"
         "Kafka → Spark Streaming → MySQL 链路约占用 4 GB 内存。\n"
         "远程连接：final shell 通过 SSH(22) 登录 CentOS，端口转发访问 HDFS(9870)、YARN(8088)、Spark(8080) Web UI。",
         fs=8.8, color=C_TEXT, linespacing=1.6)
    return save(fig, "deploy_topology.png")


# ===========================================================================
# 10. 项目进度甘特图
# ===========================================================================
def gen_gantt_plan():
    w_in, h_in = 14.0, 8.4
    fig, ax, W, H = canvas(w_in, h_in)

    text(ax, W / 2, H - 2.4, "项目进度甘特图（两周排期）", fs=19,
         color=C_TEXT, bold=True)

    tasks = [
        ("需求分析与技术选型", 1, 2, C_PRIMARY),
        ("环境搭建（VMware CentOS）", 2, 4, C_PRIMARY),
        ("数据采集与数据脱敏", 4, 6, C_AUX),
        ("数仓分层建设（Hive）", 5, 8, C_AUX),
        ("离线统计分析（Spark SQL）", 8, 10, C_ACCENT),
        ("实时链路（Kafka + Streaming）", 9, 11, C_ACCENT),
        ("Web 可视化（Flask + ECharts）", 10, 13, C_PURPLE),
        ("联调测试与性能优化", 12, 14, C_NEUTRAL),
        ("报告撰写与答辩准备", 12, 14, C_NEUTRAL),
    ]

    x0, x1 = 33.0, 97.0
    y0, y1 = 6.8, H - 7.0
    n = len(tasks)
    ytop = y1 - 2.8
    rowh = (ytop - y0) / n

    def dx(day):
        return x0 + (day - 0.5) / 14.0 * (x1 - x0)

    # 表头（周 / 日）
    ax.add_patch(Rectangle((x0, y1), x1 - x0, 3.2, fc=C_PRIMARY, ec="none",
                           zorder=3))
    for wk, (a, b) in enumerate([(1, 7), (8, 14)]):
        text(ax, x0 + ((a - 0.5) + (b - 0.5)) / 2 / 14.0 * (x1 - x0),
             y1 + 1.6, f"第 {wk + 1} 周（Day {a}-{b}）", fs=10.5,
             color=C_WHITE, bold=True, z=5)
    for d in range(1, 15):
        text(ax, dx(d), y1 - 1.35, str(d), fs=8.2, color=C_TEXT, z=5)
        ax.plot([dx(d) - (x1 - x0) / 28.0] * 2, [y0, y1], color="#e5e9f0",
                lw=0.6, zorder=1)

    # 周分隔线
    ax.plot([x0 + 7 / 14.0 * (x1 - x0)] * 2, [y0, y1 + 3.2], color=C_ACCENT,
            lw=2.0, ls="--", zorder=4)

    # 任务条
    for i, (name, s, e, col) in enumerate(tasks):
        yc = ytop - (i + 0.5) * rowh
        hb = rowh * 0.52
        if i % 2 == 0:
            ax.add_patch(Rectangle((x0, yc - rowh / 2), x1 - x0, rowh,
                                   fc="#eef2f7", ec="none", zorder=0))
        text(ax, x0 - 1.0, yc, name, fs=9.2, color=C_TEXT, ha="right",
             va="center", z=5)
        bx = dx(s) - (x1 - x0) / 28.0
        bw = (e - s + 1) / 14.0 * (x1 - x0)
        rbox(ax, bx, yc - hb / 2, bw, hb, fc=col, ec=col, lw=1.0,
             radius=hb * 0.35, z=4)
        text(ax, bx + bw / 2, yc, f"{e - s + 1} 天", fs=8.0, color=C_WHITE,
             bold=True, z=5)

    text(ax, 50, 3.6,
         "说明：第 1 周以环境搭建与数据准备为主，第 2 周以离线/实时计算与 Web 可视化为主，测试与报告贯穿后段。",
         fs=9.0, color=C_NEUTRAL)
    return save(fig, "gantt_plan.png")


# ===========================================================================
# 调度
# ===========================================================================
GENERATORS = {
    "arch_overall": gen_arch_overall,
    "arch_lambda": gen_arch_lambda,
    "hive_layers": gen_hive_layers,
    "flow_data": gen_flow_data,
    "flow_desensitize": gen_flow_desensitize,
    "er_diagram": gen_er_diagram,
    "er_diagram_ads": gen_er_diagram_ads,
    "dash_mockup": gen_dash_mockup,
    "deploy_topology": gen_deploy_topology,
    "gantt_plan": gen_gantt_plan,
}


def main():
    ap = argparse.ArgumentParser(description="生成报告插图")
    ap.add_argument("--only", type=str, default="",
                    help="逗号分隔的图名，仅生成指定图")
    ap.add_argument("--list", action="store_true", help="列出可生成的图名")
    args = ap.parse_args()

    if args.list:
        for k in GENERATORS:
            print(k)
        return

    names = [s.strip() for s in args.only.split(",") if s.strip()] or list(GENERATORS)
    print(f"字体候选（已注册）：{_available}")
    print(f"输出目录：{OUT_DIR}")
    for nm in names:
        if nm not in GENERATORS:
            print(f"[SKIP] 未知图名：{nm}")
            continue
        GENERATORS[nm]()

    # 自检：打印尺寸
    print("\n===== 尺寸自检 =====")
    try:
        from PIL import Image
        for nm in names:
            p = os.path.join(OUT_DIR, f"{nm}.png")
            if os.path.exists(p):
                with Image.open(p) as im:
                    print(f"{nm}.png  {im.size[0]}x{im.size[1]}  dpi={im.info.get('dpi')}")
    except Exception as e:
        print("PIL 自检跳过：", e)


if __name__ == "__main__":
    main()
