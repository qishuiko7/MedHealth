# -*- coding: utf-8 -*-
"""
课程设计报告总生成入口
==================================================
流程：
    1. 以《课程设计报告——封面.docx》为母版，填写封面并清空母版正文
    2. 撰写第 1~4 章（绪论 / 相关技术 / 需求分析 / 总体设计）
    3. 撰写第 5~7 章（详细设计与实现 / 系统测试 / 总结与展望）
    4. 追加参考文献与附录
    5. 保存为 report/ 目录下的 docx

所有统计数据均从 MySQL 的 ADS 结果表读取，保证报告与系统运行结果一致。

运行： python gen_report.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_builder import OUT_DIR, OUT_DOCX
from gen_report_ch1_4 import build, TABLE_N, FIG_N
from gen_report_ch5_7 import ch5, ch6, ch7, refs, appendix


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 70)
    print("生成课程设计报告")
    print("=" * 70)

    print("[1/4] 封面 + 第 1~4 章 ...")
    rep = build()

    print("[2/4] 第 5 章（详细设计与系统实现）...")
    ch5(rep)

    print("[3/4] 第 6~7 章（系统测试 / 总结与展望）...")
    ch6(rep)
    ch7(rep)

    print("[4/4] 参考文献 + 附录 ...")
    refs(rep)
    appendix(rep)

    # 页脚页码
    try:
        rep.add_page_number_footer()
    except Exception as e:
        print(f"  （页脚添加失败，忽略：{e}）")

    path = os.path.abspath(OUT_DOCX).replace("/", "\\")
    rep.d.save(path)
    size_mb = os.path.getsize(path) / 1024 / 1024
    print("-" * 70)
    print(f"共生成 表 {TABLE_N[0]} 个、图 {FIG_N[0]} 张")
    print(f"输出：{path}  （{size_mb:.2f} MB）")


if __name__ == "__main__":
    main()
