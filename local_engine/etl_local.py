# -*- coding: utf-8 -*-
"""
本地离线计算引擎（ODS -> DWD -> DWS -> ADS）
==================================================================
本模块是 `code/warehouse/hive/*.sql` 的**本地等价实现**。

为什么需要它：
  集群（Hadoop + Hive + Spark）是本课程设计的标准生产环境，但课程答辩演示
  通常在一台 Windows 机器上完成。为了让整条链路「在单机上可复现、可演示」，
  这里用 pandas 把 Hive SQL 的四层加工逻辑 1:1 复现一遍，产出**同名、同结构、
  同口径**的 DWD / DWS / ADS 结果表，再统一导入 MySQL 供 Flask 读取。

一致性保证：
  - 表名、字段名、字段顺序与 Hive DDL 完全一致
  - 口径一致：如「挂号量」仅统计 status='已就诊'、「就诊量」仅统计诊断非空、
    「平均住院日」= 住院天数合计 / 住院人次、「感染性疾病占比」= 感染就诊人次 / 就诊人次
  - 便于交叉验证：在集群上跑完 Hive 后，可用同一套 SQL 抽样比对（见 docs 校验章节）

运行：
  python etl_local.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))
import config as C


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def read(name):
    return pd.read_csv(os.path.join(C.ODS_DIR, name), dtype=str, keep_default_na=False)


def num(s, dtype="float"):
    return pd.to_numeric(s, errors="coerce").fillna(0).astype(dtype)


# ===========================================================================
# DIM / DWD
# ===========================================================================
def build_dim_date():
    dates = pd.date_range("2025-01-01", "2026-12-31", freq="D")
    d = pd.DataFrame({"dt": dates.strftime("%Y-%m-%d")})
    d["year"] = dates.year
    d["quarter"] = dates.quarter
    d["month"] = dates.month
    d["day"] = dates.day
    d["weekday"] = dates.weekday + 1           # 1=周一 ... 7=周日
    d["weekday_cn"] = "星期" + pd.Series(d["weekday"]).map(
        {1: "一", 2: "二", 3: "三", 4: "四", 5: "五", 6: "六", 7: "日"}).values
    d["is_weekend"] = (d["weekday"] >= 6).astype(int)
    d["season"] = d["month"].map(lambda m: "春" if m in (3, 4, 5) else
                                 "夏" if m in (6, 7, 8) else "秋" if m in (9, 10, 11) else "冬")
    return d


def build_dwd():
    dept = read("ods_department.csv")
    doctor = read("ods_doctor.csv")
    patient = read("ods_patient.csv")
    disease = read("ods_disease.csv")
    drug = read("ods_drug.csv")
    reg = read("ods_registration.csv")
    visit = read("ods_visit.csv")
    presc = read("ods_prescription.csv")
    adm = read("ods_admission.csv")

    for df, cols in ((dept, ["dept_id"]), (doctor, ["doctor_id", "dept_id"]),
                     (patient, ["patient_id"]), (disease, ["disease_id"]),
                     (drug, ["drug_id"]), (reg, ["reg_id", "patient_id", "dept_id", "doctor_id"]),
                     (visit, ["visit_id", "reg_id", "patient_id", "dept_id", "doctor_id", "diagnosis_id"]),
                     (presc, ["presc_id", "visit_id", "drug_id"]),
                     (adm, ["adm_id", "patient_id", "dept_id", "doctor_id", "diagnosis_id"])):
        for c in cols:
            df[c] = num(df[c], "int64")

    dept_np = dept.set_index("dept_id")
    pat_np = patient.set_index("patient_id")
    dis_np = disease.set_index("disease_id")
    dr_np = doctor.set_index("doctor_id")
    drug_np = drug.set_index("drug_id")

    # ---------------- DWD-1 挂号明细 ----------------
    r = reg[reg["status"] == "已就诊"].copy()
    r["patient_no"] = r["patient_id"].map(pat_np["patient_no"])
    r["gender"] = r["patient_id"].map(pat_np["gender"])
    r["age"] = r["patient_id"].map(pat_np["age"])
    r["age_group"] = r["patient_id"].map(pat_np["age_group"])
    r["insurance_type"] = r["patient_id"].map(pat_np["insurance_type"])
    r["dept_name"] = r["dept_id"].map(dept_np["dept_name"])
    r["dept_type_name"] = r["dept_id"].map(dept_np["dept_type_name"])
    r["doctor_name"] = r["doctor_id"].map(dr_np["doctor_name"])
    r["doctor_title"] = r["doctor_id"].map(dr_np["title"])
    r["reg_hour"] = r["reg_hour"].astype(int)
    r["reg_period"] = np.select([r["reg_hour"].between(6, 11), r["reg_hour"].between(12, 17)],
                                ["上午", "下午"], default="夜间")
    r["reg_fee"] = num(r["reg_fee"])
    r["is_visited"] = num(r["is_visited"], "int64")
    r["reg_time"] = r["reg_time"].astype(str).str.replace("T", " ")
    dwd_reg = r[["reg_id", "reg_no", "patient_id", "patient_no", "gender", "age", "age_group",
                 "insurance_type", "dept_id", "dept_name", "dept_type_name", "doctor_id",
                 "doctor_name", "doctor_title", "reg_time", "reg_hour", "reg_period", "reg_type",
                 "channel", "reg_fee", "status", "is_visited", "reg_date"]].rename(
        columns={"reg_date": "dt"}).reset_index(drop=True)

    # ---------------- DWD-2 就诊明细 ----------------
    v = visit[visit["diagnosis_code"].astype(str).str.strip() != ""].copy()
    v["gender"] = v["patient_id"].map(pat_np["gender"])
    v["age"] = v["patient_id"].map(pat_np["age"])
    v["age_group"] = v["patient_id"].map(pat_np["age_group"])
    v["insurance_type"] = v["patient_id"].map(pat_np["insurance_type"])
    v["dept_name"] = v["dept_id"].map(dept_np["dept_name"])
    v["doctor_name"] = v["doctor_id"].map(dr_np["doctor_name"])
    v["visit_hour"] = v["visit_hour"].astype(int)
    v["visit_period"] = np.select([v["visit_hour"].between(6, 11), v["visit_hour"].between(12, 17)],
                                  ["上午", "下午"], default="夜间")
    v["severity"] = num(v["diagnosis_id"].map(dis_np["severity"]), "int64")
    v["is_chronic"] = num(v["diagnosis_id"].map(dis_np["is_chronic"]), "int64")
    v["is_infectious"] = num(v["is_infectious"], "int64")
    v["visit_time"] = v["visit_time"].astype(str).str.replace("T", " ")
    dwd_visit = v[["visit_id", "reg_id", "patient_id", "gender", "age", "age_group", "insurance_type",
                   "dept_id", "dept_name", "doctor_id", "doctor_name", "visit_time", "visit_hour",
                   "visit_period", "visit_type", "diagnosis_code", "diagnosis_name", "disease_category",
                   "severity", "is_infectious", "is_chronic", "chief_complaint", "visit_date"]].rename(
        columns={"visit_date": "dt"}).reset_index(drop=True)

    # ---------------- DWD-3 处方明细 ----------------
    p = presc.copy()
    p["quantity"] = num(p["quantity"], "int64")
    p["unit_price"] = num(p["unit_price"])
    p["amount"] = num(p["amount"])
    p = p[(p["quantity"] > 0) & (p["amount"] > 0)].copy()
    vmap = v.set_index("visit_id")
    p["patient_id"] = p["visit_id"].map(vmap["patient_id"])
    p["dept_id"] = p["visit_id"].map(vmap["dept_id"])
    p["dept_name"] = p["dept_id"].map(dept_np["dept_name"])
    p["drug_name"] = p["drug_id"].map(drug_np["drug_name"])
    p["drug_type"] = p["drug_id"].map(drug_np["drug_type"])
    p["spec"] = p["drug_id"].map(drug_np["spec"])
    p["unit"] = p["drug_id"].map(drug_np["unit"])
    p["is_insurance"] = num(p["is_insurance"], "int64")
    p["visit_date"] = p["visit_id"].map(vmap["visit_date"])
    dwd_presc = p[["presc_id", "visit_id", "patient_id", "dept_id", "dept_name", "drug_id",
                   "drug_name", "drug_type", "spec", "unit", "quantity", "unit_price", "amount",
                   "usage_desc", "is_insurance", "visit_date"]].rename(
        columns={"visit_date": "dt"}).reset_index(drop=True)

    # ---------------- DWD-4 住院明细 ----------------
    a = adm[num(adm["los_days"], "int64") > 0].copy()
    a["los_days"] = num(a["los_days"], "int64")
    a["total_cost"] = num(a["total_cost"])
    a["gender"] = a["patient_id"].map(pat_np["gender"])
    a["age"] = a["patient_id"].map(pat_np["age"])
    a["age_group"] = a["patient_id"].map(pat_np["age_group"])
    a["insurance_type"] = a["patient_id"].map(pat_np["insurance_type"])
    a["dept_name"] = a["dept_id"].map(dept_np["dept_name"])
    a["doctor_name"] = a["doctor_id"].map(dr_np["doctor_name"])
    a["diagnosis_code"] = a["diagnosis_id"].map(dis_np["diagnosis_code"])
    a["diagnosis_name"] = a["diagnosis_id"].map(dis_np["diagnosis_name"])
    a["disease_category"] = a["diagnosis_id"].map(dis_np["disease_category"])
    a["los_level"] = pd.cut(a["los_days"], bins=[0, 3, 7, 14, 30, 10 ** 6],
                            labels=["1-3天", "4-7天", "8-14天", "15-30天", "30天以上"]).astype(str)
    a["day_avg_cost"] = (a["total_cost"] / a["los_days"]).round(2)
    a["admit_time"] = a["admit_time"].astype(str).str.replace("T", " ")
    a["discharge_time"] = a["discharge_time"].astype(str).str.replace("T", " ")
    a["dt"] = a["admit_time"].str[:10]
    dwd_adm = a[["adm_id", "adm_no", "patient_id", "gender", "age", "age_group", "insurance_type",
                 "dept_id", "dept_name", "doctor_id", "doctor_name", "diagnosis_code", "diagnosis_name",
                 "disease_category", "admit_time", "discharge_time", "los_days", "los_level",
                 "total_cost", "day_avg_cost", "outcome", "admit_type", "dt"]].reset_index(drop=True)

    # 全部挂号（含取消 / 爽约），供 ADS 层计算挂号就诊转化率
    reg_all = reg[["reg_id", "reg_time"]].copy()
    reg_all["dt"] = reg_all["reg_time"].astype(str).str.replace("T", " ").str[:10]

    return dwd_reg, dwd_visit, dwd_presc, dwd_adm, reg_all


# ===========================================================================
# DWS
# ===========================================================================
def build_dws(dwd_reg, dwd_visit, dwd_presc, dwd_adm):
    dept_dim = read("ods_department.csv")
    dept_dim["dept_id"] = num(dept_dim["dept_id"], "int64")
    type_map = dept_dim.set_index("dept_id")["dept_type_name"]

    # DWS-1 科室工作量
    g_reg = dwd_reg.groupby(["dt", "dept_id", "dept_name", "dept_type_name"], as_index=False).agg(
        reg_cnt=("reg_id", "count"), reg_fee_sum=("reg_fee", "sum"))
    g_visit = dwd_visit.groupby(["dt", "dept_id", "dept_name"], as_index=False).agg(
        visit_cnt=("visit_id", "count"))
    g_presc = dwd_presc.groupby(["dt", "dept_id", "dept_name"], as_index=False).agg(
        presc_amount=("amount", "sum"), drug_qty=("quantity", "sum"))
    g_adm = dwd_adm.groupby(["dt", "dept_id", "dept_name"], as_index=False).agg(
        admission_cnt=("adm_id", "count"), los_sum=("los_days", "sum"), los_cost_sum=("total_cost", "sum"))

    # 以「dt + 科室」为主体键取并集，再统一补科室类型，避免同一科室出现多行
    keys = pd.concat([g_reg[["dt", "dept_id", "dept_name"]],
                      g_visit[["dt", "dept_id", "dept_name"]],
                      g_presc[["dt", "dept_id", "dept_name"]],
                      g_adm[["dt", "dept_id", "dept_name"]]], ignore_index=True).drop_duplicates()
    base = keys.copy()
    dws_dept = base.merge(g_reg[["dt", "dept_id", "reg_cnt", "reg_fee_sum"]],
                          on=["dt", "dept_id"], how="left") \
        .merge(g_visit[["dt", "dept_id", "visit_cnt"]], on=["dt", "dept_id"], how="left") \
        .merge(g_presc[["dt", "dept_id", "presc_amount", "drug_qty"]], on=["dt", "dept_id"], how="left") \
        .merge(g_adm[["dt", "dept_id", "admission_cnt", "los_sum", "los_cost_sum"]], on=["dt", "dept_id"], how="left")
    dws_dept["dept_type_name"] = dws_dept["dept_id"].map(type_map).fillna("门诊科室")
    for c in ["reg_cnt", "visit_cnt", "admission_cnt", "drug_qty"]:
        dws_dept[c] = dws_dept[c].fillna(0).astype("int64")
    for c in ["reg_fee_sum", "presc_amount", "los_sum", "los_cost_sum"]:
        dws_dept[c] = dws_dept[c].fillna(0).round(2)
    dws_dept["stat_month"] = dws_dept["dt"].str[:7]
    dws_dept = dws_dept[["dt", "dept_id", "dept_name", "dept_type_name", "reg_cnt", "visit_cnt",
                         "reg_fee_sum", "presc_amount", "drug_qty", "admission_cnt", "los_sum",
                         "los_cost_sum", "stat_month"]]

    # DWS-2 就诊时段
    dd = build_dim_date()
    dws_time = dwd_visit.groupby(["dt", "visit_hour"], as_index=False).agg(
        visit_cnt=("visit_id", "count"), visit_period=("visit_period", "first"))
    dws_time = dws_time.merge(dd[["dt", "weekday", "weekday_cn", "is_weekend"]], on="dt", how="left")
    dws_time["stat_month"] = dws_time["dt"].str[:7]
    dws_time = dws_time[["dt", "visit_hour", "visit_period", "weekday", "weekday_cn",
                         "is_weekend", "visit_cnt", "stat_month"]]

    # DWS-3 疾病分布
    by_cat = dwd_visit.groupby(["dt", "disease_category"], as_index=False).agg(
        visit_cnt=("visit_id", "count"), is_infectious=("is_infectious", "max"))
    by_cat["dim_type"], by_cat["dim_value"] = "类别", by_cat["disease_category"]
    by_dis = dwd_visit.groupby(["dt", "diagnosis_name", "disease_category"], as_index=False).agg(
        visit_cnt=("visit_id", "count"), is_infectious=("is_infectious", "max"))
    by_dis["dim_type"], by_dis["dim_value"] = "疾病", by_dis["diagnosis_name"]
    cols = ["dt", "dim_type", "dim_value", "disease_category", "is_infectious", "visit_cnt"]
    dws_dis = pd.concat([by_cat[cols], by_dis[cols]], ignore_index=True)
    dws_dis["stat_month"] = dws_dis["dt"].str[:7]

    # DWS-4 药品消耗
    dws_drug = dwd_presc.groupby(["dt", "drug_id", "drug_name", "drug_type"], as_index=False).agg(
        total_qty=("quantity", "sum"), total_amount=("amount", "sum"),
        presc_times=("presc_id", "count"), is_insurance=("is_insurance", "max"))
    dws_drug["total_amount"] = dws_drug["total_amount"].round(2)
    dws_drug["stat_month"] = dws_drug["dt"].str[:7]

    # DWS-5 住院天数
    def los_agg(df, name):
        g = df.groupby(["dt", name], as_index=False).agg(
            admission_cnt=("adm_id", "count"), los_sum=("los_days", "sum"),
            los_max=("los_days", "max"), los_min=("los_days", "min"), cost_sum=("total_cost", "sum"))
        g["cured_cnt"] = df[df["outcome"].isin(["治愈", "好转"])].groupby(["dt", name]).size().reindex(
            pd.MultiIndex.from_frame(g[["dt", name]])).fillna(0).values.astype("int64")
        g = g.rename(columns={name: "dim_value"})
        return g
    l1 = los_agg(dwd_adm, "dept_name"); l1["dim_type"] = "科室"
    l2 = los_agg(dwd_adm, "los_level"); l2["dim_type"] = "天数区间"
    l3 = los_agg(dwd_adm, "disease_category"); l3["dim_type"] = "疾病类别"
    dws_los = pd.concat([l1, l2, l3], ignore_index=True)
    dws_los["cost_sum"] = dws_los["cost_sum"].round(2)
    dws_los["stat_month"] = dws_los["dt"].str[:7]
    dws_los = dws_los[["dt", "dim_type", "dim_value", "admission_cnt", "los_sum", "los_max",
                       "los_min", "cost_sum", "cured_cnt", "stat_month"]]

    # DWS-6 人群结构
    dws_demo = dwd_visit.groupby(["dt", "gender", "age_group", "insurance_type"], as_index=False).agg(
        visit_cnt=("visit_id", "count"), patient_cnt=("patient_id", "nunique"))
    dws_demo["stat_month"] = dws_demo["dt"].str[:7]

    return dws_dept, dws_time, dws_dis, dws_drug, dws_los, dws_demo


# ===========================================================================
# ADS
# ===========================================================================
def _period_cols(df, keys):
    """把 DWS 按 月 + 全部 两种周期展开。"""
    a = df.groupby(["stat_month"] + keys, as_index=False).sum(numeric_only=True)
    a = a.rename(columns={"stat_month": "stat_period"})
    b = df.groupby(keys, as_index=False).sum(numeric_only=True)
    b["stat_period"] = "全部"
    return pd.concat([a, b], ignore_index=True)


def build_ads(dwd_reg, dwd_visit, dwd_presc, dwd_adm, reg_all,
              dws_dept, dws_time, dws_dis, dws_drug, dws_los, dws_demo):
    ads = {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ---------- ADS-1 总体 KPI ----------
    def _agg_one(df, agg):
        out = {}
        for name, (col, how) in agg.items():
            if how == "count":
                out[name] = int(df[col].count())
            elif how == "nunique":
                out[name] = int(df[col].nunique())
            else:
                out[name] = float(df[col].sum())
        return out

    def per_period(df, agg):
        key = df["dt"].str[:7]
        a = pd.DataFrame([{**_agg_one(g, agg), "stat_period": k} for k, g in df.groupby(key)])
        b = pd.DataFrame([{**_agg_one(df, agg), "stat_period": "全部"}])
        return pd.concat([a, b], ignore_index=True)

    r = per_period(reg_all, {"reg_cnt": ("reg_id", "count")})
    rv = per_period(dwd_reg, {"visited_cnt": ("reg_id", "count"), "reg_fee_sum": ("reg_fee", "sum")})
    r = r.merge(rv, on="stat_period", how="outer")
    v = per_period(dwd_visit, {"visit_cnt": ("visit_id", "count"), "patient_cnt": ("patient_id", "nunique")})
    p = per_period(dwd_presc, {"presc_amount": ("amount", "sum"), "drug_qty": ("quantity", "sum")})
    a = per_period(dwd_adm, {"admission_cnt": ("adm_id", "count"), "los_sum": ("los_days", "sum"),
                             "admission_cost": ("total_cost", "sum")})
    inf_src = dws_dis[(dws_dis["dim_type"] == "疾病") & (dws_dis["is_infectious"] == 1)]
    i = per_period(inf_src, {"infectious_cnt": ("visit_cnt", "sum")})
    d = per_period(dwd_reg, {"dept_cnt": ("dept_id", "nunique")})

    kpi = r.merge(v, on="stat_period", how="outer").merge(p, on="stat_period", how="outer") \
        .merge(a, on="stat_period", how="outer").merge(i, on="stat_period", how="outer") \
        .merge(d, on="stat_period", how="outer")
    kpi["visit_rate"] = (kpi["visited_cnt"] * 100 / kpi["reg_cnt"]).round(2)
    kpi["avg_los_days"] = (kpi["los_sum"] / kpi["admission_cnt"]).round(2)
    kpi["avg_reg_fee"] = (kpi["reg_fee_sum"] / kpi["visited_cnt"]).round(2)
    kpi["avg_visit_drug_fee"] = (kpi["presc_amount"] / kpi["visit_cnt"]).round(2)
    kpi["infectious_rate"] = (kpi["infectious_cnt"] * 100 / kpi["visit_cnt"]).round(2)
    kpi["presc_amount"] = kpi["presc_amount"].round(2)
    kpi["admission_cost"] = kpi["admission_cost"].round(2)
    kpi["update_time"] = now
    int_cols = ["reg_cnt", "visited_cnt", "visit_cnt", "admission_cnt", "drug_qty",
                "infectious_cnt", "patient_cnt", "dept_cnt"]
    float_cols = ["visit_rate", "avg_los_days", "presc_amount", "admission_cost", "avg_reg_fee",
                  "avg_visit_drug_fee", "infectious_rate"]
    kpi[int_cols] = kpi[int_cols].fillna(0).astype("int64")
    kpi[float_cols] = kpi[float_cols].fillna(0).astype(float).round(2)
    kpi = kpi.sort_values("stat_period").reset_index(drop=True)   # 月份在前，'全部' 在最后
    ads["ads_overview_kpi"] = kpi[[
        "stat_period", "reg_cnt", "visited_cnt", "visit_rate", "visit_cnt", "admission_cnt",
        "avg_los_days", "presc_amount", "drug_qty", "admission_cost", "avg_reg_fee",
        "avg_visit_drug_fee", "infectious_cnt", "infectious_rate", "patient_cnt", "dept_cnt",
        "update_time"]].reset_index(drop=True)

    # ---------- ADS-2 疾病分布 ----------
    rows = []
    for dim_type in ("类别", "疾病"):
        sub = dws_dis[dws_dis["dim_type"] == dim_type]
        g = _period_cols(sub[["stat_month", "dim_value", "visit_cnt", "is_infectious"]].rename(
            columns={"dim_value": "disease_name"}), ["disease_name"])
        g["is_infectious"] = g["is_infectious"].astype(bool).astype(int)
        cat_map = sub.drop_duplicates("dim_value").set_index("dim_value")["disease_category"]
        g["disease_category"] = g["disease_name"].map(cat_map)
        g["dim_type"] = dim_type
        g["visit_ratio"] = (g["visit_cnt"] * 100 / g.groupby("stat_period")["visit_cnt"].transform("sum")).round(2)
        g["rank_no"] = g.groupby("stat_period")["visit_cnt"].rank(ascending=False, method="first").astype("int64")
        rows.append(g)
    dis = pd.concat(rows, ignore_index=True)
    ads["ads_disease_distribution"] = dis[[
        "stat_period", "dim_type", "disease_name", "disease_category", "is_infectious",
        "visit_cnt", "visit_ratio", "rank_no"]].reset_index(drop=True)

    # ---------- ADS-3 就诊高峰 ----------
    t_hour = dws_time.copy()
    t_hour["time_value"] = t_hour["visit_hour"].map(lambda h: f"{int(h):02d}:00")
    t_hour["sort_key"] = t_hour["visit_hour"]
    g1 = _period_cols(t_hour[["stat_month", "time_value", "sort_key", "visit_cnt"]], ["time_value", "sort_key"])
    g1["time_dim"] = "时段"

    t_wd = dws_time.groupby(["stat_month", "weekday", "weekday_cn"], as_index=False).agg(
        visit_cnt=("visit_cnt", "sum"))
    t_wd["time_value"] = t_wd["weekday_cn"]
    t_wd["sort_key"] = t_wd["weekday"]
    g2 = _period_cols(t_wd[["stat_month", "time_value", "sort_key", "visit_cnt"]], ["time_value", "sort_key"])
    g2["time_dim"] = "星期"

    t_mo = dws_time.groupby("stat_month", as_index=False).agg(visit_cnt=("visit_cnt", "sum"))
    t_mo["time_value"] = t_mo["stat_month"]
    t_mo["sort_key"] = t_mo["stat_month"].str[5:7].astype(int)
    g3 = t_mo.rename(columns={"stat_month": "stat_period"})
    g3["time_dim"] = "月份"

    peak = pd.concat([g1, g2, g3], ignore_index=True)
    peak["visit_ratio"] = (peak["visit_cnt"] * 100 / peak.groupby(["stat_period", "time_dim"])["visit_cnt"].transform("sum")).round(2)
    peak["rank_no"] = peak.groupby(["stat_period", "time_dim"])["visit_cnt"].rank(ascending=False, method="first").astype("int64")
    ads["ads_visit_peak"] = peak[["stat_period", "time_dim", "time_value", "sort_key",
                                  "visit_cnt", "visit_ratio", "rank_no"]].reset_index(drop=True)

    # ---------- ADS-4 科室工作量 ----------
    g = _period_cols(dws_dept[["stat_month", "dept_id", "dept_name", "dept_type_name", "reg_cnt",
                               "visit_cnt", "admission_cnt", "presc_amount", "drug_qty",
                               "reg_fee_sum", "los_sum"]],
                     ["dept_id", "dept_name", "dept_type_name"])
    g["dept_type_name"] = g["dept_type_name"].fillna("")
    g["avg_reg_fee"] = (g["reg_fee_sum"] / g["reg_cnt"]).round(2)
    g["los_avg_days"] = (g["los_sum"] / g["admission_cnt"]).round(2)
    g["workload_index"] = (g["visit_cnt"] + g["presc_amount"] / 100 + g["admission_cnt"] * 3).round(2)
    g["presc_amount"] = g["presc_amount"].round(2)
    g["rank_no"] = g.groupby("stat_period")["workload_index"].rank(ascending=False, method="first").astype("int64")
    ads["ads_dept_workload"] = g[[
        "stat_period", "dept_id", "dept_name", "dept_type_name", "reg_cnt", "visit_cnt",
        "admission_cnt", "presc_amount", "drug_qty", "avg_reg_fee", "los_avg_days",
        "workload_index", "rank_no"]].reset_index(drop=True)

    # ---------- ADS-5 药品消耗 ----------
    g = _period_cols(dws_drug[["stat_month", "drug_id", "drug_name", "drug_type", "total_qty",
                               "total_amount", "presc_times"]],
                     ["drug_id", "drug_name", "drug_type"])
    g["total_amount"] = g["total_amount"].round(2)
    g["qty_ratio"] = (g["total_qty"] * 100 / g.groupby("stat_period")["total_qty"].transform("sum")).round(2)
    g["amount_ratio"] = (g["total_amount"] * 100 / g.groupby("stat_period")["total_amount"].transform("sum")).round(2)
    g["rank_no"] = g.groupby("stat_period")["total_amount"].rank(ascending=False, method="first").astype("int64")
    ads["ads_drug_consumption"] = g[[
        "stat_period", "drug_id", "drug_name", "drug_type", "total_qty", "total_amount",
        "presc_times", "qty_ratio", "amount_ratio", "rank_no"]].reset_index(drop=True)

    # ---------- ADS-6 住院天数分析 ----------
    g = _period_cols(dws_los[["stat_month", "dim_type", "dim_value", "admission_cnt", "los_sum",
                              "cost_sum", "cured_cnt"]], ["dim_type", "dim_value"])
    los_max = dws_los.groupby(["dim_type", "dim_value"])["los_max"].max()
    los_min = dws_los.groupby(["dim_type", "dim_value"])["los_min"].min()
    g["los_max"] = g.set_index(["dim_type", "dim_value"]).index.map(los_max).astype("Int64")
    g["los_min"] = g.set_index(["dim_type", "dim_value"]).index.map(los_min).astype("Int64")
    g["avg_los"] = (g["los_sum"] / g["admission_cnt"]).round(2)
    g["avg_cost"] = (g["cost_sum"] / g["admission_cnt"]).round(2)
    g["total_cost"] = g["cost_sum"].round(2)
    g["cure_rate"] = (g["cured_cnt"] * 100 / g["admission_cnt"]).round(2)
    g["rank_no"] = g.groupby(["stat_period", "dim_type"])["avg_los"].rank(ascending=False, method="first").astype("int64")
    ads["ads_los_analysis"] = g[[
        "stat_period", "dim_type", "dim_value", "admission_cnt", "avg_los", "los_max", "los_min",
        "avg_cost", "total_cost", "cure_rate", "rank_no"]].reset_index(drop=True)

    # ---------- ADS-7 感染性疾病监测 ----------
    sub = dws_dis[(dws_dis["dim_type"] == "疾病") & (dws_dis["is_infectious"] == 1)]
    g = _period_cols(sub[["stat_month", "dim_value", "disease_category", "visit_cnt"]]
                     .rename(columns={"dim_value": "diagnosis_name"}), ["diagnosis_name", "disease_category"])
    g["case_cnt"] = g["visit_cnt"]
    g["case_ratio"] = (g["case_cnt"] * 100 / g.groupby("stat_period")["case_cnt"].transform("sum")).round(2)
    g["rank_no"] = g.groupby("stat_period")["case_cnt"].rank(ascending=False, method="first").astype("int64")
    code_map = dwd_visit.drop_duplicates("diagnosis_name").set_index("diagnosis_name")["diagnosis_code"]
    g["diagnosis_code"] = g["diagnosis_name"].map(code_map)
    ads["ads_infectious_monitor"] = g[[
        "stat_period", "diagnosis_code", "diagnosis_name", "disease_category", "case_cnt",
        "case_ratio", "rank_no"]].reset_index(drop=True)

    # ---------- 统一排序，便于人工核对与前端展示 ----------
    sort_keys = {
        "ads_overview_kpi": ["stat_period"],
        "ads_disease_distribution": ["stat_period", "dim_type", "rank_no"],
        "ads_visit_peak": ["stat_period", "time_dim", "sort_key"],
        "ads_dept_workload": ["stat_period", "rank_no"],
        "ads_drug_consumption": ["stat_period", "rank_no"],
        "ads_los_analysis": ["stat_period", "dim_type", "rank_no"],
        "ads_infectious_monitor": ["stat_period", "rank_no"],
    }
    for k, keys in sort_keys.items():
        ads[k] = ads[k].sort_values(keys).reset_index(drop=True)

    return ads


# ===========================================================================
# 主流程
# ===========================================================================
def main():
    t0 = datetime.now()
    log("=" * 70)
    log("本地离线计算引擎：ODS -> DWD -> DWS -> ADS")
    log("=" * 70)

    log("读取 ODS ...")
    log("构建 DIM/DWD 层 ...")
    dwd_reg, dwd_visit, dwd_presc, dwd_adm, reg_all = build_dwd()
    dd = build_dim_date()
    for name, df in (("dim_date", dd), ("dwd_registration_detail", dwd_reg),
                     ("dwd_visit_detail", dwd_visit), ("dwd_prescription_detail", dwd_presc),
                     ("dwd_admission_detail", dwd_adm)):
        log(f"  DWD {name:<28}{len(df):>10,} 行")

    log("构建 DWS 层 ...")
    dws_dept, dws_time, dws_dis, dws_drug, dws_los, dws_demo = build_dws(
        dwd_reg, dwd_visit, dwd_presc, dwd_adm)
    for name, df in (("dws_dept_workload_d", dws_dept), ("dws_visit_time_d", dws_time),
                     ("dws_disease_d", dws_dis), ("dws_drug_d", dws_drug),
                     ("dws_los_d", dws_los), ("dws_patient_demog_d", dws_demo)):
        log(f"  DWS {name:<28}{len(df):>10,} 行")

    log("构建 ADS 层 ...")
    ads = build_ads(dwd_reg, dwd_visit, dwd_presc, dwd_adm, reg_all,
                    dws_dept, dws_time, dws_dis, dws_drug, dws_los, dws_demo)
    for name, df in ads.items():
        log(f"  ADS {name:<28}{len(df):>10,} 行")

    log("落盘 ...")
    dwd_reg.to_csv(os.path.join(C.DWD_DIR, "dwd_registration_detail.csv"), index=False, encoding="utf-8-sig")
    dwd_visit.to_csv(os.path.join(C.DWD_DIR, "dwd_visit_detail.csv"), index=False, encoding="utf-8-sig")
    dwd_presc.to_csv(os.path.join(C.DWD_DIR, "dwd_prescription_detail.csv"), index=False, encoding="utf-8-sig")
    dwd_adm.to_csv(os.path.join(C.DWD_DIR, "dwd_admission_detail.csv"), index=False, encoding="utf-8-sig")
    dd.to_csv(os.path.join(C.DWD_DIR, "dim_date.csv"), index=False, encoding="utf-8-sig")

    for name, df in (("dws_dept_workload_d", dws_dept), ("dws_visit_time_d", dws_time),
                     ("dws_disease_d", dws_dis), ("dws_drug_d", dws_drug),
                     ("dws_los_d", dws_los), ("dws_patient_demog_d", dws_demo)):
        df.to_csv(os.path.join(C.DWS_DIR, f"{name}.csv"), index=False, encoding="utf-8-sig")

    for name, df in ads.items():
        df.to_csv(os.path.join(C.ADS_DIR, f"{name}.csv"), index=False, encoding="utf-8-sig")

    log("-" * 70)
    log(f"完成，耗时 {(datetime.now()-t0).total_seconds():.1f} 秒")
    log(f"ADS 输出目录：{C.ADS_DIR}")
    return ads


if __name__ == "__main__":
    main()
