# -*- coding: utf-8 -*-
"""
实时数据生产者 —— 模拟医院 HIS 系统实时产生的挂号 / 就诊 / 处方事件
==================================================================
对应《项目操作流程》第 15 步：
    「同时使用爬虫技术实时爬取数据，将数据交给 spark streaming 进行实时处理」

集群模式（默认）：
    事件以 JSON 形式写入 Kafka 主题 med_registration / med_visit / med_prescription。
    Kafka 地址由 config.KAFKA_BOOTSTRAP 指定（默认 hadoop01:9092）。

本地模式（--local）：
    未部署 Kafka 时，事件写入本地 jsonl 文件，供 local_stream.py 消费，
    保证在 Windows 单机上也能完整演示「生产 → 消费 → 窗口聚合 → 落库」链路。

运行：
    python producer.py                 # 写入 Kafka（集群模式）
    python producer.py --local --rate 20 --seconds 300
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as C
import pandas as pd

try:
    from kafka import KafkaProducer
    HAS_KAFKA = True
except Exception:
    HAS_KAFKA = False

DEPTS = ["内科", "外科", "儿科", "妇产科", "骨科", "眼科", "耳鼻喉科", "皮肤科",
         "神经内科", "心血管内科", "消化内科", "呼吸内科", "内分泌科", "急诊科",
         "中医科", "口腔科", "康复医学科", "肿瘤科", "感染科", "精神心理科"]

LOCAL_STREAM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stream_events.jsonl")


def load_context():
    """从 ODS 数据中抽取真实存在的患者 / 科室 / 药品，保证实时数据与离线数据同源。"""
    pat = pd.read_csv(os.path.join(C.ODS_DIR, "ods_patient.csv"), usecols=["patient_id", "gender", "age"])
    drug = pd.read_csv(os.path.join(C.ODS_DIR, "ods_drug.csv"), usecols=["drug_id", "drug_name", "unit_price", "drug_type"])
    dis = pd.read_csv(os.path.join(C.ODS_DIR, "ods_disease.csv"), usecols=["diagnosis_code", "diagnosis_name", "disease_category", "is_infectious"])
    return pat, drug, dis


def make_event(pat, drug, dis):
    """构造一条实时挂号+就诊+处方事件。"""
    p = pat.sample(1).iloc[0]
    d = random.choice(DEPTS)
    dept_id = DEPTS.index(d) + 1
    diag = dis.sample(1).iloc[0]
    lines = random.choice([1, 2, 2, 3, 3, 4])
    items = []
    total = 0.0
    for _ in range(lines):
        dr = drug.sample(1).iloc[0]
        qty = random.randint(1, 6)
        amt = round(float(dr["unit_price"]) * qty, 2)
        total += amt
        items.append({"drug_id": int(dr["drug_id"]), "drug_name": dr["drug_name"],
                      "drug_type": dr["drug_type"], "qty": qty, "amount": amt})
    now = datetime.now()
    return {
        "event_type": "visit",
        "event_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "reg_no": f"RT{now:%Y%m%d%H%M%S}{random.randint(1000, 9999)}",
        "patient_id": int(p["patient_id"]),
        "gender": p["gender"],
        "age": int(p["age"]),
        "dept_id": dept_id,
        "dept_name": d,
        "diagnosis_code": diag["diagnosis_code"],
        "diagnosis_name": diag["diagnosis_name"],
        "disease_category": diag["disease_category"],
        "is_infectious": int(diag["is_infectious"]),
        "presc_items": items,
        "presc_amount": round(total, 2),
        "source": "HIS-realtime",
    }


def main():
    ap = argparse.ArgumentParser(description="实时事件生产者")
    ap.add_argument("--local", action="store_true", help="写入本地 jsonl 文件而非 Kafka")
    ap.add_argument("--rate", type=int, default=15, help="每秒产生事件数")
    ap.add_argument("--seconds", type=int, default=0, help="运行秒数，0 表示一直运行")
    args = ap.parse_args()

    pat, drug, dis = load_context()
    t0 = datetime.now()
    n = 0

    if args.local or not HAS_KAFKA:
        mode = "本地文件" if args.local else "本地文件（未安装 kafka-python，自动降级）"
        print(f"[生产者] 运行模式：{mode} -> {LOCAL_STREAM_FILE}")
        f = open(LOCAL_STREAM_FILE, "a", encoding="utf-8")
        tick = 0
        while True:
            for _ in range(args.rate):
                f.write(json.dumps(make_event(pat, drug, dis), ensure_ascii=False) + "\n")
                n += 1
            f.flush()
            tick += 1
            if tick % 5 == 0:
                print(f"[生产者] 已生成 {n:,} 条事件  ({datetime.now():%H:%M:%S})", flush=True)
            time.sleep(1)
            if args.seconds and (datetime.now() - t0).total_seconds() >= args.seconds:
                break
        f.close()
        print(f"[生产者] 退出，共生成 {n:,} 条事件")
        return

    print(f"[生产者] 运行模式：Kafka -> {C.KAFKA_BOOTSTRAP}")
    producer = KafkaProducer(
        bootstrap_servers=C.KAFKA_BOOTSTRAP.split(","),
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        acks=1, linger_ms=200)
    tick = 0
    while True:
        for _ in range(args.rate):
            ev = make_event(pat, drug, dis)
            producer.send(C.KAFKA_TOPICS["visit"], key=str(ev["patient_id"]), value=ev)
            producer.send(C.KAFKA_TOPICS["registration"], key=str(ev["patient_id"]),
                          value={"event_type": "registration", "event_time": ev["event_time"],
                                 "patient_id": ev["patient_id"], "dept_name": ev["dept_name"],
                                 "reg_no": ev["reg_no"]})
            for it in ev["presc_items"]:
                producer.send(C.KAFKA_TOPICS["prescription"], key=str(ev["patient_id"]),
                              value={"event_type": "prescription", "event_time": ev["event_time"],
                                     "visit_id": ev["reg_no"], **it})
            n += 1
        producer.flush()
        tick += 1
        if tick % 5 == 0:
            print(f"[生产者] 已投递 {n:,} 条事件到 Kafka ({datetime.now():%H:%M:%S})", flush=True)
        time.sleep(1)
        if args.seconds and (datetime.now() - t0).total_seconds() >= args.seconds:
            break
    producer.flush()
    producer.close()
    print(f"[生产者] 退出，共投递 {n:,} 条事件")


if __name__ == "__main__":
    main()
