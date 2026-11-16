# -*- coding: utf-8 -*-
"""
Spark Structured Streaming 实时作业（集群模式）
==================================================================
对应《项目操作流程》第 15 / 16 步：
    「同时使用爬虫技术实时爬取数据，将数据交给 spark streaming 进行实时处理」
    「将实时处理好的数据保存到 Windows 的 MySQL 中存储」

链路：
    Kafka(med_visit) → Spark Structured Streaming(60s 滚动窗口)
        → 清洗（去空、时间规整、字段裁剪）
        → 按窗口 + 科室聚合（就诊量、处方金额）
        → foreachBatch 写入 MySQL：rt_visit_stat / rt_kpi

提交方式（集群）：
    spark-submit --master yarn --deploy-mode client \
        --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 \
        --jars /opt/software/mysql-connector-j-8.0.33.jar \
        spark_streaming_job.py

本地调试（Windows，需 PySpark + JDK8/11）：
    spark-submit --master local[2] spark_streaming_job.py --bootstrap localhost:9092
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))
import config as C


def build_streaming_app(bootstrap: str, window_seconds: int = 60, ck_root: str = "/tmp/ck/med_health"):
    """构建并返回 StreamingQuery（便于单元测试单独调用）。

    ck_root: checkpoint 根目录。换 schema 后必须换新目录，
             否则 Spark 会因「状态 schema 不兼容」直接失败。
    """
    from pyspark.sql import SparkSession, functions as F
    from pyspark.sql.types import (DoubleType, IntegerType, StringType, StructField, StructType)

    spark = (SparkSession.builder
             .appName("MedHealthStreamingVisit")
             .config("spark.sql.shuffle.partitions", "4")
             .config("spark.sql.streaming.checkpointLocation", ck_root)
             .enableHiveSupport()
             .getOrCreate())
    spark.sparkContext.setLogLevel("WARN")

    schema = StructType([
        StructField("event_type", StringType()),
        StructField("event_time", StringType()),
        # —— 模拟 producer.py 的字段 ——
        StructField("reg_no", StringType()),
        StructField("patient_id", IntegerType()),
        StructField("gender", StringType()),
        StructField("age", IntegerType()),
        StructField("dept_id", IntegerType()),
        StructField("dept_name", StringType()),
        StructField("diagnosis_code", StringType()),
        StructField("diagnosis_name", StringType()),
        StructField("disease_category", StringType()),
        StructField("is_infectious", IntegerType()),
        StructField("presc_amount", DoubleType()),
        # —— 爬虫 crawler.py 追加的字段（CDC 公报真实发病/死亡数）——
        StructField("period", StringType()),
        StructField("case_cnt", IntegerType()),
        StructField("death_cnt", IntegerType()),
        StructField("source_url", StringType()),
        StructField("source", StringType()),
    ])

    raw = (spark.readStream
           .format("kafka")
           .option("kafka.bootstrap.servers", bootstrap)
           .option("subscribe", C.KAFKA_TOPICS["visit"])
           .option("startingOffsets", "latest")
           .option("failOnDataLoss", "false")
           .load())

    # ① 清洗：解析 JSON、剔除无效记录、规整事件时间
    events = (raw
              .select(F.from_json(F.col("value").cast("string"), schema).alias("e"))
              .select("e.*")
              .where(F.col("dept_name").isNotNull())
              .withColumn("presc_amount", F.coalesce(F.col("presc_amount"), F.lit(0.0)))
              .withColumn("case_cnt", F.coalesce(F.col("case_cnt"), F.lit(0)))
              .withColumn("death_cnt", F.coalesce(F.col("death_cnt"), F.lit(0)))
              .withColumn("period", F.coalesce(F.col("period"), F.lit("")))
              .withColumn("diagnosis_name", F.coalesce(F.col("diagnosis_name"), F.lit("")))
              .withColumn("ts", F.to_timestamp("event_time", "yyyy-MM-dd HH:mm:ss"))
              .withWatermark("ts", f"{window_seconds} seconds"))

    # ② 窗口聚合：60 秒滚动窗口 × 科室 × 病种
    #    visit_cnt  = 事件条数（模拟就诊流；爬虫事件每条记 1 次上报）
    #    case_cnt   = 窗口内「单条事件最大发病数」（= 公报真实值；取 max 而非 sum，
    #                 因为爬虫会循环重投同一份公报，sum 会按轮次累加导致数值虚高）
    #    death_cnt  = 同理取 max（公报真实死亡数）
    agg = (events
           .groupBy(F.window(F.col("ts"), f"{window_seconds} seconds"),
                    F.col("dept_name"), F.col("diagnosis_name"), F.col("period"))
           .agg(F.count("*").alias("visit_cnt"),
                F.round(F.sum("presc_amount"), 2).alias("presc_amount"),
                F.max("case_cnt").alias("case_cnt"),
                F.max("death_cnt").alias("death_cnt")))

    # ③ 写出：foreachBatch 保证幂等（按窗口先删后插）
    def write_batch(df, epoch_id):
        rows = df.collect()
        if not rows:
            return
        import pymysql
        conn = pymysql.connect(host=C.MYSQL["host"], port=C.MYSQL["port"], user=C.MYSQL["user"],
                               password=C.MYSQL["password"], database=C.MYSQL["database"],
                               charset="utf8mb4", autocommit=True)
        cur = conn.cursor()
        total_visit, total_amount, by_dept = 0, 0.0, {}
        we = max(r["window"]["end"] for r in rows).strftime("%Y-%m-%d %H:%M:%S")

        # —— rt_visit_stat：按「窗口 × 科室」汇总（病种维度在下方 rt_crawler_stat 明细）——
        dept_agg = {}
        for r in rows:
            d = r["dept_name"]
            a = dept_agg.setdefault(d, {"visit": 0, "amount": 0.0,
                                        "cs": 0, "ds": 0, "seen": set()})
            a["visit"] += r["visit_cnt"]
            a["amount"] += float(r["presc_amount"] or 0)
            # 同一病种在窗口内只计一次发病数，避免同病多科室行重复累加
            key = (r["period"], r["diagnosis_name"])
            if key not in a["seen"]:
                a["seen"].add(key)
                a["cs"] += int(r["case_cnt"] or 0)
                a["ds"] += int(r["death_cnt"] or 0)
            total_visit += r["visit_cnt"]
            total_amount += float(r["presc_amount"] or 0)
            by_dept[d] = by_dept.get(d, 0) + r["visit_cnt"]

        ws = min(r["window"]["start"] for r in rows).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("DELETE FROM rt_visit_stat WHERE window_end = %s", (we,))
        for d, a in dept_agg.items():
            cur.execute(
                "INSERT INTO rt_visit_stat"
                "(window_start, window_end, dept_name, visit_cnt, case_cnt, death_cnt, presc_amount, update_time) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())",
                (ws, we, d, a["visit"], a["cs"], a["ds"], round(a["amount"], 2)))

        top = max(by_dept.items(), key=lambda x: x[1])[0] if by_dept else None
        cur.execute(
            "INSERT INTO rt_kpi(window_end, reg_cnt, visit_cnt, presc_amount, top_dept, msg_per_sec, update_time) "
            "VALUES (%s,%s,%s,%s,%s,%s,NOW())",
            (we, total_visit, total_visit, round(total_amount, 2), top,
             round(total_visit / max(window_seconds, 1), 2)))

        # —— rt_crawler_stat：爬虫病种明细（取公报真实发病/死亡数）——
        crawler_rows = {(r["period"], r["diagnosis_name"]): r
                        for r in rows if int(r["case_cnt"] or 0) > 0}
        if crawler_rows:
            cur.execute("DELETE FROM rt_crawler_stat WHERE window_end = %s", (we,))
            for (period, disease), r in crawler_rows.items():
                cur.execute(
                    "INSERT INTO rt_crawler_stat"
                    "(window_end, period, disease_name, case_cnt, death_cnt, source, source_url, update_time) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,NOW())",
                    (we, period, disease,
                     int(r["case_cnt"] or 0), int(r["death_cnt"] or 0),
                     "CDC-crawler", ""))
        cur.close()
        conn.close()
        print(f"[batch {epoch_id}] 写入 {len(rows)} 行，窗口结束 {we}，"
              f"就诊 {total_visit} 人次，爬虫病种 {len(crawler_rows)} 行")

    # ④ 另外把实时明细落到 Hive 实时表，供离线侧做 T+0 报表
    detail_query = (events.writeStream
                    .outputMode("append")
                    .format("parquet")
                    .option("path", "/med_health/realtime/visit_events")
                    .option("checkpointLocation", f"{ck_root}/detail")
                    .trigger(processingTime="30 seconds")
                    .start())

    agg_query = (agg.writeStream
                 .foreachBatch(write_batch)
                 .outputMode("update")
                 .trigger(processingTime=f"{window_seconds} seconds")
                 .option("checkpointLocation", f"{ck_root}/agg")
                 .start())

    return spark, detail_query, agg_query


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bootstrap", default=C.KAFKA_BOOTSTRAP)
    ap.add_argument("--window", type=int, default=C.STREAM_WINDOW_SECONDS)
    ap.add_argument("--ck-root", default="/tmp/ck/med_health", help="checkpoint 根目录")
    ap.add_argument("--ck-clean", action="store_true", help="启动前清空 checkpoint（换 schema 后必用）")
    args = ap.parse_args()

    if args.ck_clean:
        import shutil
        shutil.rmtree(args.ck_root, ignore_errors=True)
        print(f"[实时] 已清空 checkpoint：{args.ck_root}")

    spark, q1, q2 = build_streaming_app(args.bootstrap, args.window, args.ck_root)
    print(f"实时作业已启动：Kafka={args.bootstrap}, 窗口={args.window}s, ck={args.ck_root}")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
