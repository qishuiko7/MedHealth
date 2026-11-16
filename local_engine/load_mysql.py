# -*- coding: utf-8 -*-
"""
将 ADS 结果与维度数据导入 MySQL
==================================================================
对应《项目操作流程》第 13 步：
    「将 hive 处理好的离线数据导入 Windows 的 MySQL 中存储」

集群环境下这一步通常由 Sqoop 完成：
    sqoop export --connect jdbc:mysql://<win-ip>:3306/med_health \
        --username root --password *** --table ads_disease_distribution \
        --export-dir /user/hive/warehouse/med_health.db/ads_disease_distribution \
        --input-fields-terminated-by '\001'

本脚本是 Windows 单机环境下的等价实现：直接读取 ADS 层 CSV 后批量写入 MySQL，
字段映射与 Sqoop 导出一致。

运行：
  python load_mysql.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))
import config as C
import desensitize as DS
import pymysql

SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "warehouse", "mysql", "schema.sql")


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def connect(with_db=True):
    kw = dict(host=C.MYSQL["host"], port=C.MYSQL["port"], user=C.MYSQL["user"],
              password=C.MYSQL["password"], charset=C.MYSQL["charset"])
    if with_db:
        kw["database"] = C.MYSQL["database"]
    return pymysql.connect(**kw)


def run_schema():
    """执行建库建表脚本。

    说明：这里不用 mysql 客户端的 `source` 命令（路径含中文时在 Windows 下易失败），
    而是由 Python 读取 SQL 后逐条执行，既能保证 DDL 与文档完全一致，又不受路径编码影响。
    """
    with open(SCHEMA, encoding="utf-8") as f:
        content = f.read()
    # 去掉整行注释
    lines = [ln for ln in content.splitlines() if not ln.strip().startswith("--")]
    statements = [s.strip() for s in "\n".join(lines).split(";") if s.strip()]
    conn = connect(with_db=False)
    cur = conn.cursor()
    try:
        for s in statements:
            cur.execute(s)
        conn.commit()
    finally:
        cur.close()
        conn.close()
    log(f"schema.sql 执行完成（{len(statements)} 条语句）")


def load_table(conn, table, csv_path, columns=None, chunk=5000):
    if not os.path.exists(csv_path):
        log(f"  跳过（文件不存在）：{csv_path}")
        return 0
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if columns:
        df = df[[c for c in columns if c in df.columns]]
    df = df.where(pd.notna(df), None)
    cols = list(df.columns)
    ph = ",".join(["%s"] * len(cols))
    sql = f"INSERT INTO {table} ({','.join('`'+c+'`' for c in cols)}) VALUES ({ph})"
    total = 0
    cur = conn.cursor()
    try:
        cur.execute(f"SET FOREIGN_KEY_CHECKS=0")
        for i in range(0, len(df), chunk):
            part = df.iloc[i:i + chunk]
            args = [tuple(None if v == "" else v for v in row) for row in part.itertuples(index=False, name=None)]
            cur.executemany(sql, args)
            conn.commit()
            total += len(args)
    finally:
        cur.close()
    log(f"  {table:<28} {total:>9,} 行")
    return total


def main():
    t0 = datetime.now()
    log("=" * 70)
    log("ADS / 维度数据导入 MySQL")
    log("=" * 70)

    log("重建库表 ...")
    run_schema()

    conn = connect()
    try:
        log("导入维度表 ...")
        load_table(conn, "dim_department", os.path.join(C.ODS_DIR, "ods_department.csv"),
                   ["dept_id", "dept_code", "dept_name", "dept_type", "dept_type_name", "is_inpatient"])
        load_table(conn, "dim_doctor", os.path.join(C.ODS_DIR, "ods_doctor.csv"),
                   ["doctor_id", "doctor_no", "doctor_name", "dept_id", "title", "reg_fee", "hire_date"])
        load_table(conn, "dim_drug", os.path.join(C.ODS_DIR, "ods_drug.csv"),
                   ["drug_id", "drug_code", "drug_name", "drug_type", "spec", "unit",
                    "unit_price", "manufacturer", "is_insurance"])
        load_table(conn, "dim_disease", os.path.join(C.ODS_DIR, "ods_disease.csv"),
                   ["disease_id", "diagnosis_code", "diagnosis_name", "disease_category",
                    "is_infectious", "severity", "is_chronic"])

        log("导入 ADS 结果表 ...")
        for t in ["ads_overview_kpi", "ads_disease_distribution", "ads_visit_peak",
                  "ads_dept_workload", "ads_drug_consumption", "ads_los_analysis",
                  "ads_infectious_monitor"]:
            load_table(conn, t, os.path.join(C.ADS_DIR, f"{t}.csv"))

        log("导入脱敏规则说明 ...")
        cur = conn.cursor()
        cur.execute("TRUNCATE TABLE desensitize_rule")
        cur.executemany(
            "INSERT INTO desensitize_rule (field_name, rule_type, method_desc, example_raw, example_masked, principle, reversible)"
            " VALUES (%s,%s,%s,%s,%s,%s,%s)",
            [(r["field"], r["type"], r["method"], r["example_raw"], r["example_masked"],
              r["principle"], r["reversible"]) for r in DS.DESENSITIZE_RULES])
        conn.commit()
        log(f"  desensitize_rule             {len(DS.DESENSITIZE_RULES):>9,} 行")

        log("导入平台账号 ...")
        cur.execute("TRUNCATE TABLE sys_user")
        cur.executemany("INSERT INTO sys_user (username, password, display, role) VALUES (%s,%s,%s,%s)",
                        [(u, v["password"], v["display"], v["role"]) for u, v in C.USERS.items()])
        conn.commit()
        log(f"  sys_user                     {len(C.USERS):>9,} 行")
        cur.close()
    finally:
        conn.close()

    # ---- 校验 ----
    log("校验各表行数 ...")
    conn = connect()
    cur = conn.cursor()
    for t in ["dim_department", "dim_doctor", "dim_drug", "dim_disease", "ads_overview_kpi",
              "ads_disease_distribution", "ads_visit_peak", "ads_dept_workload",
              "ads_drug_consumption", "ads_los_analysis", "ads_infectious_monitor",
              "desensitize_rule", "sys_user"]:
        cur.execute(f"SELECT COUNT(1) FROM {t}")
        log(f"  {t:<28}{cur.fetchone()[0]:>10,}")
    cur.execute("SELECT stat_period, reg_cnt, visit_cnt, avg_los_days, infectious_rate "
                "FROM ads_overview_kpi WHERE stat_period='全部'")
    log(f"  全部期KPI：{cur.fetchone()}")
    cur.close()
    conn.close()

    log("-" * 70)
    log(f"完成，耗时 {(datetime.now()-t0).total_seconds():.1f} 秒")


if __name__ == "__main__":
    main()
