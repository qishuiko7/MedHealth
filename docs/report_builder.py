# -*- coding: utf-8 -*-
"""
课程设计报告生成器
==================================================================
以《课程设计报告——封面.docx》为母版：
  1. 保留母版封面表格（学院 / 专业班级 / 学号 / 学生姓名 / 报告成绩）与全部样式
  2. 清空母版正文，重新撰写本项目正文
  3. 报告中的统计数据全部从 MySQL（med_health 库 ADS 结果表）实时读取，
     保证报告数字与系统运行结果完全一致，不存在手工抄录误差

运行： python gen_report.py
      python gen_report_frontend.py      # 前端同学报告
      python gen_report_backend.py       # 后端同学报告
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "data_generator"))
sys.path.insert(0, os.path.join(ROOT, "web"))

import config as C
import db

# ---------------------------------------------------------------------------
# 路径配置（全部相对工程目录，便于整体迁移到其他电脑）
#   · 封面母版优先使用工程内自带的副本 code/docs/templates/，
#     找不到时再回退到课程下发文件的默认位置
#   · 输出目录为工程根目录下的 report/
# ---------------------------------------------------------------------------
_DOCS_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATE_LOCAL = os.path.join(_DOCS_DIR, "templates", "课程设计报告——封面.docx")
_TEMPLATE_DOWNLOADS = os.path.expanduser(r"~\Downloads\课程设计报告——封面.docx")

TEMPLATE = _TEMPLATE_LOCAL if os.path.exists(_TEMPLATE_LOCAL) else _TEMPLATE_DOWNLOADS

PROJECT_DIR = os.path.dirname(ROOT)
OUT_DIR = os.path.join(PROJECT_DIR, "report")
# 默认输出（完整报告）；前端/后端报告由各自的生成脚本覆盖该值
OUT_DOCX = os.path.join(OUT_DIR, "医疗健康数据平台与疾病统计分析-课程设计报告.docx")
IMG = os.path.join(ROOT, "images")


def set_output(filename: str) -> str:
    """切换报告输出文件名（供前端 / 后端 / 完整 三份报告共用同一套生成器）。"""
    global OUT_DOCX
    OUT_DOCX = os.path.join(OUT_DIR, filename)
    return OUT_DOCX


# ===========================================================================
# 通用工具
# ===========================================================================
def img(name):
    return os.path.join(IMG, name)


def q(sql, args=None):
    try:
        return db.query(sql, args)
    except Exception as e:      # 数据库不可用时给出显式提示，避免报告出现空表
        raise RuntimeError(f"查询失败：{sql} -> {e}")


def q1(sql, args=None):
    r = q(sql, args)
    return r[0] if r else {}


def fmtd(v, nd=0):
    if v is None:
        return '—'
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if nd == 0:
        return f"{int(round(f)):,}"
    return f"{f:,.{nd}f}"


def wan(v, nd=2):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return '—'
    if abs(f) >= 1e8:
        return f"{f/1e8:.{nd}f} 亿"
    if abs(f) >= 1e4:
        return f"{f/1e4:.{nd}f} 万"
    return f"{f:,.{nd}f}"


class Report:
    def __init__(self, template):
        self.d = Document(template)
        self.body_style = self._find_body_style()
        self._ensure_heading3()
        self.tbl_no = {}
        self.fig_no = {}

    def _find_body_style(self):
        for s in self.d.styles:
            if s.name.startswith("样式 宋体"):
                return s.name
        return "Normal"

    def _ensure_heading3(self):
        names = {s.name for s in self.d.styles}
        if "Heading 3" not in names:
            st = self.d.styles.add_style("Heading 3", WD_STYLE_TYPE.PARAGRAPH)
            st.base_style = self.d.styles["Heading 2"]
            st.font.size = Pt(12)
            st.font.bold = True
            st.font.name = "黑体"
        try:
            self.d.styles["Heading 3"].font.name = "黑体"
            self.d.styles["Heading 3"].font.size = Pt(12)
        except Exception:
            pass

    # ---------------- 段落 ----------------
    def h1(self, text):
        p = self.d.add_paragraph(text, style="Heading 1")
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(8)
        return p

    def h2(self, text):
        p = self.d.add_paragraph(text, style="Heading 2")
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(6)
        return p

    def h3(self, text):
        p = self.d.add_paragraph(text, style="Heading 3")
        p.paragraph_format.space_before = Pt(8)
        p.paragraph_format.space_after = Pt(4)
        return p

    def _add_rich_runs(self, par, text, base_size=None, base_bold=False,
                       font="宋体", mono=None):
        """把含 **加粗** / `代码` 标记的文本拆成多个 run。

        · ``**文字**``  → 真正加粗（不打印星号）
        · ``` 代码 ```` → 若指定 mono 则用等宽字体，否则去掉反引号按正文排
        · 其余按普通文本
        避免把 Markdown 标记原样打进 Word。
        """
        import re as _re

        def _set(run, bold, use_mono=False):
            run.font.bold = bold
            if use_mono and mono:
                run.font.name = mono
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            else:
                run.font.name = font
                run._element.rPr.rFonts.set(qn("w:eastAsia"), font)
            if base_size:
                run.font.size = Pt(base_size)

        for seg in _re.split(r"(\*\*.+?\*\*)", text):
            if not seg:
                continue
            if seg.startswith("**") and seg.endswith("**") and len(seg) >= 4:
                _set(par.add_run(seg[2:-2]), True)
                continue
            for ps in _re.split(r"(`[^`]+`)", seg):
                if not ps:
                    continue
                if ps.startswith("`") and ps.endswith("`") and len(ps) >= 2:
                    _set(par.add_run(ps[1:-1]), base_bold, use_mono=True)
                else:
                    _set(par.add_run(ps), base_bold)

    def p(self, text, indent=True, align=None, size=None, bold=False):
        par = self.d.add_paragraph(style=self.body_style if indent else None)
        if not indent:
            par.style = self.d.styles["Normal"]
        self._add_rich_runs(par, text, base_size=size, base_bold=bold, font="宋体")
        par.paragraph_format.line_spacing = 1.5
        par.paragraph_format.space_after = Pt(0)
        if align == "center":
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "right":
            par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        return par

    def bullet(self, text, size=10.5):
        par = self.d.add_paragraph()
        self._add_rich_runs(par, text, base_size=size, base_bold=False, font="宋体")
        par.paragraph_format.left_indent = Cm(0.9)
        par.paragraph_format.line_spacing = 1.5
        par.paragraph_format.space_after = Pt(0)
        return par

    def code(self, text):
        par = self.d.add_paragraph()
        run = par.add_run(text)
        run.font.name = "Consolas"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        run.font.size = Pt(9)
        par.paragraph_format.line_spacing = 1.15
        par.paragraph_format.left_indent = Cm(0.6)
        par.paragraph_format.space_after = Pt(0)
        pf = par.paragraph_format.element.get_or_add_pPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:fill"), "F4F6F9")
        pf.append(shd)
        return par

    def title_center(self, text, size=16, space_before=0, space_after=12):
        par = self.d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = par.add_run(text)
        run.font.name = "黑体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体")
        run.font.size = Pt(size)
        run.font.bold = True
        par.paragraph_format.space_before = Pt(space_before)
        par.paragraph_format.space_after = Pt(space_after)
        return par

    # ---------------- 表格 ----------------
    def caption(self, text):
        par = self.d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = par.add_run(text)
        run.font.name = "宋体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        run.font.size = Pt(10.5)
        run.font.bold = True
        par.paragraph_format.space_before = Pt(6)
        par.paragraph_format.space_after = Pt(2)
        return par

    def table(self, headers, rows, widths=None, caption=None, font_size=9):
        if caption:
            self.caption(caption)
        t = self.d.add_table(rows=1, cols=len(headers))
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        hdr = t.rows[0].cells
        for i, h in enumerate(headers):
            hdr[i].text = ""
            par = hdr[i].paragraphs[0]
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = par.add_run(str(h))
            run.font.bold = True
            run.font.size = Pt(font_size)
            run.font.name = "宋体"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
            self._shade(hdr[i], "EAF1FB")
        for r in rows:
            cells = t.add_row().cells
            for i, v in enumerate(r):
                cells[i].text = ""
                par = cells[i].paragraphs[0]
                par.paragraph_format.space_after = Pt(0)
                run = par.add_run("" if v is None else str(v).replace("**", ""))
                run.font.size = Pt(font_size)
                run.font.name = "宋体"
                run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
                if i > 0 and self._is_num(v):
                    par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if widths:
            for row in t.rows:
                for i, w in enumerate(widths):
                    row.cells[i].width = Cm(w)
        self.d.add_paragraph().paragraph_format.space_after = Pt(2)
        return t

    @staticmethod
    def _is_num(v):
        try:
            float(str(v).replace(",", ""))
            return True
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _shade(cell, color):
        tcPr = cell._tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear"); shd.set(qn("w:color"), "auto"); shd.set(qn("w:fill"), color)
        tcPr.append(shd)

    # ---------------- 图片 ----------------
    def figure(self, path, caption, width_cm=15.0):
        if not os.path.exists(path):
            self.p(f"【插图缺失：{os.path.basename(path)}】", align="center")
            return
        par = self.d.add_paragraph()
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        par.paragraph_format.space_before = Pt(6)
        par.paragraph_format.space_after = Pt(2)
        par.add_run().add_picture(path, width=Cm(width_cm))
        cp = self.d.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = cp.add_run(caption)
        run.font.size = Pt(10.5)
        run.font.bold = True
        run.font.name = "宋体"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
        cp.paragraph_format.space_after = Pt(10)

    def page_break(self):
        self.d.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    def toc(self):
        """插入目录占位段落。真正的目录条目在正文写完后由 build_static_toc() 生成。

        这里刻意不使用 Word 的 TOC 域：域结果在 Word 里会带灰色底纹（域底纹），
        且需要用户手动按 F9 更新。改为生成静态目录条目（带点线前导符与页码占位），
        打开即成型、无底纹、无需更新。
        """
        par = self.d.add_paragraph()
        par._p.set(qn("w:rsidR"), "00TOCPLACEHOLDER")
        self._toc_placeholder = par
        # 占位内容（build_static_toc 会整体替换）
        run = par.add_run("__TOC_PLACEHOLDER__")
        run.font.size = Pt(10.5)
        return par

    def build_static_toc(self):
        """扫描全文 Heading 1~3，生成静态目录条目，替换占位段落。

        页码无法在纯 docx 生成阶段可靠计算，因此目录条目右端保留「点线前导符」，
        页码由 Word 打开后按 F9 刷新页码域不适用；这里改为不显示页码的规范目录
        （符合课程设计「目录列出章节」的要求，且不会出现灰色底纹或待更新提示）。
        """
        placeholder = getattr(self, "_toc_placeholder", None)
        if placeholder is None:
            return
        # 收集标题
        entries = []
        for p in self.d.paragraphs:
            sty = p.style.name
            if sty == "Heading 1":
                entries.append((1, p.text.strip()))
            elif sty == "Heading 2":
                entries.append((2, p.text.strip()))
            elif sty == "Heading 3":
                entries.append((3, p.text.strip()))
        # 在占位段之前的位置，插入目录条目段
        anchor = placeholder._p
        for level, text in entries:
            newp = self.d.add_paragraph()
            pf = newp.paragraph_format
            pf.line_spacing = 1.5
            pf.space_after = Pt(0)
            pf.space_before = Pt(4 if level == 1 else 0)
            if level == 1:
                pf.left_indent = Cm(0)
                size = 13
                bold = True
            elif level == 2:
                pf.left_indent = Cm(0.74)
                size = 12
                bold = False
            else:
                pf.left_indent = Cm(1.48)
                size = 10.5
                bold = False
            run = newp.add_run(text)
            run.font.name = "黑体" if level == 1 else "宋体"
            run._element.rPr.rFonts.set(qn("w:eastAsia"), "黑体" if level == 1 else "宋体")
            run.font.size = Pt(size)
            run.font.bold = bold
            # 移到占位段之前
            anchor.addprevious(newp._p)
        # 删除占位段
        anchor.getparent().remove(anchor)
        self._toc_placeholder = None

    def add_page_number_footer(self):
        sec = self.d.sections[-1]
        footer = sec.footer
        par = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        par.text = ""
        par.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = par.add_run()
        b = OxmlElement("w:fldChar"); b.set(qn("w:fldCharType"), "begin")
        i = OxmlElement("w:instrText"); i.set(qn("xml:space"), "preserve"); i.text = "PAGE"
        e = OxmlElement("w:fldChar"); e.set(qn("w:fldCharType"), "end")
        for x in (b, i, e):
            run._r.append(x)
        run.font.size = Pt(9)
