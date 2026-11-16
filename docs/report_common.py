# -*- coding: utf-8 -*-
"""
报告生成公共模块
==================================================================
供「完整报告 / 前端同学报告 / 后端同学报告」三份生成脚本共用：
  · 图表编号、表格编号的计数器与 tab()/fig() 封装
  · 从 MySQL 读取统计结果的便捷函数（kpi / mv / netv / q / q1）
  · 数值格式化（fmtd / wan）

三份报告的数据全部从 MySQL（库 med_health）实时读取，
保证报告数字与系统运行结果完全一致，不存在手工抄录误差。
"""
from __future__ import annotations

import os
import sys

from docx.shared import Cm, Pt
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

_DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
if _DOCS_DIR not in sys.path:
    sys.path.insert(0, _DOCS_DIR)

from report_builder import Report, OUT_DIR, IMG, ROOT, TEMPLATE, img, set_output  # noqa: F401

sys.path.insert(0, os.path.join(ROOT, "data_generator"))
sys.path.insert(0, os.path.join(ROOT, "web"))
import config as C          # noqa: E402
import db                   # noqa: E402

P = "全部"          # 全部周期口径

TABLE_N = [0]
FIG_N = [0]


def reset_counters():
    TABLE_N[0] = 0
    FIG_N[0] = 0


# ---------------------------------------------------------------------------
# 数据库读取
# ---------------------------------------------------------------------------
def q(sql, args=None):
    return db.query(sql, args)


def q1(sql, args=None):
    rows = db.query(sql, args)
    return rows[0] if rows else {}


def kpi():
    """总体 KPI（全部周期）。"""
    return q1("SELECT * FROM ads_overview_kpi WHERE stat_period=%s", (P,))


def mv(model, metric, default=0.0):
    """Spark MLlib 模型评估指标。"""
    rows = q("SELECT metric_value FROM ads_ml_metric WHERE model_name=%s AND metric_name=%s",
             (model, metric))
    return float(rows[0]["metric_value"]) if rows else default


def mv_params(model):
    rows = q("SELECT params FROM ads_ml_metric WHERE model_name=%s LIMIT 1", (model,))
    return rows[0]["params"] if rows else ""


def netv(name, default=0.0):
    """疾病共现网络整体指标。"""
    rows = q("SELECT metric_value FROM ads_network_metric WHERE metric_name=%s", (name,))
    return float(rows[0]["metric_value"]) if rows else default


# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------
def fmtd(v, nd=0):
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{int(round(f)):,}" if nd == 0 else f"{f:,.{nd}f}"


def wan(v, nd=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    if abs(f) >= 1e8:
        return f"{f/1e8:.{nd}f} 亿"
    if abs(f) >= 1e4:
        return f"{f/1e4:.{nd}f} 万"
    return f"{f:,.{nd}f}"


# ---------------------------------------------------------------------------
# 表格 / 插图（自动编号）
# ---------------------------------------------------------------------------
def tab(rep, title, headers, rows, widths=None, fs=9):
    TABLE_N[0] += 1
    rep.table(headers, rows, widths=widths, caption=f"表 {TABLE_N[0]}　{title}", font_size=fs)
    return TABLE_N[0]


def fig(rep, path, title, width=15.0):
    FIG_N[0] += 1
    rep.figure(img(path), f"图 {FIG_N[0]}　{title}", width_cm=width)
    return FIG_N[0]


def tabx(rep, title, headers, rows, widths=None, fs=9):
    """不带自动编号的表（用于跨报告引用同一编号体系时）。"""
    rep.table(headers, rows, widths=widths, caption=title, font_size=fs)


# ---------------------------------------------------------------------------
# 封面填写（统一：题目 + 学院，其余留空由学生手工填写）
# ---------------------------------------------------------------------------
def _fmt_cover_cell(cell, size_pt, font="黑体", bold=True, align="center"):
    """规范化封面上某个合并单元格里段落的字体与对齐（避免模板残留导致换行/错位）。"""
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    for par in cell.paragraphs:
        par.paragraph_format.first_line_indent = 0
        par.paragraph_format.left_indent = 0
        par.alignment = (WD_ALIGN_PARAGRAPH.CENTER if align == "center"
                         else WD_ALIGN_PARAGRAPH.LEFT)
        for r in par.runs:
            r.font.size = Pt(size_pt)
            r.font.bold = bold
            r.font.name = font
            rPr = r._element.get_or_add_rPr()
            rFonts = rPr.find(qn("w:rFonts"))
            if rFonts is None:
                rFonts = OxmlElement("w:rFonts")
                rPr.insert(0, rFonts)
            rFonts.set(qn("w:eastAsia"), font)


def fill_cover(rep, title):
    """填写封面。

    模板封面表（tables[0]）行含义：
      row1 = 课程名（大数据平台架构与应用开发课程设计报告）
      row2 = 项目题目（本课题）
      row3~7 = 学院 / 专业班级 / 学号 / 学生姓名 / 报告成绩
      row8 = 日期
    模板 row1 用 28pt 楷体，标题宽度 16.1cm 装不下 20 字，会被强制折行且第二行缩进错位；
    故统一压到 22pt 使其单行排布；row2 项目名用 18pt，层次清晰。
    """
    from docx.shared import Pt as _Pt
    t = rep.d.tables[0]
    # row1：课程名（模板已含文字，仅规范格式）
    _fmt_cover_cell(t.rows[1].cells[0], 22, font="黑体", bold=True)
    # row2：项目题目
    c2 = t.rows[2].cells[0]
    c2.text = title
    _fmt_cover_cell(c2, 18, font="黑体", bold=False)
    # 学院
    t.cell(3, 3).text = "人工智能与大数据学院"
    # 专业班级 / 学号 / 学生姓名 / 报告成绩 留空，由学生本人按课程要求手工填写
    t.cell(4, 3).text = ""
    t.cell(5, 3).text = ""
    t.cell(6, 3).text = ""
    t.cell(7, 3).text = ""


def clear_body_after_cover(rep):
    """删除封面表格之后的所有正文内容（保留母版封面与样式）。"""
    body = rep.d.element.body
    keep = rep.d.tables[0]._tbl
    for child in list(body):
        if child is keep or child.tag.endswith("}sectPr"):
            continue
        body.remove(child)


def build_skeleton(template_title):
    """创建 Report 实例、填封面、清空母版正文，返回 rep。"""
    rep = Report(TEMPLATE)
    fill_cover(rep, template_title)
    clear_body_after_cover(rep)
    return rep


def save_report(rep, filename):
    """保存到 report/ 目录并返回绝对路径。"""
    path = set_output(filename)
    abspath = os.path.abspath(path).replace("/", "\\")
    rep.d.save(abspath)
    return abspath
