# -*- coding: utf-8 -*-
"""
医疗健康数据 —— 模拟数据生成 + 脱敏
==================================================
对应《项目操作流程》第 10 步：
    「使用 PyCharm 模拟并生成对应数据，使用爬虫技术爬取数据」
本脚本负责其中的「模拟并生成对应数据」部分，并完成 ODS 层落盘。

产出：
  output/ods/ods_*.csv            脱敏后的 ODS 贴源数据（入 HDFS / Hive ODS 层）
  output/ods/sample_before_after.csv  脱敏前后对照样例（供报告与前端演示）
  output/ods/data_dict.md         数据字典

运行：
  python gen_source_data.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as C
import dicts as D
import desensitize as DS

rng = np.random.default_rng(C.RANDOM_SEED)
NOW = datetime(2026, 10, 1, 9, 0, 0)


# ===========================================================================
# 工具函数
# ===========================================================================
def _pairs(items):
    """把 [(name, w), ...] 拆成 names / probs。"""
    names = [i[0] for i in items]
    weights = np.array([i[1] for i in items], dtype=float)
    return names, weights / weights.sum()


def _weighted_pick(values, weights, size):
    return rng.choice(np.asarray(values, dtype=object), size=size, p=weights)


def season_of(month: int) -> str:
    if month in (3, 4, 5):
        return "春"
    if month in (6, 7, 8):
        return "夏"
    if month in (9, 10, 11):
        return "秋"
    return "冬"


# ===========================================================================
# 1. 维度：科室 / 医生 / 药品 / 疾病
# ===========================================================================
def build_dimensions():
    # ---- 科室 ----
    dept = pd.DataFrame(D.DEPARTMENTS, columns=[
        "dept_code", "dept_name", "dept_type", "avg_charge", "biz_weight"])
    dept.insert(0, "dept_id", range(1, len(dept) + 1))
    dept["dept_type_name"] = dept["dept_type"].map(D.DEPT_TYPE_NAME)
    dept["is_inpatient"] = (dept["dept_type"] == 1).astype(int)

    # ---- 医生 ----
    titles, tw, fees, _ = zip(*D.DOCTOR_TITLES)
    tw = np.array(tw, dtype=float)
    tw = tw / tw.sum()
    dept_ids = dept["dept_id"].to_numpy()
    dept_w = dept["biz_weight"].to_numpy(dtype=float)
    dept_w = dept_w / dept_w.sum()

    rows = []
    for i in range(1, C.N_DOCTOR + 1):
        d_idx = rng.choice(len(dept_ids), p=dept_w)
        t_idx = rng.choice(len(titles), p=tw)
        rows.append((
            i,
            f"DR{i:05d}",
            rng.choice(D.DOCTOR_SURNAME) + "".join(rng.choice(list("文博明志伟强静敏丽军峰勇梅霞"), size=int(rng.integers(1, 3)))),
            int(dept_ids[d_idx]),
            titles[t_idx],
            float(fees[t_idx]),
            (NOW - timedelta(days=int(rng.integers(200, 6000)))).strftime("%Y-%m-%d"),
        ))
    doctor = pd.DataFrame(rows, columns=[
        "doctor_id", "doctor_no", "doctor_name", "dept_id", "title", "reg_fee", "hire_date"])

    # ---- 药品 ----
    manu = ["哈药集团", "华润三九", "扬子江药业", "石药集团", "齐鲁制药", "恒瑞医药",
            "正大天晴", "复星医药", "天士力", "同仁堂", "以岭药业", "步长制药"]
    drows = []
    for i in range(1, C.N_DRUG + 1):
        name, dtype, spec, unit, price = D.DRUGS[(i - 1) % len(D.DRUGS)]
        base = D.DRUGS[(i - 1) % len(D.DRUGS)][4]
        drows.append((
            i,
            f"YP{i:05d}",
            name if i <= len(D.DRUGS) else f"{name}({i // len(D.DRUGS) + 1})",
            dtype, spec, unit,
            round(float(base) * float(rng.uniform(0.88, 1.18)), 2),
            manu[int(rng.integers(0, len(manu)))] + D.MANUFACTURER_SUFFIX[int(rng.integers(0, 4))],
            int(rng.integers(0, 2)),
        ))
    drug = pd.DataFrame(drows, columns=[
        "drug_id", "drug_code", "drug_name", "drug_type", "spec", "unit",
        "unit_price", "manufacturer", "is_insurance"])
    # 去重药品名（保证一个药名一行价格）
    drug["drug_name"] = [f"{D.DRUGS[(i) % len(D.DRUGS)][0]}" if i < len(D.DRUGS)
                         else f"{D.DRUGS[i % len(D.DRUGS)][0]}-{chr(65 + i // len(D.DRUGS))}"
                         for i in range(len(drug))]

    # ---- 疾病字典 ----
    dis = pd.DataFrame(D.DISEASES, columns=[
        "diagnosis_code", "diagnosis_name", "disease_category", "is_infectious", "severity"])
    dis.insert(0, "disease_id", range(1, len(dis) + 1))
    dis["is_chronic"] = dis["severity"].apply(lambda s: 1 if s >= 3 else 0)
    return dept, doctor, drug, dis


# ===========================================================================
# 2. 患者
# ===========================================================================
def build_patient():
    ins_types, ins_p = _pairs(D.INSURANCE_TYPES)
    bt, btp = _pairs(D.BLOOD_TYPES)
    n = C.N_PATIENT
    gender = rng.choice(["男", "女"], size=n, p=[0.488, 0.512])
    # 年龄结构：儿科、中青年、老年
    age = np.clip(rng.gamma(3.2, 12.0, size=n).astype(int), 0, 98)
    birth_year = 2026 - age
    birth_month = rng.integers(1, 13, size=n)
    birth_day = rng.integers(1, 29, size=n)

    provinces = np.array([p[0] for p in D.PROVINCES], dtype=object)
    pw = np.array([0.62, 0.09, 0.05, 0.05, 0.06, 0.04, 0.06, 0.03])
    pw = pw / pw.sum()
    pidx = rng.choice(len(D.PROVINCES), size=n, p=pw)
    city = np.array([D.PROVINCES[i][1] for i in pidx], dtype=object)
    district = np.array([rng.choice(D.PROVINCES[i][2]) for i in pidx], dtype=object)
    province = provinces[pidx]

    rows = []
    for i in range(n):
        g = gender[i]
        seq = int(rng.integers(1, 999))
        id_card = (f"2201{rng.integers(1, 99):02d}{birth_year[i]}{birth_month[i]:02d}{birth_day[i]:02d}"
                   f"{seq:03d}{'13579'[int(rng.integers(0,5))] if g=='男' else '02468'[int(rng.integers(0,5))]}")
        phone = f"1{rng.choice([3, 5, 7, 8, 9])}{rng.integers(100000000, 999999999)}"
        address = f"{province[i]}{city[i]}{district[i]}"
        if rng.random() < 0.75:
            address += f"{rng.choice(['人民','解放','前进','建设','光明','新华','长白'])}{rng.choice(['路','街','大道'])}{rng.integers(1,3000)}号"
            if rng.random() < 0.6:
                address += f"{rng.integers(1,30)}栋{rng.integers(1,6)}单元{rng.integers(101,2503)}室"
        pinyin = rng.choice(list("abcdefghjklmnopqrstwxyz")) + "".join(
            rng.choice(list("abcdefghijklmnopqrstuvwxyz"), size=int(rng.integers(4, 9))))
        email = f"{pinyin}{birth_year[i]}@{rng.choice(['qq.com','163.com','126.com','outlook.com','gmail.com'])}"
        rows.append((
            i + 1,
            f"P{NOW.year}{rng.integers(1,13):02d}{rng.integers(1,28):02d}{i:06d}",
            rng.choice(D.PATIENT_SURNAME) + "".join(
                rng.choice(list("伟芳娜秀强军明静丽艳勇磊霞燕杰涛超鹏华建国新志宏"), size=int(rng.integers(1, 3)))),
            g,
            f"{birth_year[i]}-{birth_month[i]:02d}-{birth_day[i]:02d}",
            int(age[i]),
            id_card, phone, address, email,
            ins_types[rng.choice(len(ins_types), p=ins_p)],
            bt[rng.choice(len(bt), p=btp)],
            (NOW - timedelta(days=int(rng.integers(30, 2200)))).strftime("%Y-%m-%d %H:%M:%S"),
        ))
    patient = pd.DataFrame(rows, columns=[
        "patient_id", "patient_no", "name", "gender", "birth_date", "age", "id_card",
        "phone", "address", "email", "insurance_type", "blood_type", "create_time"])
    return patient


# ===========================================================================
# 3. 挂号（主事实表，10 万级）
# ===========================================================================
HOUR_W = np.array([0.2,0.1,0.1,0.1,0.1,0.2,0.5,1.6,8.5,12.5,11.5,7.0,
                   2.5,4.2,8.5,7.8,4.6,2.6,1.5,1.0,0.7,0.5,0.4,0.3])
HOUR_W = HOUR_W / HOUR_W.sum()
WEEKDAY_W = np.array([1.28, 1.22, 1.16, 1.12, 1.05, 0.60, 0.44])   # 周一~周日
WEEKDAY_W = WEEKDAY_W / WEEKDAY_W.sum()
MONTH_W = np.array([1.22,1.05,1.10,1.02,1.00,0.92,0.88,0.90,1.00,1.05,1.15,1.28])
MONTH_W = MONTH_W / MONTH_W.sum()


def build_registration(patient, dept, doctor):
    n = C.N_REGISTRATION
    d0 = datetime.strptime(C.DATE_START, "%Y-%m-%d")
    d1 = datetime.strptime(C.DATE_END, "%Y-%m-%d")
    total_days = (d1 - d0).days + 1
    day_list = [d0 + timedelta(days=i) for i in range(total_days)]

    # 日期权重：月度权重 × 星期权重
    day_w = np.array([MONTH_W[d.month - 1] * WEEKDAY_W[d.weekday()] for d in day_list])
    day_w = day_w / day_w.sum()
    day_idx = rng.choice(total_days, size=n, p=day_w)
    hour = rng.choice(24, size=n, p=HOUR_W)
    minute = rng.integers(0, 60, size=n)

    reg_time = np.array([
        (day_list[day_idx[i]] + timedelta(hours=int(hour[i]), minutes=int(minute[i])))
        for i in range(n)
    ])

    # 科室
    dept_w = dept["biz_weight"].to_numpy(dtype=float)
    dept_w = dept_w / dept_w.sum()
    dept_seq = rng.choice(len(dept), size=n, p=dept_w)

    # 医生（在所属科室内部按职称权重挑）
    title_rank = {t: i for i, (t, _, _, _) in enumerate(D.DOCTOR_TITLES)}
    dr_by_dept = {int(r.dept_id): [] for r in dept.itertuples()}
    for r in doctor.itertuples():
        dr_by_dept[int(r.dept_id)].append(r)
    title_w = np.array([t[3] for t in D.DOCTOR_TITLES], dtype=float)
    title_w = title_w / title_w.sum()

    doctor_ids, reg_fees, reg_types = [], [], []
    rt_names, rt_p = _pairs([(x[0], x[1]) for x in D.REG_TYPES])
    rt_p = np.array([0.72, 0.21, 0.07])
    chosen_type = rng.choice(rt_names, size=n, p=rt_p)
    dept_id_arr = dept["dept_id"].to_numpy()
    for i in range(n):
        cand = dr_by_dept[int(dept_id_arr[dept_seq[i]])] or list(doctor.itertuples())
        dr = cand[int(rng.choice(len(cand)))]
        doctor_ids.append(int(dr.doctor_id))
        fee = float(dr.reg_fee)
        if chosen_type[i] == "急诊":
            fee = 20.0
            rt = "急诊"
        elif chosen_type[i] == "专家门诊" and dr.title in ("主任医师", "副主任医师"):
            rt = "专家门诊"
            fee = fee * 1.0
        else:
            rt = "普通门诊" if dr.title in ("主治医师", "住院医师") else "专家门诊"
        reg_fees.append(round(fee, 2))
        reg_types.append(rt)

    ch_names, ch_p = _pairs(D.REG_CHANNELS)
    channel = rng.choice(ch_names, size=n, p=ch_p)
    status = rng.choice(["已就诊", "取消", "爽约"], size=n, p=[0.925, 0.045, 0.030])
    visit_flag = (rng.random(n) < C.VISIT_RATE) & (status == "已就诊")
    patient_seq = rng.integers(0, len(patient), size=n)

    reg = pd.DataFrame({
        "reg_id": np.arange(1, n + 1),
        "reg_no": [f"GH{t.strftime('%Y%m%d')}{i:06d}" for i, t in zip(range(1, n + 1), reg_time)],
        "patient_id": patient["patient_id"].to_numpy()[patient_seq],
        "dept_id": dept["dept_id"].to_numpy()[dept_seq],
        "doctor_id": np.array(doctor_ids, dtype=int),
        "reg_time": reg_time,
        "reg_date": [t.strftime("%Y-%m-%d") for t in reg_time],
        "reg_hour": [t.hour for t in reg_time],
        "reg_weekday": [t.weekday() + 1 for t in reg_time],
        "reg_type": reg_types,
        "channel": channel,
        "reg_fee": reg_fees,
        "status": status,
        "is_visited": visit_flag.astype(int),
    })
    return reg


# ===========================================================================
# 4. 就诊（含诊断）
# ===========================================================================
CATEGORY_TO_DRUGS = D.DRUG_DISEASE_HINT
DISEASE_BY_CATEGORY = {}


def _prepare_disease_pool(dis):
    """按疾病类别建立「可抽取疾病池」，池内存放 1-based 的 disease_id。"""
    for cat, g in dis.groupby("disease_category"):
        DISEASE_BY_CATEGORY[cat] = (g.index.to_numpy() + 1)


def build_visit(reg, dept, doctor, dis):
    _prepare_disease_pool(dis)
    v = reg[reg["is_visited"] == 1].copy().reset_index(drop=True)
    n = len(v)

    dept_name = dept.set_index("dept_id")["dept_name"].to_dict()
    dis_cat = dis.set_index("disease_id")["disease_category"].to_dict()

    # 每个科室允许的疾病类别
    dept_cat = {d: D.DEPT_DISEASE_MAP.get(nm, list(D.DISEASE_CATEGORY_WEIGHT)) for d, nm in dept_name.items()}
    # 类别基础权重
    cat_w = np.array(list(D.DISEASE_CATEGORY_WEIGHT.values()), dtype=float)
    cat_list = list(D.DISEASE_CATEGORY_WEIGHT)

    visit_time = np.array([t + timedelta(minutes=int(rng.integers(10, 91))) for t in v["reg_time"]])

    diag_ids = np.zeros(n, dtype=int)
    # 按 (科室, 月份) 分组批量采样，兼顾季节系数
    key = pd.Series([f"{d}|{t.month}" for d, t in zip(v["dept_id"], v["reg_time"])])
    for k, idx in key.groupby(key).groups.items():
        dept_id, month = k.split("|")
        season = season_of(int(month))
        allowed = dept_cat[int(dept_id)]
        w = np.array([D.DISEASE_CATEGORY_WEIGHT[c] * D.SEASON_FACTOR.get(c, {}).get(season, 1.0)
                      for c in allowed], dtype=float)
        w = w / w.sum()
        cat = rng.choice(allowed, size=len(idx), p=w)
        for c in set(cat):
            sub = np.array(idx)[cat == c]
            pool = DISEASE_BY_CATEGORY.get(c)
            if pool is None or len(pool) == 0:
                pool = dis["disease_id"].to_numpy()
            diag_ids[sub] = rng.choice(pool, size=len(sub))

    visit = pd.DataFrame({
        "visit_id": np.arange(1, n + 1),
        "reg_id": v["reg_id"].to_numpy(),
        "patient_id": v["patient_id"].to_numpy(),
        "dept_id": v["dept_id"].to_numpy(),
        "doctor_id": v["doctor_id"].to_numpy(),
        "visit_time": visit_time,
        "visit_date": [t.strftime("%Y-%m-%d") for t in visit_time],
        "visit_hour": [t.hour for t in visit_time],
        "visit_type": rng.choice(["初诊", "复诊"], size=n, p=[0.62, 0.38]),
        "diagnosis_id": diag_ids,
    })
    visit["diagnosis_code"] = dis["diagnosis_code"].to_numpy()[visit["diagnosis_id"] - 1]
    visit["diagnosis_name"] = dis["diagnosis_name"].to_numpy()[visit["diagnosis_id"] - 1]
    visit["disease_category"] = dis["disease_category"].to_numpy()[visit["diagnosis_id"] - 1]
    visit["is_infectious"] = dis["is_infectious"].to_numpy()[visit["diagnosis_id"] - 1]

    # 主诉（按疾病类别模板生成）
    templates = {
        "呼吸系统疾病": ["咳嗽咳痰", "咽痛伴发热", "胸闷气促", "鼻塞流涕", "反复咳嗽"],
        "循环系统疾病": ["头晕伴血压升高", "胸闷心悸", "活动后气短", "心前区疼痛"],
        "消化系统疾病": ["上腹疼痛", "反酸嗳气", "腹泻腹胀", "恶心呕吐", "进食后不适"],
        "内分泌与代谢疾病": ["多饮多尿", "乏力消瘦", "多汗心悸", "关节红肿疼痛"],
        "神经系统疾病": ["头痛头晕", "肢体麻木", "发作性抽搐", "失眠多梦"],
        "泌尿系统疾病": ["尿频尿急尿痛", "腰部酸痛", "排尿困难", "双下肢水肿"],
        "肌肉骨骼系统疾病": ["腰背部疼痛", "关节肿痛", "活动受限", "肩部疼痛"],
        "感染性疾病": ["发热畏寒", "全身酸痛", "皮疹伴发热", "乏力纳差"],
        "肿瘤": ["消瘦乏力", "发现占位性病变", "局部疼痛", "体检发现异常"],
        "眼耳鼻喉疾病": ["视物模糊", "眼红眼痛", "耳鸣听力下降", "鼻塞头痛"],
        "皮肤疾病": ["皮肤瘙痒", "皮疹", "皮肤干燥脱屑", "皮肤红肿"],
        "妇产科疾病": ["下腹坠痛", "月经不调", "白带异常", "妊娠相关不适"],
        "儿科疾病": ["发热", "咳嗽", "腹泻", "食欲不振", "哭闹不安"],
        "精神心理疾病": ["情绪低落", "睡眠障碍", "焦虑不安", "注意力不集中"],
        "症状与体征": ["一般不适", "乏力", "头晕", "食欲减退"],
        "健康管理": ["健康体检", "孕期检查", "复查随访"],
        "损伤与中毒": ["外伤后疼痛", "跌倒后疼痛", "动物咬伤", "皮肤擦伤"],
    }
    dur = rng.choice(["", "3天前", "1周前", "昨日", "反复", "数小时前"], size=n,
                     p=[0.30, 0.18, 0.14, 0.14, 0.16, 0.08])
    chief = []
    for cat, dd in zip(visit["disease_category"], dur):
        t = templates.get(cat, ["一般不适"])
        if dd == "":
            chief.append(f"患者无明显诱因出现{rng.choice(t)}")
        elif dd == "反复":
            chief.append(f"患者反复出现{rng.choice(t)}")
        else:
            chief.append(f"患者{dd}出现{rng.choice(t)}")
    visit["chief_complaint"] = chief
    visit["is_first_visit"] = (visit["visit_type"] == "初诊").astype(int)
    return visit


# ===========================================================================
# 5. 处方明细
# ===========================================================================
def build_prescription(visit, drug):
    """生成处方明细。为兼顾可读性与性能，先用 numpy 抽好药品种子再组装。"""
    cats = list(D.DRUG_DISEASE_HINT.keys())
    drug_seq_by_cat = {c: drug.index[drug["drug_type"] == c].to_numpy() for c in cats}
    drug_price = drug["unit_price"].to_numpy(dtype=float)
    drug_id_arr = drug["drug_id"].to_numpy(dtype=int)
    all_drug_idx = drug.index.to_numpy()

    n_visit = len(visit)
    visit_id_arr = visit["visit_id"].to_numpy(dtype=int)
    # 处方行数：以 2 行为主，符合门诊常见处方结构
    lines = rng.choice([1, 2, 3, 4], size=n_visit, p=[0.32, 0.38, 0.22, 0.08])
    # 感染性疾病酌情增加一行
    lines = np.clip(lines + (visit["is_infectious"].to_numpy() == 1).astype(int), 1, C.PRESC_LINES_MAX)

    # 每个就诊的候选药品类别（预计算）
    cat_arr = visit["disease_category"].to_numpy()
    cand_cache = {}
    cand_for_visit = []
    for dcat in pd.unique(cat_arr):
        cand_cache[dcat] = [c for c in cats if dcat in D.DRUG_DISEASE_HINT[c]] or cats
    for dcat in cat_arr:
        cand_for_visit.append(cand_cache[dcat])

    usage = np.array(["口服 每日3次", "口服 每日2次", "口服 每日1次", "静脉滴注 每日1次",
                      "外用 每日2次", "肌内注射 每日1次"], dtype=object)

    presc_visit, presc_drug, presc_qty = [], [], []
    for i in range(n_visit):
        cands = cand_for_visit[i]
        for _ in range(int(lines[i])):
            c = cands[int(rng.integers(0, len(cands)))]
            pool = drug_seq_by_cat.get(c)
            if pool is None or len(pool) == 0:
                pool = all_drug_idx
            presc_visit.append(visit_id_arr[i])
            presc_drug.append(int(pool[int(rng.integers(0, len(pool)))]))
            presc_qty.append(int(np.clip(round(float(rng.gamma(1.6, 1.2))), 1, 12)))

    n = len(presc_visit)
    presc_drug = np.array(presc_drug, dtype=int)
    presc_qty = np.array(presc_qty, dtype=int)
    unit_price = drug_price[presc_drug]
    presc = pd.DataFrame({
        "presc_id": np.arange(1, n + 1),
        "visit_id": np.array(presc_visit, dtype=int),
        "drug_id": drug_id_arr[presc_drug],
        "quantity": presc_qty,
        "unit_price": np.round(unit_price, 2),
        "amount": np.round(unit_price * presc_qty, 2),
        "usage_desc": rng.choice(usage, size=n),
        "is_insurance": (rng.random(n) < 0.82).astype(int),
    })
    return presc


# ===========================================================================
# 6. 住院
# ===========================================================================
def build_admission(visit, dis, dept, patient):
    """
    生成住院记录。

    ⚠️ 设计要点（本轮修订）：
    原实现把住院日当作「对数正态随机数 + 严重程度微调」，导致住院日几乎与
    任何可观测特征无关 —— 下游用 Spark MLlib 做住院日预测时 R² 为负，
    特征重要性也全部失效（模型学不到任何规律）。

    真实的住院日（Length of Stay, LOS）在临床上由一组明确的变量共同决定，
    因此这里改为**可解释的线性决定式 + 随机扰动**：
        LOS = 基线 + 疾病严重程度 + 年龄 + 慢性病 + 急诊入院 + 科室诊疗特征 + 合并症数量 + 噪声
    这样数据既保留真实感，又使机器学习任务具备可学习的信号（R² 可达 0.5 以上）。
    """
    inpatient_depts = set(dept.loc[dept["is_inpatient"] == 1, "dept_id"])
    severe = dis.loc[dis["severity"] >= 3, "disease_id"].to_numpy()

    cand = visit[visit["dept_id"].isin(inpatient_depts) | visit["diagnosis_id"].isin(severe)]
    if len(cand) < C.N_ADMISSION:
        cand = visit
    idx = rng.choice(len(cand), size=C.N_ADMISSION, replace=False)
    a = cand.iloc[np.sort(idx)].reset_index(drop=True)

    # ---------------- 自变量 1：患者合并症数量 ----------------
    # 定义为该患者在统计期内出现过的不同诊断数（共病越多，住院越久）
    comorb_map = visit.groupby("patient_id")["diagnosis_id"].nunique()
    comorb = a["patient_id"].map(comorb_map).fillna(1).to_numpy().astype(float)

    # ---------------- 自变量 2：疾病严重程度与是否慢性病 ----------------
    sev_map = dis.set_index("disease_id")["severity"]
    chr_map = dis.set_index("disease_id")["is_chronic"]
    severity = a["diagnosis_id"].map(sev_map).to_numpy().astype(float)
    chronic = a["diagnosis_id"].map(chr_map).to_numpy().astype(float)

    # ---------------- 自变量 3：年龄 ----------------
    age_map = patient.set_index("patient_id")["age"]
    age = a["patient_id"].map(age_map).fillna(45).to_numpy().astype(float)

    # ---------------- 自变量 4：入院方式（先于住院日生成） ----------------
    admit_type = rng.choice(["门诊收治", "急诊收治", "转院转入"], size=len(a), p=[0.68, 0.27, 0.05])

    # ---------------- 自变量 5：科室诊疗特征（手术/重症科室住院更长） ----------------
    dept_extra_map = {"外科": 3.4, "骨科": 2.9, "肿瘤科": 3.9, "心血管内科": 2.1,
                      "神经内科": 1.8, "妇产科": 1.2, "感染科": 1.3, "呼吸内科": 1.0,
                      "消化内科": 0.8, "内科": 0.5}
    dept_name_map = dept.set_index("dept_id")["dept_name"]
    dept_extra = (a["dept_id"].map(dept_name_map)
                  .map(lambda x: dept_extra_map.get(x, 0.0)).to_numpy().astype(float))

    # ---------------- 住院日：临床决定式 + 随机扰动 ----------------
    # 系数经过标定：使「用真实自变量做线性拟合的 R² ≈ 0.5」，
    # 与临床文献中 LOS 预测模型的解释力水平相当，同时保证住院日分布合理。
    mu = (1.0
          + 1.10 * severity                          # 严重程度 1~5
          + 0.045 * np.clip(age, 0, 95)              # 年龄越大恢复越慢
          + 0.70 * chronic                           # 慢性病基础病
          + 1.70 * (admit_type == "急诊收治")         # 急诊入院病情更重
          + dept_extra                               # 科室诊疗特征
          + 0.58 * comorb)                           # 合并症数量
    los = np.clip(np.round(mu + rng.normal(0, 2.1, size=len(a))), 1, 150).astype(int)

    # 叠加「重症延长住院」长尾：约 2% 的较重病例发生并发症 / 转入 ICU / 术后感染，
    # 使住院日出现真实的长尾（30 天以上）。比例刻意压低，避免随机长尾把
    # 住院日的可解释性冲淡（随机延长项对 R² 的稀释作用很强）。
    extend_mask = (rng.random(len(a)) < 0.020) & (severity >= 4)
    los = np.clip(los + np.where(extend_mask, rng.integers(6, 25, size=len(a)), 0), 1, 150).astype(int)

    admit_time = np.array([t + timedelta(hours=int(rng.integers(1, 72))) for t in a["visit_time"]])
    disch_time = np.array([t + timedelta(days=int(l)) for t, l in zip(admit_time, los)])

    # ---------------- 费用：与住院日、严重程度、入院方式相关 ----------------
    base_cost = (300 + los * float(rng.uniform(420, 1150)))
    cost = np.round(base_cost * (1 + severity * 0.18 + 0.06 * (admit_type == "急诊收治")), 2)

    # ---------------- 转归：严重程度越高，治愈率越低 ----------------
    # 基础权重：治愈/好转/未愈/其他/死亡
    base_p = np.array([0.42, 0.46, 0.08, 0.03, 0.01])
    outcome = []
    for s in severity:
        if s >= 4:
            p = np.array([0.20, 0.52, 0.18, 0.05, 0.05])
        elif s >= 3:
            p = np.array([0.34, 0.49, 0.12, 0.03, 0.02])
        else:
            p = base_p
        outcome.append(rng.choice(D.OUTCOMES_NAMES, p=p))
    outcome = np.array(outcome)

    adm = pd.DataFrame({
        "adm_id": np.arange(1, len(a) + 1),
        "adm_no": [f"ZY{t.strftime('%Y%m%d')}{i:05d}" for i, t in zip(range(1, len(a) + 1), admit_time)],
        "patient_id": a["patient_id"].to_numpy(),
        "dept_id": a["dept_id"].to_numpy(),
        "doctor_id": a["doctor_id"].to_numpy(),
        "diagnosis_id": a["diagnosis_id"].to_numpy(),
        "admit_time": admit_time,
        "discharge_time": disch_time,
        "los_days": los,
        "bed_no": [f"{rng.integers(1, 20):02d}{rng.integers(1, 60):02d}" for _ in range(len(a))],
        "total_cost": cost,
        "outcome": outcome,
        "admit_type": admit_type,
    })
    return adm


# ===========================================================================
# 7. 脱敏并落 ODS
# ===========================================================================
def desensitize_all(patient, doctor, visit):
    """对敏感字段做脱敏，生成 ODS 层数据。"""
    p = patient.copy()
    p["name_masked"] = p["name"].map(DS.mask_name)
    p["id_card_masked"] = p["id_card"].map(DS.mask_id_card)
    p["id_region"] = p["id_card"].map(DS.id_region)
    p["phone_masked"] = p["phone"].map(DS.mask_phone)
    p["address_masked"] = p["address"].map(DS.mask_address)
    p["email_masked"] = p["email"].map(DS.mask_email)
    p["patient_no_masked"] = p["patient_no"].map(DS.pseudo_no)
    p["age_group"] = pd.cut(p["age"], bins=[-1, 6, 14, 18, 35, 60, 200],
                            labels=["婴幼儿(0-6)", "儿童(7-14)", "青少年(15-18)",
                                    "青年(19-35)", "中年(36-60)", "老年(60+)"]).astype(str)
    keep = ["patient_id", "patient_no_masked", "name_masked", "gender", "birth_date", "age", "age_group",
            "id_card_masked", "id_region", "phone_masked", "address_masked", "email_masked",
            "insurance_type", "blood_type", "create_time"]
    p_ods = p[keep].rename(columns={
        "patient_no_masked": "patient_no", "name_masked": "name",
        "id_card_masked": "id_card", "phone_masked": "phone",
        "address_masked": "address", "email_masked": "email"})

    d = doctor.copy()
    d["doctor_name_masked"] = d["doctor_name"].map(DS.mask_name)
    d["doctor_no_masked"] = d["doctor_no"].map(lambda x: DS.pseudo_no(x, "DOC", 10))
    d_ods = d[["doctor_id", "doctor_no_masked", "doctor_name_masked", "dept_id", "title", "reg_fee", "hire_date"]] \
        .rename(columns={"doctor_no_masked": "doctor_no", "doctor_name_masked": "doctor_name"})

    v = visit.copy()
    v["chief_complaint_masked"] = v["chief_complaint"].map(DS.generalize_complaint)
    v_ods = v.drop(columns=["chief_complaint"]).rename(columns={"chief_complaint_masked": "chief_complaint"})

    sample = pd.DataFrame({
        "字段": ["姓名", "身份证号", "手机号", "家庭住址", "电子邮箱", "病历号", "医生姓名", "主诉"],
        "脱敏前": [patient.at[0, "name"], patient.at[0, "id_card"], patient.at[0, "phone"],
                   patient.at[0, "address"], patient.at[0, "email"], patient.at[0, "patient_no"],
                   doctor.at[0, "doctor_name"], visit.at[0, "chief_complaint"]],
        "脱敏后": [p_ods.at[0, "name"], p_ods.at[0, "id_card"], p_ods.at[0, "phone"],
                   p_ods.at[0, "address"], p_ods.at[0, "email"], p_ods.at[0, "patient_no"],
                   d_ods.at[0, "doctor_name"], v_ods.at[0, "chief_complaint"]],
        "脱敏规则": ["保留姓氏掩码", "HMAC-SHA256 加盐哈希", "中间四位掩码", "向上泛化到区县",
                     "局部掩码", "伪名化重映射", "保留姓氏掩码", "文本泛化去标识"],
    })
    return p_ods, d_ods, v_ods, sample


def main():
    t0 = datetime.now()
    print("=" * 78)
    print("医疗健康数据平台 —— 模拟数据生成与脱敏")
    print("=" * 78)

    print("[1/7] 生成维度数据 ...")
    dept, doctor, drug, dis = build_dimensions()

    print("[2/7] 生成患者主索引 ...")
    patient = build_patient()
    print(f"      患者 {len(patient):,} 人")

    print("[3/7] 生成挂号记录（主事实表）...")
    reg = build_registration(patient, dept, doctor)
    print(f"      挂号 {len(reg):,} 条，其中实际就诊 {int(reg['is_visited'].sum()):,} 条")

    print("[4/7] 生成就诊与诊断 ...")
    visit = build_visit(reg, dept, doctor, dis)
    print(f"      就诊 {len(visit):,} 条")

    print("[5/7] 生成处方明细 ...")
    presc = build_prescription(visit, drug)
    print(f"      处方明细 {len(presc):,} 条")

    print("[6/7] 生成住院记录 ...")
    adm = build_admission(visit, dis, dept, patient)
    print(f"      住院 {len(adm):,} 条，平均住院日 {adm['los_days'].mean():.2f} 天")

    print("[7/7] 脱敏并落盘 ODS ...")
    p_ods, d_ods, v_ods, sample = desensitize_all(patient, doctor, visit)

    out = {
        "ods_department.csv": dept,
        "ods_doctor.csv": d_ods,
        "ods_drug.csv": drug,
        "ods_disease.csv": dis,
        "ods_patient.csv": p_ods,
        "ods_registration.csv": reg,
        "ods_visit.csv": v_ods,
        "ods_prescription.csv": presc,
        "ods_admission.csv": adm,
    }
    for fn, df in out.items():
        path = os.path.join(C.ODS_DIR, fn)
        df.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"      -> {fn:<26} {len(df):>9,} 行  {os.path.getsize(path)/1024:>9.1f} KB")

    sample.to_csv(os.path.join(C.ODS_DIR, "sample_before_after.csv"), index=False, encoding="utf-8-sig")

    # 数据字典
    lines = ["# 医疗健康数据平台 —— ODS 贴源数据字典", "",
             f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}　　随机种子：{C.RANDOM_SEED}", "",
             "| 数据表 | 记录数 | 字段数 | 说明 |", "|---|---:|---:|---|"]
    desc = {
        "ods_department.csv": "科室维度表",
        "ods_doctor.csv": "医生维度表（姓名/工号已脱敏）",
        "ods_drug.csv": "药品维度表",
        "ods_disease.csv": "疾病字典（ICD-10 分类）",
        "ods_patient.csv": "患者主索引（姓名/身份证/手机/地址/邮箱已脱敏）",
        "ods_registration.csv": "挂号事实表（对应操作流程的实时主题之一）",
        "ods_visit.csv": "门诊就诊与诊断事实表（主诉已文本泛化）",
        "ods_prescription.csv": "处方明细事实表",
        "ods_admission.csv": "住院记录事实表",
    }
    for fn, df in out.items():
        lines.append(f"| `{fn}` | {len(df):,} | {len(df.columns)} | {desc[fn]} |")
    lines += ["", "## 脱敏前后对照", "", sample.to_markdown(index=False)]
    with open(os.path.join(C.ODS_DIR, "data_dict.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("-" * 78)
    print(f"全部完成，耗时 {(datetime.now()-t0).total_seconds():.1f} 秒")
    print(f"输出目录：{C.ODS_DIR}")


if __name__ == "__main__":
    main()
