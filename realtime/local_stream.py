# -*- coding: utf-8 -*-
"""
本地实时流处理引擎（无 Kafka / Spark 环境的等价实现）
==================================================================
作用：在没有部署 Kafka + Spark 的 Windows 单机上，完整演示实时链路的
      「事件生产 → 窗口聚合 → 结果落 MySQL」，供平台「实时数据监控」页面展示。

与集群模式的对应关系：
    Kafka 主题 med_visit          ←→  本地 stream_events.jsonl（生产者写入）
    Spark Streaming 60s 滚动窗口  ←→  本脚本按 window 秒切分窗口
    foreachBatch 写 MySQL         ←→  本脚本按窗口 INSERT 到 rt_visit_stat / rt_kpi
    字段、表结构、口径与集群模式完全一致，可横向对照。

运行：
    python local_stream.py --window 10 --idle-exit 0
    （--idle-exit 0 表示无新数据时也不退出，持续等待生产者）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))
import config as C
import pymysql

STREAM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stream_events.jsonl")


def conn():
    return pymysql.connect(host=C.MYSQL["host"], port=C.MYSQL["port"], user=C.MYSQL["user"],
                           password=C.MYSQL["password"], database=C.MYSQL["database"],
                           charset="utf8mb4", autocommit=True)


def read_new(fp, pos):
    """从 pos 起读取新增行。"""
    if not os.path.exists(STREAM_FILE):
        return [], pos
    size = os.path.getsize(STREAM_FILE)
    if size < pos:      # 文件被重建
        pos = 0
    if size == pos:
        return [], pos
    with open(STREAM_FILE, "r", encoding="utf-8") as f:
        f.seek(pos)
        lines = f.readlines()
        pos = f.tell()
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out, pos


def flush_window(c, ws, we, buf, total_events, window_seconds):
    if not buf:
        return 0
    by_dept = defaultdict(lambda: [0, 0.0, 0, 0, set()])
    crawler = {}          # (period, disease) -> (case_cnt, death_cnt)
    for ev in buf:
        d = ev.get("dept_name") or "未知科室"
        by_dept[d][0] += 1
        by_dept[d][1] += float(ev.get("presc_amount") or 0)
        cs, ds = int(ev.get("case_cnt") or 0), int(ev.get("death_cnt") or 0)
        if cs > 0 or ds > 0:
            key = (ev.get("period") or "", ev.get("diagnosis_name") or d)
            if key not in by_dept[d][4]:     # 同一病种在窗口内只计一次
                by_dept[d][4].add(key)
                by_dept[d][2] += cs
                by_dept[d][3] += ds
            crawler[key] = (cs, ds)          # 取窗口内最大值即可（公报为定值）
    we_s = we.strftime("%Y-%m-%d %H:%M:%S")
    ws_s = ws.strftime("%Y-%m-%d %H:%M:%S")
    rows = [(ws_s, we_s, d, v[0], v[2], v[3], round(v[1], 2)) for d, v in by_dept.items()]
    cur = c.cursor()
    cur.execute("DELETE FROM rt_visit_stat WHERE window_end = %s", (we_s,))
    cur.executemany(
        "INSERT INTO rt_visit_stat"
        "(window_start, window_end, dept_name, visit_cnt, case_cnt, death_cnt, presc_amount, update_time) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())", rows)
    total_visit = sum(r[3] for r in rows)
    total_amount = round(sum(r[6] for r in rows), 2)
    top = max(by_dept.items(), key=lambda x: x[1][0])[0] if by_dept else None
    cur.execute(
        "INSERT INTO rt_kpi(window_end, reg_cnt, visit_cnt, presc_amount, top_dept, msg_per_sec, update_time) "
        "VALUES (%s,%s,%s,%s,%s,%s,NOW())",
        (we_s, total_visit, total_visit, total_amount, top,
         round(total_visit / max(window_seconds, 1), 2)))
    # 爬虫病种明细
    if crawler:
        cur.execute("DELETE FROM rt_crawler_stat WHERE window_end = %s", (we_s,))
        cur.executemany(
            "INSERT INTO rt_crawler_stat"
            "(window_end, period, disease_name, case_cnt, death_cnt, source, source_url, update_time) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())",
            [(we_s, p, dn, cs, ds, "CDC-crawler", "") for (p, dn), (cs, ds) in crawler.items()])
    cur.close()
    print(f"[窗口 {ws:%H:%M:%S} ~ {we:%H:%M:%S}] 科室 {len(rows)} 个，就诊 {total_visit} 人次，"
          f"处方金额 {total_amount:.2f} 元，最忙科室 {top}，爬虫病种 {len(crawler)} 个", flush=True)
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=10, help="窗口长度（秒），集群默认 60s")
    ap.add_argument("--idle-exit", type=int, default=0, help="连续无数据的窗口数达到该值则退出，0 表示不退出")
    ap.add_argument("--max-windows", type=int, default=0, help="最多处理窗口数，0 表示不限")
    args = ap.parse_args()

    c = conn()
    cur = c.cursor()
    cur.execute("DELETE FROM rt_visit_stat")
    cur.execute("DELETE FROM rt_kpi")
    cur.execute("DELETE FROM rt_crawler_stat")
    cur.close()

    print("=" * 70)
    print(f"本地实时流引擎启动：窗口 {args.window}s，监听 {STREAM_FILE}")
    print("提示：另开一个终端运行 python crawler.py --local --rate 15 抓取 CDC 公报生成实时事件")
    print("=" * 70)

    pos = 0
    if os.path.exists(STREAM_FILE):
        pos = os.path.getsize(STREAM_FILE)      # 从文件末尾开始，只处理启动后新增的数据
    buf = []
    total_events = 0
    windows = 0
    idle = 0
    ws = datetime.now()

    try:
        while True:
            time.sleep(1)
            events, pos = read_new(pos, pos)
            if events:
                buf.extend(events)
                total_events += len(events)
                idle = 0
            now = datetime.now()
            if (now - ws).total_seconds() >= args.window:
                we = now
                n = flush_window(c, ws, we, buf, total_events, args.window)
                windows += 1
                buf = []
                ws = we
                if n == 0:
                    idle += 1
                    if args.idle_exit and idle >= args.idle_exit:
                        print(f"[引擎] 连续 {idle} 个窗口无数据，退出。累计处理 {total_events:,} 条事件")
                        break
                if args.max_windows and windows >= args.max_windows:
                    print(f"[引擎] 已达最大窗口数 {args.max_windows}，退出。累计处理 {total_events:,} 条事件")
                    break
    except KeyboardInterrupt:
        print("\n[引擎] 手动停止")
    finally:
        c.close()


if __name__ == "__main__":
    main()
