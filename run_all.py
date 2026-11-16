# -*- coding: utf-8 -*-
"""
一键复现脚本 —— 医疗健康数据平台与疾病统计分析（单机全链路）
==================================================================
按顺序执行：
    1. 数据生成与脱敏              → output/ods/*.csv
    2. 本地数仓分层与统计计算      → output/dwd|dws|ads/*.csv
    3. ADS 结果与维度数据导入 MySQL → 库 med_health
    4. （可选）启动 Flask 可视化平台

用法：
    python run_all.py               # 执行 1~3 步
    python run_all.py --web         # 执行 1~3 步后启动 Web 平台
    python run_all.py --skip-gen    # 跳过数据生成（复用已有 ODS 数据）
    python run_all.py --realtime 6  # 额外运行 6 个实时窗口做演示（爬虫 --local 投递 + 本地窗口聚合）

集群模式：本脚本的第 1、3 步在集群环境下分别对应「数据上传 HDFS」与「Sqoop 导出」，
第 2 步对应「beeline 执行 Hive SQL + spark-submit 离线统计」，
详见 code/docs/集群部署文档.md 与 code/deploy/ 下的部署脚本。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def run(title, script, cwd, extra_env=None):
    print()
    print("=" * 74)
    print(f"  {title}")
    print("=" * 74)
    t0 = time.time()
    env = dict(os.environ)
    if extra_env:
        env.update(extra_env)
    p = subprocess.run([PY, script], cwd=cwd, env=env)
    if p.returncode != 0:
        print(f"[失败] {title}（退出码 {p.returncode}）")
        sys.exit(p.returncode)
    print(f"[完成] {title}  耗时 {time.time()-t0:.1f} 秒")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-gen", action="store_true", help="跳过数据生成步骤")
    ap.add_argument("--web", action="store_true", help="完成后启动 Flask 平台")
    ap.add_argument("--realtime", type=int, default=0, metavar="N",
                    help="运行 N 个实时窗口的演示数据（默认 0，不运行）")
    args = ap.parse_args()

    t0 = datetime.now()
    print("#" * 74)
    print("#  医疗健康数据平台与疾病统计分析 —— 单机全链路复现")
    print(f"#  开始时间：{t0:%Y-%m-%d %H:%M:%S}")
    print("#" * 74)

    if not args.skip_gen:
        run("步骤 1/3　模拟数据生成与脱敏",
            "gen_source_data.py", os.path.join(HERE, "data_generator"))
    else:
        print("\n（已跳过步骤 1：数据生成）")

    run("步骤 2/3　数仓分层与离线统计（DWD → DWS → ADS）",
        "etl_local.py", os.path.join(HERE, "local_engine"))

    run("步骤 3/3　ADS 结果导入 MySQL（库 med_health）",
        "load_mysql.py", os.path.join(HERE, "local_engine"))

    if args.realtime:
        print()
        print("=" * 74)
        print(f"  附加：实时链路演示（{args.realtime} 个窗口，爬虫抓取 CDC 公开公报）")
        print("=" * 74)
        rt = os.path.join(HERE, "realtime")
        env = dict(os.environ)
        # 实时数据源优先用爬虫（爬取中国疾控中心公开疫情公报）；
        # 网络不可达时自动退回模拟生产者 producer.py。
        crawler_ok = os.path.exists(os.path.join(rt, "crawler.py"))
        if crawler_ok:
            prod = subprocess.Popen([PY, "crawler.py", "--local", "--rate", "12"], cwd=rt, env=env)
        else:
            prod = subprocess.Popen([PY, "producer.py", "--local", "--rate", "12"], cwd=rt, env=env)
        try:
            subprocess.run([PY, "local_stream.py", "--window", "10",
                            "--max-windows", str(args.realtime)], cwd=rt, env=env)
        finally:
            prod.terminate()

    print()
    print("#" * 74)
    print(f"#  全链路完成，总耗时 {(datetime.now()-t0).total_seconds():.1f} 秒")
    print("#" * 74)

    if args.web:
        print("\n启动 Flask 可视化平台：http://127.0.0.1:5000")
        print("账号： admin/admin123　doctor/doctor123　viewer/viewer123\n")
        subprocess.run([PY, "app.py"], cwd=os.path.join(HERE, "web"))
    else:
        print("\n提示：执行 `python run_all.py --web` 可启动可视化平台；")
        print("      或先 `cd web && python app.py` 再访问 http://127.0.0.1:5000")


if __name__ == "__main__":
    main()
