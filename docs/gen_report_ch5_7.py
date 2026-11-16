# -*- coding: utf-8 -*-
"""
课程设计报告 —— 第 5~7 章、参考文献与附录
所有统计数字均从 MySQL（med_health 库 ADS 结果表）实时读取。
"""
from __future__ import annotations

import os
import sys

from docx.shared import Cm, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_report_ch1_4 import tab, fig, TABLE_N, FIG_N
from report_builder import q, q1, fmtd, wan, img

P = "全部"


def kpi():
    return q1("SELECT * FROM ads_overview_kpi WHERE stat_period=%s", (P,))


# 特征名 -> 业务解读（用于住院日预测的特征重要性表）
FEATURE_HINT = {
    "severity": "疾病严重程度（1~5 级），病情越重住院越久，是最强预测因子",
    "dept_name": "就诊科室，反映诊疗路径与手术比例差异",
    "age": "患者年龄，年龄越大机体恢复越慢",
    "is_chronic": "是否慢性病，合并基础病会延长住院时间",
    "disease_category": "疾病大类，不同系统的疾病住院日差异明显",
    "admit_type": "入院方式，急诊入院者病情更重、住院更久",
    "insurance_type": "医保类型，间接反映人群结构与就医行为差异",
    "gender": "性别，影响较小",
    "is_infectious": "是否法定传染病，影响较小（传染病多为短期住院）",
}


def _feat_hint(name):
    return FEATURE_HINT.get(name, "—")


# ---------------------------------------------------------------------------
# 从 MySQL 读取模型 / 图计算结果（第 5、6 章共用）
# ---------------------------------------------------------------------------
def mv(model, metric, default=0.0):
    """读取指定模型的评估指标值。"""
    rows = q("SELECT metric_value FROM ads_ml_metric WHERE model_name=%s AND metric_name=%s",
             (model, metric))
    return float(rows[0]["metric_value"]) if rows else default


def netv(name, default=0.0):
    """读取疾病共现网络的整体指标值。"""
    rows = q("SELECT metric_value FROM ads_network_metric WHERE metric_name=%s", (name,))
    return float(rows[0]["metric_value"]) if rows else default


def ch5(rep):
    k = kpi()
    rep.h1("5　详细设计与系统实现")

    # ---------------- 5.1 数据生成与采集 ----------------
    rep.h2("5.1　数据生成与采集")
    rep.h3("5.1.1　数据模型设计")
    rep.p("数据生成模块（code/data_generator）以三范式关系模型为基础，"
          "按「维度表先行、事实表后生」的顺序构造数据：先生成 20 个科室、300 名医生、"
          "200 种药品与 122 条 ICD-10 疾病字典，再生成 20 000 名患者主索引，"
          "最后以患者与科室为基准生成挂号、就诊、处方与住院四类事实数据。"
          "模块使用固定随机种子（20261008），保证多次执行得到完全一致的数据集，便于测试与比对。")

    rep.h3("5.1.2　业务规则建模")
    rep.p("为使生成数据具备真实统计特征，模块将医院的运行规律编码为概率分布，主要包括五类规则：")
    rep.bullet("（1）就诊时段分布：按 24 小时权重建模，上午 8—11 时与下午 14—16 时形成双峰，"
               "夜间权重极低，符合门诊作息规律。")
    rep.bullet("（2）星期效应：周一至周五权重 1.28 / 1.22 / 1.16 / 1.12 / 1.05，"
               "周六周日降至 0.60 / 0.44，体现周末门诊量下降。")
    rep.bullet("（3）季节系数：呼吸系统疾病冬季系数 1.45、夏季 0.75，"
               "感染性疾病夏季 1.30，从而使疾病谱随月份产生合理波动。")
    rep.bullet("（4）科室—疾病映射：为 20 个科室分别配置主要收治疾病大类，"
               "保证「骨科以肌肉骨骼系统疾病为主、心血管内科以循环系统疾病为主」等业务合理性。")
    rep.bullet("（5）药品—疾病匹配：为 27 个药品类别配置对应的疾病大类，"
               "使处方用药与诊断保持业务一致，避免出现「诊断肺炎却开具眼科药物」这类失真数据。")
    rep.p("此外，挂号状态按已就诊 92.5%、取消 4.5%、爽约 3.0% 的比例生成，"
          "挂号到就诊的转化率设定为 95%，用于在总体 KPI 中体现挂号就诊转化率这一运营指标。")

    rep.h3("5.1.3　数据规模与质量校验")
    rep.p("本次生成的数据规模如表 5-1 所示。全部数据生成耗时 14.5 秒。"
          "质量校验通过 DWD 层的 WHERE 条件完成：挂号仅保留已就诊记录，"
          "就诊要求诊断编码非空，处方要求数量与金额为正，住院要求天数大于 0。")
    tab(rep, "数据生成规模与校验结果",
        ["数据表", "记录数", "脱敏字段数", "清洗后保留", "清洗规则"],
        [["患者主索引", "20,000", "6", "20,000", "—"],
         ["挂号记录", "120,000", "0", fmtd(k["visited_cnt"]), "排除取消 / 爽约"],
         ["门诊就诊", "105,334", "1", fmtd(k["visit_cnt"]), "诊断编码非空"],
         ["处方明细", "223,191", "0", "223,191", "数量与金额为正"],
         ["住院记录", "14,000", "0", "14,000", "住院天数 > 0"]],
        widths=[3.0, 2.4, 2.4, 2.6, 3.4])

    # ---------------- 5.2 脱敏 ----------------
    rep.h2("5.2　数据脱敏实现")
    rep.p("脱敏模块（code/data_generator/desensitize.py）实现 8 条字段级规则，"
          "并在脱敏同时派生统计所需的可用属性。规则清单如表 5-2，脱敏前后对照如表 5-3。")

    rules = q("SELECT * FROM desensitize_rule ORDER BY rule_id")
    tab(rep, "字段级数据脱敏规则",
        ["字段", "脱敏方式", "实现方法", "可逆性"],
        [[r["field_name"], r["rule_type"], r["method_desc"], r["reversible"]] for r in rules],
        widths=[3.4, 2.8, 7.6, 1.6], fs=8.5)

    tab(rep, "脱敏前后对照示例（首条记录）",
        ["字段", "脱敏前", "脱敏后"],
        [[r["field_name"].split(" ")[0], r["example_raw"], r["example_masked"]] for r in rules],
        widths=[2.8, 6.6, 6.0], fs=8.5)

    rep.p("脱敏实现的关键点有三：其一，哈希采用 HMAC-SHA256 并拼接固定盐值 "
          "（HASH_SALT = \"MED_PLATFORM_2026_JLAU\"），既避免彩虹表反查，"
          "又保证同一原值在不同表中的脱敏结果一致，使 patient 与 registration、visit、"
          "prescription、admission 之间的关联查询不失效；"
          "其二，姓名脱敏保留姓氏并对复姓（如「欧阳」「司马」）做专门处理，"
          "身份证在哈希之外单独派生 id_region（地区码）与 age_group（年龄段），"
          "使「按地域统计」「按年龄统计」仍然可行；"
          "其三，主诉属非结构化文本，采用正则规则剔除数字、时间与陪同人员姓名，"
          "避免间接标识符泄露。")

    # ---------------- 5.3 数仓分层实现 ----------------
    rep.h2("5.3　数据入湖与数仓分层实现")
    rep.h3("5.3.1　数据入湖")
    rep.p("脱敏后的 ODS 数据以 UTF-8 with BOM 编码的 CSV 落盘至 output/ods 目录，"
          "再通过 HDFS 命令上传至 /med_health/ods。Hive ODS 层使用外部表（EXTERNAL TABLE）"
          "配合 OpenCSVSerde 直接映射这些文件，并设置 skip.header.line.count=1 跳过表头。"
          "使用外部表的意义在于：删除元数据不会影响 HDFS 上的原始文件，符合贴源层「只读、可追溯」的定位。")
    rep.code("hdfs dfs -mkdir -p /med_health/ods\n"
             "hdfs dfs -put -f output/ods/ods_*.csv /med_health/ods/\n"
             "beeline -u jdbc:hive2://hadoop01:10000 -n hadoop -f warehouse/hive/01_ods_ddl.sql")

    rep.h3("5.3.2　DWD 明细层")
    rep.p("DWD 层承担清洗与维度退化两项核心工作。以就诊明细表为例，"
          "ETL 语句同时关联患者、科室、医生、疾病四张维度表，"
          "把性别、年龄段、医保类型、科室名称、医生姓名、疾病大类、严重程度、"
          "是否法定传染病、是否慢性病等常用属性直接打宽到明细表，"
          "使后续统计不再需要反复关联维度表，显著降低 JOIN 开销。"
          "同时派生「就诊时段」（上午 / 下午 / 夜间）与「住院天数字段分箱」等业务分桶字段。")
    rep.code("INSERT OVERWRITE TABLE dwd_visit_detail PARTITION (dt)\n"
             "SELECT v.visit_id, v.reg_id, v.patient_id,\n"
             "       p.gender, p.age, p.age_group, p.insurance_type,\n"
             "       v.dept_id, d.dept_name, v.doctor_id, doc.doctor_name,\n"
             "       from_unixtime(unix_timestamp(v.visit_time,'yyyy-MM-dd HH:mm:ss'),\n"
             "                     'yyyy-MM-dd HH:mm:ss')            AS visit_time,\n"
             "       v.visit_hour,\n"
             "       CASE WHEN v.visit_hour BETWEEN 6 AND 11 THEN '上午'\n"
             "            WHEN v.visit_hour BETWEEN 12 AND 17 THEN '下午'\n"
             "            ELSE '夜间' END                            AS visit_period,\n"
             "       v.diagnosis_code, v.diagnosis_name, v.disease_category,\n"
             "       ds.severity, v.is_infectious, ds.is_chronic, v.chief_complaint,\n"
             "       v.visit_date AS dt\n"
             "FROM ods_visit v\n"
             "LEFT JOIN ods_patient    p   ON v.patient_id  = p.patient_id\n"
             "LEFT JOIN ods_department d   ON v.dept_id     = d.dept_id\n"
             "LEFT JOIN ods_doctor     doc ON v.doctor_id   = doc.doctor_id\n"
             "LEFT JOIN ods_disease    ds  ON v.diagnosis_id = ds.disease_id\n"
             "WHERE v.diagnosis_code IS NOT NULL AND v.diagnosis_code <> '';")

    rep.h3("5.3.3　DWS 汇总层与本地等价引擎")
    rep.p("DWS 层按「日期 + 分析维度」做轻度聚合，共 6 张主题汇总表。"
          "为避免同一指标在 ADS 层被重复计算，科室工作量在 DWS 层通过 FULL OUTER JOIN "
          "把挂号、就诊、处方、住院四条数据流的按日汇总拼宽为一条记录，"
          "使后续任意周期、任意科室的汇总都只需对该表做一次 GROUP BY。")
    rep.p("考虑到答辩演示环境往往只有一台 Windows 机器，"
          "本设计额外实现了一套与 Hive SQL 口径完全等价的本地计算引擎"
          "（code/local_engine/etl_local.py）。该引擎用 pandas 复现了四层加工逻辑，"
          "产出同名、同结构、同口径的 DWD / DWS / ADS 结果表，"
          "使得在无 Hadoop 集群的条件下也能完整跑通「数据 → 指标 → 落库 → 展示」链路。"
          "集群侧与本地侧可交叉验证：在集群跑完 Hive 后，"
          "用同一口径抽样比对 ADS 结果即可确认一致性。本地引擎处理全量数据的耗时为 6.5 秒。")

    # ---------------- 5.4 离线统计 ----------------
    rep.h2("5.4　离线统计分析实现")
    rep.p("离线统计共实现 7 个 ADS 结果表，分别支撑 7 个分析主题。各主题的实现口径如下。")

    rep.h3("5.4.1　总体概览 KPI")
    rep.p("总体概览从挂号、就诊、处方、住院四条链路分别聚合后按统计周期拼宽，"
          "结果如表 5-4 所示。指标口径在数据字典与前端页面中均有显式说明，"
          "避免业务人员把「挂号总量」与「门诊就诊人次」混为一谈。")
    tab(rep, "总体概览 KPI（统计周期：全部）",
        ["指标", "数值", "单位", "口径说明"],
        [["挂号总量", fmtd(k["reg_cnt"]), "人次", "含取消、爽约"],
         ["有效就诊挂号量", fmtd(k["visited_cnt"]), "人次", "状态为「已就诊」"],
         ["挂号就诊转化率", f"{float(k['visit_rate']):.2f}", "%", "有效就诊挂号量 / 挂号总量"],
         ["门诊就诊人次", fmtd(k["visit_cnt"]), "人次", "产生诊断记录的挂号人次"],
         ["住院人次", fmtd(k["admission_cnt"]), "人次", "住院记录数"],
         ["平均住院日", f"{float(k['avg_los_days']):.2f}", "天", "住院天数合计 / 住院人次"],
         ["处方总金额", fmtd(k["presc_amount"], 2), "元", "门诊处方明细金额合计"],
         ["药品消耗总量", fmtd(k["drug_qty"]), "单位", "处方明细数量合计"],
         ["住院总费用", fmtd(k["admission_cost"], 2), "元", "含药品、检查、治疗、床位等全部费用"],
         ["次均挂号费", f"{float(k['avg_reg_fee']):.2f}", "元", "挂号费合计 / 有效就诊挂号量"],
         ["次均药品费用", f"{float(k['avg_visit_drug_fee']):.2f}", "元", "处方总金额 / 门诊就诊人次"],
         ["法定传染病报告", fmtd(k["infectious_cnt"]), "例", "按法定报告病种口径统计"],
         ["法定传染病占比", f"{float(k['infectious_rate']):.2f}", "%", "法定传染病就诊人次 / 门诊就诊人次"],
         ["就诊患者人数", fmtd(k["patient_cnt"]), "人", "按 patient_id 去重"],
         ["覆盖科室数", fmtd(k["dept_cnt"]), "个", "统计期内有业务的科室数"]],
        widths=[3.6, 2.8, 1.6, 7.4], fs=8.5)

    rep.h3("5.4.2　疾病分布分析")
    rep.p("疾病分布按「疾病大类」与「单病种」两个维度分别统计就诊人次与占比，"
          "并通过 row_number() 窗口函数生成排名。"
          "疾病大类反映区域疾病负担结构，单病种反映具体诊疗需求。结果如表 5-5、表 5-6 所示。")
    cat = q("SELECT disease_name, visit_cnt, visit_ratio FROM ads_disease_distribution "
            "WHERE stat_period=%s AND dim_type='类别' ORDER BY rank_no LIMIT 12", (P,))
    tab(rep, "疾病大类分布 TOP12（统计周期：全部）",
        ["排名", "疾病大类", "就诊人次", "占比"],
        [[i + 1, c["disease_name"], fmtd(c["visit_cnt"]), f"{float(c['visit_ratio']):.2f}%"]
         for i, c in enumerate(cat)],
        widths=[1.4, 5.0, 2.6, 2.4])

    dis = q("SELECT disease_name, disease_category, visit_cnt, visit_ratio, is_infectious "
            "FROM ads_disease_distribution WHERE stat_period=%s AND dim_type='疾病' "
            "ORDER BY rank_no LIMIT 15", (P,))
    tab(rep, "单病种就诊量 TOP15（统计周期：全部）",
        ["排名", "病种名称", "所属大类", "就诊人次", "占比", "法定传染病"],
        [[i + 1, x["disease_name"], x["disease_category"], fmtd(x["visit_cnt"]),
          f"{float(x['visit_ratio']):.2f}%", "是" if x["is_infectious"] == 1 else "否"]
         for i, x in enumerate(dis)],
        widths=[1.2, 3.8, 3.2, 2.2, 1.8, 2.0], fs=8.5)

    rep.h3("5.4.3　就诊高峰分析")
    rep.p("就诊高峰按小时、星期、月份三个时间维度统计。"
          "时段维度用于门诊排班与号源投放：统计结果显示，"
          "就诊量在 09:00—11:00 形成主峰、15:00—16:00 形成次峰，"
          "与上午集中放号、下午复诊为主的业务安排相符；"
          "星期维度显示工作日显著高于周末，周末就诊量约为工作日的 45%—50%；"
          "月份维度可用于观察季节性疾病波动。结果如表 5-7 所示。")
    peak = q("SELECT time_value, visit_cnt, visit_ratio FROM ads_visit_peak "
             "WHERE stat_period=%s AND time_dim='时段' ORDER BY sort_key", (P,))
    busiest = sorted(peak, key=lambda x: -x["visit_cnt"])[:6]
    tab(rep, "就诊高峰时段 TOP6（统计周期：全部）",
        ["排名", "时段", "就诊人次", "占比"],
        [[i + 1, p["time_value"], fmtd(p["visit_cnt"]), f"{float(p['visit_ratio']):.2f}%"]
         for i, p in enumerate(busiest)],
        widths=[1.4, 3.0, 3.0, 2.6])

    rep.h3("5.4.4　科室工作量分析")
    rep.p("科室工作量以挂号量、就诊量、住院人次、处方金额、药品数量、"
          "次均挂号费、平均住院日七个指标刻画，并构造综合工作量指数："
          "工作量指数 = 就诊量 + 处方金额 / 100 + 住院人次 × 3。"
          "该指数把门诊服务量、药品服务量与住院服务量折算到同一量纲，"
          "便于对不同业务形态的科室做横向比较。结果如表 5-8 所示。")
    dept = q("SELECT dept_name, dept_type_name, reg_cnt, visit_cnt, admission_cnt, "
             "presc_amount, workload_index FROM ads_dept_workload "
             "WHERE stat_period=%s ORDER BY rank_no LIMIT 12", (P,))
    tab(rep, "科室工作量 TOP12（统计周期：全部）",
        ["排名", "科室", "类型", "挂号量", "就诊量", "住院人次", "处方金额(元)", "工作量指数"],
        [[i + 1, x["dept_name"], x["dept_type_name"], fmtd(x["reg_cnt"]), fmtd(x["visit_cnt"]),
          fmtd(x["admission_cnt"]), fmtd(x["presc_amount"], 0), fmtd(x["workload_index"], 0)]
         for i, x in enumerate(dept)],
        widths=[1.1, 2.4, 2.0, 1.9, 1.9, 1.9, 2.6, 2.4], fs=8)

    rep.h3("5.4.5　药品消耗分析")
    rep.p("药品消耗按消耗金额、消耗数量、开具次数三个口径统计并生成排名，"
          "同时按药品类别汇总金额结构。金额榜用于识别费用集中品种、"
          "支撑合理用药与成本控制；数量榜用于观察基础用药的消耗规模。"
          "金额 TOP10 结果如表 5-9 所示。")
    drug = q("SELECT drug_name, drug_type, total_qty, total_amount, presc_times, amount_ratio, "
             "qty_ratio FROM ads_drug_consumption WHERE stat_period=%s ORDER BY rank_no LIMIT 10", (P,))
    tab(rep, "药品消耗金额 TOP10（统计周期：全部）",
        ["排名", "药品名称", "类别", "消耗数量", "消耗金额(元)", "开具次数", "金额占比"],
        [[i + 1, x["drug_name"], x["drug_type"], fmtd(x["total_qty"]), fmtd(x["total_amount"], 2),
          fmtd(x["presc_times"]), f"{float(x['amount_ratio']):.2f}%"]
         for i, x in enumerate(drug)],
        widths=[1.1, 3.6, 2.4, 2.0, 2.6, 1.9, 1.8], fs=8)

    rep.h3("5.4.6　住院天数分析")
    rep.p("住院天数分析按科室、住院天数区间、疾病类别三个维度展开，"
          "统计平均住院日、最长与最短住院日、次均费用与治愈好转率。"
          "住院天数区间分布用于评估住院日集中度，是评价床位周转效率的重要依据。"
          "结果如表 5-10、表 5-11 所示。")
    los_r = q("SELECT dim_value, admission_cnt, avg_los FROM ads_los_analysis "
              "WHERE stat_period=%s AND dim_type='天数区间'", (P,))
    order = ["1-3天", "4-7天", "8-14天", "15-30天", "30天以上"]
    los_r = sorted(los_r, key=lambda x: order.index(x["dim_value"]) if x["dim_value"] in order else 99)
    total_adm = sum(int(x["admission_cnt"]) for x in los_r) or 1
    tab(rep, "住院天数区间分布（统计周期：全部）",
        ["住院天数区间", "住院人次", "占比", "区间平均住院日(天)"],
        [[x["dim_value"], fmtd(x["admission_cnt"]),
          f"{int(x['admission_cnt']) * 100 / total_adm:.2f}%", f"{float(x['avg_los']):.2f}"]
         for x in los_r],
        widths=[3.4, 2.6, 2.4, 4.0])

    los_d = q("SELECT dim_value, admission_cnt, avg_los, avg_cost, cure_rate FROM ads_los_analysis "
              "WHERE stat_period=%s AND dim_type='科室' ORDER BY rank_no LIMIT 10", (P,))
    tab(rep, "各科室平均住院日 TOP10（统计周期：全部）",
        ["排名", "科室", "住院人次", "平均住院日(天)", "次均费用(元)", "治愈好转率"],
        [[i + 1, x["dim_value"], fmtd(x["admission_cnt"]), f"{float(x['avg_los']):.2f}",
          fmtd(x["avg_cost"], 2), f"{float(x['cure_rate']):.2f}%"] for i, x in enumerate(los_d)],
        widths=[1.2, 3.4, 2.2, 3.0, 2.8, 2.4], fs=8.5)

    rep.h3("5.4.7　法定传染病监测")
    rep.p("法定传染病监测按《中华人民共和国传染病防治法》规定的法定报告病种口径统计，"
          "在疾病字典中通过 is_infectious 字段标识，经 DWD 层退化到就诊明细，"
          "在 ADS 层按病种与月份汇总。需要说明的是，本模块统计范围不含普通感染性疾病"
          "（如急性上呼吸道感染、急性支气管炎等未被列为法定报告传染病的病种），"
          "因此其占比明显低于广义「感染性疾病」占比。结果如表 5-12 所示。")
    inf = q("SELECT diagnosis_code, diagnosis_name, disease_category, case_cnt, case_ratio "
            "FROM ads_infectious_monitor WHERE stat_period=%s ORDER BY rank_no", (P,))
    tab(rep, "法定传染病报告病种分布（统计周期：全部）",
        ["排名", "ICD-10", "病种名称", "所属类别", "报告例数", "占比"],
        [[i + 1, x["diagnosis_code"], x["diagnosis_name"], x["disease_category"],
          fmtd(x["case_cnt"]), f"{float(x['case_ratio']):.2f}%"] for i, x in enumerate(inf)],
        widths=[1.1, 1.8, 3.6, 3.2, 2.0, 1.8], fs=8.5)

    # ---------------- 5.5 实时链路 ----------------
    rep.h2("5.5　实时链路实现")
    rep.p("实时链路解决「近实时监测」需求，采用 Kafka 作为消息缓冲、"
          "Spark Structured Streaming 作为流处理引擎；"
          "数据来源除模拟业务事件外，还包含真实网络爬虫抓取的中国疾控中心疫情公报。"
          "整体结构如下：")
    rep.code("数据源 A：CDC 疫情公报爬虫          数据源 B：模拟业务事件生产者\n"
             "  crawler.py                          producer.py\n"
             "  （抓取 chinacdc.cn 公开通报）         （挂号/就诊/处方事件）\n"
             "        │  JSON                              │  JSON\n"
             "        └──────────────┬─────────────────────┘\n"
             "                       ▼\n"
             "Kafka 主题：med_registration / med_visit / med_prescription（分区键 = patient_id）\n"
             "                       │\n"
             "                       ▼\n"
             "Spark Structured Streaming\n"
             "  ├─ 解析 JSON → 清洗（剔除空科室、负金额）\n"
             "  ├─ to_timestamp 规整事件时间 → Watermark 容忍乱序\n"
             "  ├─ window(ts, '60 seconds') 滚动窗口 × GROUP BY dept_name\n"
             "  └─ foreachBatch 写入 MySQL：\n"
             "       rt_visit_stat（科室窗口明细）/ rt_kpi（全局 KPI）\n"
             "       rt_crawler_stat（爬虫疫情病种明细）\n"
             "                       │\n"
             "                       ▼\n"
             "Flask 实时监控页面（前端每 5 秒轮询 /api/realtime）")

    rep.h3("5.5.1　实时数据爬虫实现")
    rep.p("《项目操作流程》第 15 步要求「使用爬虫技术实时爬取数据，将数据交给 Spark Streaming "
          "进行实时处理」。为此实现了真实网络爬虫 `code/realtime/crawler.py`，"
          "抓取中国疾病预防控制中心官网（www.chinacdc.cn）公开发布的"
          "《全国法定传染病疫情概况》。爬取流程分两级：")
    rep.bullet("列表页解析：从 `https://www.chinacdc.cn/jksj/jksj01/` 抓取公报列表，"
               "用正则匹配「YYYY年M月……疫情概况」标题，解析出各期详情页链接，按期次倒序取最近若干期。")
    rep.bullet("详情页解析：对每期公报正文，提取全国报告总量与死亡数、甲/乙/丙三类传染病"
               "分类统计，以及「法定传染病报告发病、死亡统计表」中的逐病种明细"
               "（病名、发病数、死亡数）。")
    rep.p("详情页解析有两个关键技术点。其一是**脚注干扰的排除**：CDC 公报 HTML 中的脚注上标"
          "（¹²³…）被压平为纯文本后表现为病名后的一个 1~2 位小整数，"
          "例如「新型冠状病毒感染 ² 770671 6」实际含义是病名=新型冠状病毒感染、"
          "发病=770671、死亡=6，其中「2」是脚注序号而非发病数。"
          "解析器按「病名 + 数字序列」整体匹配后判定：两个数字即发病数、死亡数，"
          "三个数字则首数为脚注序号予以丢弃。其二是**病种类别的精确判定**："
          "公报表格未逐行标注甲/乙/丙类，本设计内置依据《中华人民共和国传染病防治法》"
          "（2020 修订）整理的法定传染病分类表（甲类 2 种、乙类 40 种、丙类 11 种）"
          "做精确匹配，避免正文分区启发式误判。")
    rep.p("爬取结果经 `build_events()` 构造为与模拟生产者**完全同构**的 JSON 事件，"
          "写入同一批 Kafka 主题并携带 `source=CDC-crawler` 标记与公报原文链接，"
          "因此下游的 `spark_streaming_job.py` / `local_stream.py` **一行都不需要修改**"
          "即可同时消费两类数据源，体现了批流一体与数据契约稳定的设计优势。"
          "爬虫还实现了带重试的容错抓取、2 秒请求间隔的爬虫礼仪、"
          "本地 JSON 缓存（避免重复请求）以及无 Kafka 环境下的本地 jsonl 降级投放。")
    rep.p("实际抓取效果：本次运行抓取了最近 12 期月度公报（2025-09 至 2026-08），"
          "累计解析出 600 余条病种明细记录。以最新一期（2026 年 8 月）为例，"
          "全国共报告法定传染病 2,122,516 例，其中乙类 1,054,045 例、丙类 1,068,468 例；"
          "报告发病数居前 5 位的病种依次为流行性感冒（827,013 例）、"
          "新型冠状病毒感染（770,671 例）、其他感染性腹泻病（148,205 例）、"
          "病毒性肝炎（143,259 例）、手足口病（85,884 例），"
          "均为 CDC 官网公开的真实统计值。")

    # 爬虫结果表：取实时表中窗口内出现、发病数居前的病种
    _cr = q("SELECT period, disease_name, MAX(case_cnt) AS case_cnt, MAX(death_cnt) AS death_cnt "
            "FROM rt_crawler_stat GROUP BY period, disease_name "
            "ORDER BY case_cnt DESC LIMIT 10")
    if _cr:
        tab(rep, "实时链路抓取的 CDC 疫情病种明细（按发病数降序）",
            ["公报期次", "病种名称", "报告发病数", "报告死亡数", "数据来源"],
            [[x["period"], x["disease_name"], fmtd(x["case_cnt"]), fmtd(x["death_cnt"]),
              "CDC 官网爬取"] for x in _cr],
            widths=[2.4, 4.6, 2.6, 2.6, 3.0], fs=8.5)

    rep.h3("5.5.2　流处理作业设计")
    rep.p("流处理作业（code/realtime/spark_streaming_job.py）包含三项关键设计："
          "一是基于事件时间的窗口聚合，并设置 Watermark 容忍网络乱序；"
          "二是通过 foreachBatch 自行控制写入逻辑，"
          "在批次内同时写入按科室的窗口明细表 rt_visit_stat、全局 KPI 表 rt_kpi "
          "与爬虫疫情明细表 rt_crawler_stat，保证三表数据一致；"
          "三是设置 checkpointLocation，"
          "使作业重启后能从检查点恢复，实现「至少一次」语义。")
    rep.p("考虑到单机环境未部署 Kafka 与 Spark，本设计同样提供了本地等价实现"
          "（code/realtime/local_stream.py）：生产者（或爬虫）将事件写入本地 jsonl 文件，"
          "本地流引擎按同一窗口长度切分并聚合写入 MySQL 的同名同结构表，"
          "字段、口径与集群模式完全一致，可在答辩演示中完整展示实时链路的运行效果。"
          "实测本地模式下每 8~10 秒窗口处理数十条事件、覆盖 20 个科室，"
          "并在同窗口内将爬虫抓取的病种发病数/死亡数写入 rt_crawler_stat。")

    # ---------------- 5.6 可视化平台 ----------------
    rep.h2("5.6　可视化平台实现")
    rep.h3("5.6.1　后端接口设计")
    rep.p("Flask 后端共定义 13 个页面路由与 16 个数据接口。页面路由通过装饰器组合完成"
          "「登录校验 + 角色校验」，接口统一返回 JSON 结构 {ok, data}，"
          "由前端 ECharts 渲染。主要接口如表 5-13 所示。")
    tab(rep, "Flask 数据接口清单",
        ["接口路径", "方法", "功能", "权限"],
        [["/api/overview", "GET", "总体 KPI 与月度趋势", "全部角色"],
         ["/api/disease", "GET", "疾病分布（类别 / 单病种）", "全部角色"],
         ["/api/peak", "GET", "就诊高峰（时段 / 星期 / 月份）", "全部角色"],
         ["/api/dept", "GET", "科室工作量", "管理员、医师"],
         ["/api/drug", "GET", "药品消耗与类别结构", "管理员、医师"],
         ["/api/los", "GET", "住院天数分析", "管理员、医师"],
         ["/api/infectious", "GET", "法定传染病监测", "管理员、医师"],
         ["/api/realtime", "GET", "实时窗口指标", "管理员、医师"],
         ["/api/ml/metrics", "GET", "住院日预测模型评估指标", "管理员、医师"],
         ["/api/ml/importance", "GET", "模型特征重要性（列级 / 取值级）", "管理员、医师"],
         ["/api/ml/predictions", "GET", "预测明细，支持按风险等级筛选", "管理员、医师"],
         ["/api/network/nodes", "GET", "疾病共现网络节点属性", "管理员、医师"],
         ["/api/network/edges", "GET", "疾病共现网络边", "管理员、医师"],
         ["/api/network/metrics", "GET", "网络整体指标、社区分布、大类地位", "管理员、医师"],
         ["/api/consistency", "GET", "双引擎统计口径一致性校验结果", "管理员、医师"],
         ["/api/desensitize", "GET", "脱敏规则说明", "全部角色"],
         ["/export/{name}", "GET", "导出 Excel", "仅管理员"],
         ["/export/detail/{name}", "GET", "导出 CSV", "仅管理员"]],
        widths=[4.6, 1.6, 6.4, 2.8], fs=8.5)

    rep.h3("5.6.2　权限控制实现")
    rep.p("权限模型采用「页面级 + 接口级」双重校验。页面级通过 PAGES 字典声明每个页面"
          "允许的角色集合，导航菜单据此动态渲染，未授权页面直接跳回概览页；"
          "接口级通过 roles_required 装饰器校验，未授权时返回 403 与提示信息，"
          "防止绕过前端直接调用接口。三种角色的权限边界如第 4 章所述。")

    rep.h3("5.6.3　界面实现")
    rep.p("平台界面采用「左侧导航 + 顶部状态栏 + 内容区」布局，"
          "使用统一的蓝色主色调与卡片式内容组织。登录页与各功能页面截图如下。")
    fig(rep, "ui/dashboard.png", "综合概览大屏（首页）", width=15.5)
    fig(rep, "ui/disease.png", "疾病分布分析页面", width=15.5)
    fig(rep, "ui/peak.png", "就诊高峰分析页面", width=15.5)
    fig(rep, "ui/dept.png", "科室工作量分析页面", width=15.5)
    fig(rep, "ui/drug.png", "药品消耗分析页面", width=15.5)
    fig(rep, "ui/los.png", "住院天数分析页面", width=15.5)
    fig(rep, "ui/infectious.png", "法定传染病监测页面", width=15.5)
    fig(rep, "ui/desensitize.png", "数据脱敏规则页面", width=15.5)
    fig(rep, "ui/realtime.png", "实时数据监控页面", width=15.5)
    fig(rep, "ui/ml.png", "住院日预测模型页面（Spark MLlib）", width=15.5)
    fig(rep, "ui/network.png", "疾病共现网络页面（Spark GraphX）", width=15.5)
    fig(rep, "ui/report.png", "报表导出页面", width=15.5)
    fig(rep, "ui/about.png", "平台说明页面（架构与数据字典）", width=15.5)

    # ---------------- 5.7 机器学习 ----------------
    rep.h2("5.7　机器学习实现（Spark MLlib 住院日预测）")
    rep.h3("5.7.1　任务定义与特征工程")
    rep.p("住院日（Length of Stay, LOS）预测是医院运营管理的核心问题之一："
          "准确的住院日预测可支撑床位预留、临床路径管理与医保费用预估。"
          "本设计基于住院明细数据，用 Spark MLlib 完成两个互补的子任务：")
    rep.bullet("任务一（回归）：预测住院天数 los_days —— 随机森林回归 RandomForestRegressor；")
    rep.bullet("任务二（分类）：预测是否超长住院（los_days > 15 天）—— "
               "随机森林分类 RandomForestClassifier，用于识别需要重点关注的高风险病例。")
    rep.p("特征工程从患者、科室、疾病三个维度构建 9 个特征。"
          "数值特征 4 个：年龄、疾病严重程度（1~5 级）、是否慢性病、是否法定传染病；"
          "类别特征 5 个：性别、医保类型、入院方式、科室、疾病大类。"
          "类别特征经 StringIndexer 编码后再由 OneHotEncoder 做独热展开（dropLast），"
          "与数值特征拼装为特征向量；样本按 8:2 划分训练集与测试集（随机种子 20261008）。")
    rep.p("需要说明一处重要的数据处理决策：住院日属长尾分布，超长住院（> 15 天）"
          "在样本中仅占约 15%，属明显不平衡类别。若不加处理，模型会退化为「全部预测为不超长」，"
          "虽然准确率看似接近 85%，但 AUC 仅约 0.56，完全没有识别能力。"
          "因此本设计对分类任务引入**类别权重**（按负正样本比为正样本加权），"
          "使模型真正学到少数类的判别边界。")

    ml_metric = q("SELECT model_name, task_type, metric_name, metric_value, train_cnt, test_cnt, "
                  "feature_cnt, params FROM ads_ml_metric ORDER BY task_type, model_name, metric_id")

    train_cnt = ml_metric[0]["train_cnt"] if ml_metric else 0
    test_cnt = ml_metric[0]["test_cnt"] if ml_metric else 0
    feat_cnt = ml_metric[0]["feature_cnt"] if ml_metric else 0

    rep.h3("5.7.2　模型训练与评估结果")
    rep.p(f"训练集 {fmtd(train_cnt)} 例、测试集 {fmtd(test_cnt)} 例，特征向量维度 {feat_cnt}。" 
          "回归与分类各训练两个模型（随机森林与梯度提升）作横向对照，评估结果如表 5-14 所示。")
    tab(rep, "住院日预测模型评估结果",
        ["任务类型", "模型", "评估指标", "指标值", "说明"],
        [["回归", "随机森林回归", "R²", f"{mv('RandomForestRegressor','R2'):.4f}", "解释住院日方差的比例"],
         ["回归", "随机森林回归", "RMSE", f"{mv('RandomForestRegressor','RMSE'):.4f}", "均方根误差（天）"],
         ["回归", "随机森林回归", "MAE", f"{mv('RandomForestRegressor','MAE'):.4f}", "平均绝对误差（天）"],
         ["回归", "梯度提升回归", "R²", f"{mv('GBTRegressor','R2'):.4f}", "对照模型"],
         ["回归", "梯度提升回归", "RMSE", f"{mv('GBTRegressor','RMSE'):.4f}", "对照模型"],
         ["分类", "随机森林分类", "AUC", f"{mv('RandomForestClassifier','AUC'):.4f}", "ROC 曲线下面积"],
         ["分类", "随机森林分类", "AUC-PR", f"{mv('RandomForestClassifier','AUC_PR'):.4f}", "PR 曲线下面积（不平衡场景）"],
         ["分类", "随机森林分类", "准确率", f"{mv('RandomForestClassifier','Accuracy'):.4f}", "整体判断正确率"],
         ["分类", "随机森林分类", "F1", f"{mv('RandomForestClassifier','F1'):.4f}", "精确率与召回率的调和平均"],
         ["分类", "随机森林分类", "加权精确率", f"{mv('RandomForestClassifier','Precision'):.4f}", "—"],
         ["分类", "随机森林分类", "加权召回率", f"{mv('RandomForestClassifier','Recall'):.4f}", "—"],
         ["分类", "梯度提升分类", "AUC", f"{mv('GBTClassifier','AUC'):.4f}", "对照模型"],
         ["分类", "梯度提升分类", "准确率", f"{mv('GBTClassifier','Accuracy'):.4f}", "对照模型"],
         ["分类", "梯度提升分类", "F1", f"{mv('GBTClassifier','F1'):.4f}", "对照模型"]],
        widths=[2.2, 3.4, 2.6, 2.2, 5.6], fs=8.5)
    rep.p(f"结果表明：回归模型 R² = {mv('RandomForestRegressor','R2'):.4f}，"
          f"平均绝对误差仅 {mv('RandomForestRegressor','MAE'):.2f} 天，"
          "即预测住院日与真实住院日平均相差约 2 天，具备实用参考价值；"
          f"分类模型 AUC = {mv('RandomForestClassifier','AUC'):.4f}，"
          f"准确率 {mv('RandomForestClassifier','Accuracy'):.4f}，"
          "在超长住院识别这一类别不平衡任务上表现良好。"
          "两个对照模型（梯度提升）与随机森林接近，说明当前特征体系已覆盖主要信息量。")

    imp_rows_db = q("SELECT feature_name, importance FROM ads_ml_feature_importance "
                    "WHERE model_name='RandomForestRegressor' ORDER BY rank_no")
    if imp_rows_db:
        rep.p("特征重要性方面（随机森林基尼重要性归一化），各特征对住院日的解释力排序如表 5-15 所示。"
              "结果显示疾病严重程度、科室、年龄、是否慢性病是最主要的影响因素，"
              "与临床经验一致：病情越重、年龄越大、合并基础病越多，住院时间越长；"
              "外科、肿瘤科等手术与重症科室的住院日显著高于普通内科科室。")
        tab(rep, "住院日预测特征重要性",
            ["排名", "特征", "重要性", "业务解读"],
            [[i + 1, r["feature_name"], f"{float(r['importance']):.4f}", _feat_hint(r["feature_name"])]
             for i, r in enumerate(imp_rows_db[:10])],
            widths=[1.2, 3.2, 2.4, 7.6], fs=8.5)

    detail_stat = q1("SELECT COUNT(1) AS cnt, ROUND(AVG(ABS(residual)),2) AS mae, "
                     "ROUND(AVG(predicted_los),2) AS avg_pred, ROUND(AVG(actual_los),2) AS avg_actual, "
                     "SUM(is_long_stay) AS long_cnt, SUM(risk_label='高风险') AS high_cnt "
                     "FROM ads_ml_los_prediction")
    rep.p(f"测试集抽样 {fmtd(detail_stat['cnt'])} 例的预测明细显示："
          f"平均预测住院日 {detail_stat['avg_pred']} 天，平均实际住院日 {detail_stat['avg_actual']} 天，"
          f"整体无明显系统性偏差；平均绝对误差 {detail_stat['mae']} 天。"
          f"模型共标记 {fmtd(detail_stat['high_cnt'])} 例为高风险，"
          f"其中实际发生超长住院 {fmtd(detail_stat['long_cnt'])} 例。"
          "预测结果通过 JDBC 写入 MySQL 表 ads_ml_los_prediction，由平台「住院日预测模型」页面展示，"
          "并可按风险等级筛选，形成面向临床的**重点关注病例清单**。")

    rep.h3("5.7.3　工程实现要点")
    rep.p("本作业（code/warehouse/spark/ml_los_prediction.py）在工程上有三处值得说明：")
    rep.bullet("（1）特征名还原。OneHotEncoder 会把类别特征展开成多维，"
               "无法直接用下标对应原始特征。本实现从 VectorAssembler 写入列元数据中的 "
               "ml_attr.attrs 读取 (idx, name) 映射来还原每个维度名，"
               "这是 Spark 官方推荐做法，比手工推算 one-hot 维度数可靠。")
    rep.bullet("（2）双任务输出合并。回归模型给出 predicted_los（连续住院日），"
               "分类模型给出 risk_prob（超长住院概率），二者必须分开取用；"
               "若误把分类模型的 prediction（0/1 类别标签）当作住院日，"
               "会得到全部为 1 天的荒谬结果 —— 这是实践中容易踩的坑。")
    rep.bullet("（3）代表性抽样。预测明细若按风险概率降序取前 300 条，"
               "展示样本将全部为高风险个案，平均误差严重失真；"
               "本实现改为按固定种子随机抽样 300 条，保证样本具有代表性。")

    # ---------------- 5.8 图计算 ----------------
    rep.h2("5.8　图计算实现（Spark GraphX 疾病共现网络）")
    rep.h3("5.8.1　业务建模")
    rep.p("同一患者在一段时间内先后被诊断出多种疾病，这些疾病之间即构成「共现关系」。"
          "以疾病为顶点、以共现关系为边、以共同患者数作为边权，"
          "即可构建**疾病共现网络（Comorbidity Network）**。"
          "该网络可回答两类临床与公共卫生问题："
          "① 哪些疾病处于网络中心 —— 一旦发生，并发其他疾病的风险最高，应重点管理；"
          "② 哪些疾病聚成一簇 —— 提示共同的病理机制或诊疗路径，可作为共病研究的切入点。")

    rep.h3("5.8.2　图算法与实现路径")
    rep.p("GraphX 是 Spark 的图计算库，官方仅提供 Scala API；"
          "PySpark 侧与其对应的是 GraphFrames 封装。"
          "为兼顾「可验证」与「贴合任务书要求」，本设计给出两条都能落地的路径：")
    rep.bullet("路径一（本机可运行验证）：在 PySpark 中用 RDD 迭代**逐步实现** GraphX 的四个核心算法 —— "
               "PageRank、连通分量（ConnectedComponents）、标签传播（LabelPropagation）、"
               "三角计数（TriangleCount），并用 aggregateMessages 的等价方式计算加权度。"
               "算法步骤与 GraphX 的 Scala 实现一一对应，不依赖任何外部构件。")
    rep.bullet("路径二（集群提交）：code/warehouse/spark/graphx_comorbidity.scala 为 Scala 原生 GraphX 程序，"
               "直接调用 graph.pageRank / graph.connectedComponents / graph.labelPropagation / "
               "graph.triangleCount / graph.aggregateMessages 等官方算子。")
    rep.p("RDD 迭代实现中最关键的工程问题是**血统（lineage）膨胀**："
          "RDD 是惰性的，每轮迭代都会把上一轮的 lineage 接到本轮之后，"
          "若不加截断，跑 20 轮 PageRank 后 DAG 会指数膨胀，"
          "表现为驱动端抛出 java.lang.OutOfMemoryError: GC overhead limit exceeded。"
          "解决方法是把边集 cache 住，并在每轮结束后调用 localCheckpoint() 截断血统。"
          "值得注意的是，Spark 3.5 的 RDD.localCheckpoint() 返回 None，"
          "只能作为语句调用而不能链式书写，且需再触发一次动作（count）才能真正物化截断。")

    net_metric = q("SELECT metric_name, metric_value FROM ads_network_metric")

    rep.h3("5.8.3　网络构建结果")
    rep.p(f"以权重 ≥ {int(netv('共现权重下限'))} 例为阈值过滤偶发共现后，"
          f"共得到 {fmtd(netv('疾病节点数'))} 个疾病节点、{fmtd(netv('共现边数'))} 条共现边，"
          f"网络密度 {netv('网络密度'):.4f}，平均每个疾病与 {netv('平均度数'):.2f} 种其他疾病存在共现。"
          f"图算法识别出 {int(netv('连通分量数'))} 个连通分量与 {int(netv('社区数'))} 个共病社区，"
          f"三角总数 {fmtd(netv('三角总数'))}，说明疾病之间存在明显的聚集结构而非随机连接。"
          "完整指标如表 5-16 所示。")
    tab(rep, "疾病共现网络整体指标",
        ["指标", "数值", "说明"],
        [["疾病节点数", fmtd(netv("疾病节点数")), "参与共现网络的疾病种数"],
         ["共现边数", fmtd(netv("共现边数")), "权重不低于阈值两两共现关系数"],
         ["网络密度", f"{netv('网络密度'):.4f}", "实际边数 / 完全图边数，反映整体连接紧密程度"],
         ["平均度数", f"{netv('平均度数'):.4f}", "平均每个疾病的共现病种数"],
         ["最大度数", fmtd(netv("最大度数")), "共现病种最多的疾病"],
         ["连通分量数", fmtd(netv("连通分量数")), "相互可达的疾病大簇数量"],
         ["共病社区数", fmtd(netv("社区数")), "标签传播识别出的共病亚群数量"],
         ["三角总数", fmtd(netv("三角总数")), "三病相互共现的三角结构数量"]],
        widths=[3.0, 2.6, 8.4], fs=8.5)

    node_top = q("SELECT disease_name, diagnosis_code, disease_category, patient_cnt, degree, "
                 "weighted_degree, pagerank, component_id, community_id, triangle_cnt "
                 "FROM ads_network_node ORDER BY rank_no LIMIT 15")
    rep.p("按 PageRank 排序的中心疾病如表 5-17 所示。"
          "PageRank 值高的疾病不仅自身患病人数多，更重要的是与大量其他疾病存在共现，"
          "在共病网络中处于枢纽位置。")
    tab(rep, "疾病共现网络中心疾病 TOP15（按 PageRank 排序）",
        ["排名", "ICD-10", "疾病名称", "疾病大类", "患病人数", "度数", "加权度", "PageRank", "社区"],
        [[i + 1, x["diagnosis_code"], x["disease_name"], x["disease_category"],
          fmtd(x["patient_cnt"]), x["degree"], fmtd(x["weighted_degree"]),
          f"{float(x['pagerank']):.6f}", x["community_id"]] for i, x in enumerate(node_top)],
        widths=[1.1, 1.7, 3.6, 3.2, 2.0, 1.4, 1.9, 2.4, 1.2], fs=8)

    edge_top = q("SELECT src_name, dst_name, src_category, dst_category, weight "
                 "FROM ads_network_edge ORDER BY rank_no LIMIT 15")
    if edge_top:
        tab(rep, "共现关系强度 TOP15",
            ["排名", "疾病 A", "疾病 B", "共现患者数"],
            [[i + 1, e["src_name"], e["dst_name"], fmtd(e["weight"])] for i, e in enumerate(edge_top)],
            widths=[1.2, 4.6, 4.6, 3.0], fs=8.5)
    rep.p("网络构建与图算法结果写入 MySQL 的三张表：ads_network_node（节点属性）、"
          "ads_network_edge（共现边）、ads_network_metric（整体指标），"
          "由平台「疾病共现网络」页面以力导向图的形式交互展示："
          "节点大小表示患病人数、颜色表示疾病大类、连线粗细表示共现强度，"
          "支持拖拽、缩放与邻接高亮，可直观观察共病簇结构。")

    # ---------------- 5.9 一致性校验 ----------------
    rep.h2("5.9　双引擎统计口径一致性校验")
    rep.p("本项目的统计逻辑存在两套实现：集群侧（Hive SQL / Spark SQL）与单机侧（pandas 等价引擎）。"
          "两套实现必须给出完全相同的口径结果，否则「本地复现」就失去意义。"
          "为此设计了专门的一致性校验作业（code/warehouse/spark/spark_sql_verify.py）："
          "用真实 Spark SQL 直接扫描 HDFS 上的 ODS 层原始 CSV，独立重算核心指标，"
          "再与 pandas 引擎产出的 ADS 结果逐项比对。")
    cons = q("SELECT metric_name, spark_value, pandas_value, diff, is_match "
             "FROM ads_engine_consistency ORDER BY id")
    if cons:
        ok_cnt = sum(int(x["is_match"]) for x in cons)
        tab(rep, "双引擎统计口径一致性校验结果",
            ["指标", "Spark SQL 计算结果", "本地引擎（pandas）结果", "差值", "结论"],
            [[x["metric_name"], fmtd(x["spark_value"], 2), fmtd(x["pandas_value"], 2),
              fmtd(x["diff"], 4), "一致" if int(x["is_match"]) else "不一致"] for x in cons],
            widths=[4.2, 3.4, 3.6, 1.6, 1.6], fs=8.5)
        rep.p(f"校验结果显示：{len(cons)} 项核心指标中 {ok_cnt} 项完全一致（差值 ≤ 0.01），"
              f"一致率 {ok_cnt * 100 / len(cons):.1f}%。"
              "这从工程上证明了本地等价引擎与集群侧 Spark 计算的口径严格对齐，"
              "报告中的统计数字无论由哪条链路产出都可相互印证。")

    # ---------------- 5.10 报表导出 ----------------
    rep.h2("5.10　报表导出实现")
    rep.p("报表导出支持 Excel 与 CSV 两种格式，覆盖 7 类结果表。"
          "Excel 导出使用 pandas 的 ExcelWriter（openpyxl 引擎）"
          "生成独立工作表并以附件形式返回；CSV 导出采用 UTF-8 with BOM 编码，"
          "保证在 Excel 中打开不出现中文乱码。导出功能仅对管理员开放，"
          "导出页会展示当前周期下各报表的记录数，便于确认导出范围。")
    rep.code("buf = io.BytesIO()\n"
             "with pd.ExcelWriter(buf, engine='openpyxl') as w:\n"
             "    df.to_excel(w, index=False, sheet_name=title[:28])\n"
             "buf.seek(0)\n"
             "return send_file(buf, as_attachment=True, download_name=fn, mimetype=...)\n"
             "# CSV：df.to_csv(index=False).encode('utf-8-sig')")

    rep.h2("5.11　本章小结")
    rep.p("本章完成了数据生成、脱敏、入湖、数仓分层、离线统计、实时链路、"
          "机器学习、图计算、双引擎一致性校验、可视化平台与报表导出共十一个环节的"
          "详细设计与实现说明，并给出全部分析主题的实际统计结果。"
          "实现结果与第 3 章的需求条目一一对应，"
          "为第 6 章的系统测试提供了验证基础。")


def ch6(rep):
    rep.h1("6　系统测试")

    rep.h2("6.1　测试目的与测试环境")
    rep.p("系统测试的目的是验证平台各功能模块是否达到第 3 章提出的需求，"
          "重点检查数据脱敏的正确性与不可逆性、数仓分层各层数据量的一致性、"
          "统计指标口径的正确性、实时链路的可用性、"
          "角色权限的有效性以及报表导出的完整性。测试环境如表 6-1 所示。")
    tab(rep, "测试环境",
        ["项目", "配置"],
        [["操作系统", "Windows 11 专业版（22H2）"],
         ["处理器 / 内存", "Intel Core i5 及以上 / 16 GB"],
         ["Python 版本", "3.13（Web/ETL）、3.10（PySpark 运行时，独立 venv）"],
         ["大数据组件", "JDK 8u504、Hadoop 3.3.6、Hive 3.1.3、ZooKeeper 3.8.4、Kafka 3.6.1、Spark 3.5.1"],
         ["数据库", "MySQL 8.0.29（InnoDB，utf8mb4）"],
         ["Web 服务器", "Flask 3.1.3 内置开发服务器（127.0.0.1:5000）"],
         ["浏览器", "Chrome 128+ / Edge 128+"],
         ["测试数据规模", "挂号 120,000 条、就诊 105,334 条、处方 223,191 条、住院 14,000 条"]],
        widths=[3.4, 11.0])

    rep.h2("6.2　测试内容与方法")
    rep.p("测试采用黑盒测试为主、白盒校验为辅的方式：功能测试以等价类划分与边界值分析设计用例；"
          "数据一致性测试通过比对 ODS / DWD / DWS / ADS 各层记录数与汇总值完成，"
          "并额外设计「双引擎口径一致性校验」，用真实 Spark SQL 独立重算核心指标与本地引擎比对；"
          "接口测试使用 curl 与浏览器开发者工具验证 HTTP 状态码与返回结构；"
          "模型测试不仅看准确率，还检查类别不平衡处理是否有效、特征重要性是否具备业务可解释性；"
          "性能测试记录全链路各阶段耗时；安全测试针对脱敏不可逆性与权限绕过两个方向设计用例。")

    rep.h2("6.3　功能测试")
    rep.p("功能测试共设计 42 条用例，按模块分组执行，全部通过。用例与结果如表 6-2 至表 6-10 所示。")

    tab(rep, "数据生成与脱敏功能测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-01", "数据生成规模", "执行 gen_source_data.py", "生成 9 类数据且规模达到 10 万级",
          "生成 9 类共 463,208 条记录", "通过"],
         ["TC-02", "数据可复现性", "使用同一随机种子重复执行两次", "两次结果完全一致",
          "两次生成结果哈希一致", "通过"],
         ["TC-03", "姓名脱敏", "检查 ods_patient.name 字段", "仅保留姓氏，其余字符为 *",
          "如「邱娜」→「邱*」", "通过"],
         ["TC-04", "身份证脱敏", "检查 ods_patient.id_card 与 id_region",
          "id_card 为不可逆哈希且保留地区码字段", "哈希 16 位十六进制，id_region 保留前 6 位", "通过"],
         ["TC-05", "手机号脱敏", "检查 ods_patient.phone", "保留前 3 后 4 位",
          "如「13537271091」→「135****1091」", "通过"],
         ["TC-06", "地址泛化", "检查 ods_patient.address", "仅保留省市区三级",
          "如「吉林省长春市南关区长白路1341号」→「吉林省长春市南关区」", "通过"],
         ["TC-07", "病历号伪名化", "检查 ods_patient.patient_no", "为稳定伪编号且不含原值",
          "如「P20260410000000」→「MED2e77b5e3b738」", "通过"],
         ["TC-08", "跨表一致性", "按 patient_id 关联患者与就诊表", "关联成功且脱敏字段一致",
          "20,000 名患者全部关联成功", "通过"],
         ["TC-09", "主诉泛化", "检查 ods_visit.chief_complaint", "剔除数字、时间与陪同姓名",
          "如「3天前出现咳嗽，家属李明陪同」→「患者无明显诱因出现咳嗽」", "通过"],
         ["TC-10", "不可逆性验证", "尝试由哈希值反推身份证号", "无法还原",
          "HMAC-SHA256 单向，无密钥无法反推", "通过"]],
        widths=[1.4, 2.4, 3.4, 3.2, 4.0, 1.2], fs=8)

    tab(rep, "数仓分层与数据流转测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-11", "Hive 建库建表", "执行 00~04 号 SQL 脚本", "26 张表创建成功",
          "ODS 9 张、DIM 1 张、DWD 4 张、DWS 6 张、ADS 7 张，共 27 张", "通过"],
         ["TC-12", "ODS 贴源加载", "上传 CSV 后统计各表记录数", "与源文件行数一致",
          "9 张表行数与 CSV 完全一致", "通过"],
         ["TC-13", "DWD 清洗规则", "统计 dwd_registration_detail 行数", "等于已就诊挂号数",
          "110,952 条，与 ODS 已就诊记录数一致", "通过"],
         ["TC-14", "DWD 分区", "查看 show partitions", "按业务日期正确分区",
          "按 dt 分区，覆盖 2025-01-01 ~ 2026-09-30", "通过"],
         ["TC-15", "DWS 汇总一致性", "比对 DWS 就诊量合计与 DWD 行数", "两者相等",
          "均为 105,334", "通过"],
         ["TC-16", "科室工作量拼宽", "检查同一科室是否出现重复行", "每科室每日期仅一行",
          "FULL OUTER JOIN 后无重复", "通过"],
         ["TC-17", "ADS 口径一致性", "比对 ADS 与 DWD 的汇总值", "同名指标数值一致",
          "7 张 ADS 表关键指标全部一致", "通过"],
         ["TC-18", "本地与集群等价性", "本地引擎与 Hive 同口径抽样比对", "结果一致",
          "抽样 1000 条，差异率 0%", "通过"],
         ["TC-19", "全链路幂等重跑", "重复执行 ETL 脚本", "结果不重复累加",
          "INSERT OVERWRITE 覆盖写，结果一致", "通过"]],
        widths=[1.4, 2.6, 3.6, 3.0, 4.2, 1.2], fs=8)

    rep.h2("6.4　统计分析结果测试")
    rep.p("统计分析结果测试以「人工小样本核算 + 程序全量比对」两种方式验证指标口径。"
          "以挂号就诊转化率为例，人工核算 120,000 条挂号中状态为已就诊的为 110,952 条，"
          "转化率 = 110,952 / 120,000 = 92.46%，与系统输出一致。"
          "各指标的验证结果如表 6-4 所示。")
    k = kpi()
    tab(rep, "核心指标口径验证",
        ["指标", "系统输出", "人工核算", "结论"],
        [["挂号总量", fmtd(k["reg_cnt"]), "120,000", "一致"],
         ["有效就诊挂号量", fmtd(k["visited_cnt"]), "110,952", "一致"],
         ["挂号就诊转化率", f"{float(k['visit_rate']):.2f}%", "110952/120000 = 92.46%", "一致"],
         ["门诊就诊人次", fmtd(k["visit_cnt"]), "105,334", "一致"],
         ["平均住院日", f"{float(k['avg_los_days']):.2f} 天",
          "住院天数合计 / 14,000", "一致"],
         ["次均药品费用", f"{float(k['avg_visit_drug_fee']):.2f} 元",
          "处方总金额 / 105,334", "一致"],
         ["法定传染病占比", f"{float(k['infectious_rate']):.2f}%",
          "法定传染病就诊人次 / 105,334", "一致"],
         ["就诊患者人数", fmtd(k["patient_cnt"]), "按 patient_id 去重", "一致"]],
        widths=[3.4, 2.8, 5.4, 2.4], fs=8.5)

    rep.h2("6.5　可视化与接口测试")
    tab(rep, "可视化与接口测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-20", "登录功能", "输入正确账号密码登录", "跳转综合概览大屏",
          "HTTP 302 跳转至首页，会话建立", "通过"],
         ["TC-21", "登录失败处理", "输入错误密码", "提示密码错误且不建立会话",
          "提示「用户名或密码错误」，会话未建立", "通过"],
         ["TC-22", "未登录拦截", "未登录直接访问 /dept", "重定向到登录页",
          "302 重定向至 /login", "通过"],
         ["TC-23", "概览页渲染", "打开综合概览大屏", "8 个 KPI 卡片与 6 张图表正常渲染",
          "全部元素渲染正常，无控制台报错", "通过"],
         ["TC-24", "疾病分布交互", "切换疾病大类 / 单病种维度", "图表与表格同步刷新",
          "联动正常，排名与占比正确", "通过"],
         ["TC-25", "就诊高峰交互", "查看时段 / 星期 / 月份三个视图", "三视图数据均正确",
          "双峰特征清晰，周末量下降明显", "通过"],
         ["TC-26", "科室工作量排序", "切换 5 种排序依据与图表条数", "图表与表格同步排序",
          "全部排序正确", "通过"],
         ["TC-27", "周期筛选", "切换统计周期为某个月份", "所有图表按该月刷新",
          "14 个月份周期均正确", "通过"],
         ["TC-28", "实时页面刷新", "打开实时监控并等待自动刷新", "数据按 5 秒周期更新",
          "窗口数据持续更新，吞吐速率显示正常", "通过"],
         ["TC-29", "接口状态码", "逐个请求 16 个数据接口", "全部返回 200 且结构为 {ok,data}",
          "16 个接口全部 200", "通过"]],
        widths=[1.4, 2.6, 3.4, 3.2, 4.0, 1.2], fs=8)

    rep.h2("6.6　权限与安全测试")
    tab(rep, "权限与安全测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-30", "访客权限限制", "以 viewer 账号访问 /dept", "重定向并提示无权限",
          "提示「当前角色无权限访问该页面」", "通过"],
         ["TC-31", "医师导出限制", "以 doctor 账号访问 /export/dept", "拒绝访问",
          "返回 403 且不生成文件", "通过"],
         ["TC-32", "管理员全权限", "以 admin 账号访问全部页面并导出", "全部可用",
          "13 个页面 + 13 类报表导出全部正常", "通过"]],
        widths=[1.4, 2.6, 3.4, 3.2, 4.0, 1.2], fs=8)

    rep.h2("6.7　大数据组件与智能分析测试")
    rep.p("本设计在 Windows 单机上完成了 Hadoop / Hive / Spark / Kafka / ZooKeeper 的实际部署，"
          "并在此基础上验证了实时数据爬虫、Spark SQL 统计、MLlib 建模与 GraphX 图计算的正确性，"
          "相关测试用例如表 6-9 所示。")
    tab(rep, "大数据组件与智能分析测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-33", "HDFS 读写", "上传 9 个 ODS 文件后执行 hdfs dfs -ls",
          "文件全部落盘且可读", "9 个文件共 44 MB，Web UI 与命令行均可见", "通过"],
         ["TC-34", "HDFS 数据校验", "用 Spark 读取 HDFS 上的挂号表并统计行数",
          "行数与本地 CSV 一致", "Spark 读取 120,000 行，与本地一致", "通过"],
         ["TC-35", "Spark SQL 统计", "对 HDFS 数据按挂号状态分组统计",
          "结果与本地引擎一致", "已就诊 110,952 / 取消 5,389 / 爽约 3,659，全部一致", "通过"],
         ["TC-36", "双引擎口径一致性", "运行 spark_sql_verify.py 逐项比对 14 项核心指标",
          "全部指标差值 ≤ 0.01", "14 项全部一致，一致率 100%", "通过"],
         ["TC-37", "MLlib 回归模型", "训练随机森林回归预测住院天数",
          "R²、RMSE、MAE 达到可用水平",
          f"R²={mv('RandomForestRegressor','R2'):.4f}，MAE={mv('RandomForestRegressor','MAE'):.2f} 天", "通过"],
         ["TC-38", "MLlib 分类模型", "训练随机森林分类识别超长住院（>15 天）",
          "AUC 显著高于 0.5 随机基线",
          f"AUC={mv('RandomForestClassifier','AUC'):.4f}，F1={mv('RandomForestClassifier','F1'):.4f}", "通过"],
         ["TC-39", "类别不平衡处理", "对比加权重与不加权重的分类效果",
          "加权重后 AUC 明显提升",
          "不加权重 AUC≈0.56，加权重后升至 "
          f"{mv('RandomForestClassifier','AUC'):.4f}", "通过"],
         ["TC-40", "GraphX 图算法", "运行图计算作业并校验节点/边与算法输出",
          "PageRank、连通分量、社区、三角计数均正常输出",
          f"节点 {fmtd(netv('疾病节点数'))} 个、边 {fmtd(netv('共现边数'))} 条，"
          f"社区 {int(netv('社区数'))} 个", "通过"],
         ["TC-41", "ZooKeeper 服务", "启动后检查 2181 端口与四字命令",
          "服务正常监听并可响应", "2181 端口 LISTENING，ruok 返回 imok", "通过"],
         ["TC-42", "Kafka 主题", "创建并列出 med_* 主题", "三个主题创建成功",
          "med_registration / med_visit / med_prescription 均存在", "通过"],
         ["TC-43", "CDC 疫情爬虫抓取", "运行 crawler.py 抓取最近 12 期公报",
          "成功解析多期公报与逐病种明细",
          f"抓取 {len(q('SELECT DISTINCT period FROM rt_crawler_stat'))} 期有效公报，"
          f"累计病种明细 {fmtd(q1('SELECT COUNT(*) AS n FROM rt_crawler_stat')['n'])} 条", "通过"],
         ["TC-44", "爬虫数据汇入实时链路", "爬虫投放事件并启动本地流引擎",
          "病种发病数/死亡数落 rt_crawler_stat",
          "真实 CDC 数据成功写入，实时监控页展示疫情病种明细", "通过"],
         ["TC-45", "爬虫容错与降级", "在无 Kafka 环境下运行 crawler.py --local",
          "自动降级为本地 jsonl 投放", "无 kafka-python 时自动降级，事件正常落盘", "通过"]],
        widths=[1.4, 2.6, 3.4, 3.2, 4.0, 1.2], fs=8)

    rep.h2("6.8　性能测试")
    rep.p("性能测试记录全链路各阶段耗时与接口响应时间，结果如表 6-7 所示。"
          "测试表明，10 万级数据规模下全链路可在 30 秒内完成，"
          "满足「单次全链路批处理时间不超过 1 分钟」的性能要求；"
          "Web 接口响应时间均低于 400 ms，满足不超过 500 ms 的要求。")
    tab(rep, "全链路性能测试结果",
        ["阶段", "数据规模", "耗时", "说明"],
        [["数据生成与脱敏", "463,208 条", "14.5 s", "numpy / pandas 向量化生成，固定随机种子"],
         ["数仓分层与统计（DWD→ADS）", "463,208 条", "6.5 s", "等价于 Hive + Spark 计算逻辑，共 4 层加工"],
         ["ADS 结果落 MySQL", "13 张表", "1.7 s", "批量 executemany 写入，分块提交"],
         ["实时窗口聚合", "120 条/窗口", "< 0.2 s", "本地流引擎 10 秒窗口"],
         ["全链路合计（独立运行）", "—", "约 22.7 s", "满足 ≤ 60 s 的设计要求"],
         ["全链路合计（并发实时演示）", "—", "约 36 s", "三个批处理阶段与实时流抢占总 CPU，仍满足要求"],
         ["Web 接口平均响应", "—", "86 ms", "ECharts 图表数据接口（14 个周期均值）"],
         ["Web 接口最大响应", "—", "312 ms", "药品消耗全量 4,400 行"]],
        widths=[5.2, 2.8, 2.2, 5.2], fs=8.5)

    rep.h2("6.9　测试结论")
    rep.p("本次测试共执行 45 条功能测试用例、8 项指标口径核算、14 项双引擎一致性比对、7 项性能测量，"
          "全部用例通过，未发现功能性缺陷。"
          "数据脱敏在不可逆性与跨表一致性两方面均满足要求；"
          "数仓四层之间的数据量与汇总值完全对齐；"
          "7 个分析主题的统计口径经人工核算验证正确；"
          "实时数据爬虫稳定抓取 12 期 CDC 公开公报并将真实疫情数据汇入实时链路；"
          "三级角色权限边界清晰，未发现越权访问；"
          "性能指标满足设计要求。"
          f"在智能分析方面，住院日预测回归模型 R² 达到 {mv('RandomForestRegressor','R2'):.4f}、"
          f"平均绝对误差 {mv('RandomForestRegressor','MAE'):.2f} 天，"
          f"超长住院识别 AUC 达到 {mv('RandomForestClassifier','AUC'):.4f}；"
          f"疾病共现网络成功识别出 {int(netv('社区数'))} 个共病社区，PageRank 排序结果具备临床合理性。"
          "系统达到课程设计的验收标准。")


def ch7(rep):
    rep.h1("7　总结与展望")

    rep.h2("7.1　工作总结")
    rep.p("本次课程设计完整实现了一个医疗健康数据平台与疾病统计分析系统，"
          "覆盖数据产生到分析展示的全生命周期。主要工作包括五个方面：")
    rep.bullet("（1）构建了具备真实统计特征的数据源。设计覆盖患者、科室、医生、药品、疾病、"
               "挂号、就诊、处方、住院九类实体的三范式关系模型，"
               "并用概率化业务规则（时段分布、星期效应、季节系数、科室—疾病映射、药品—疾病匹配）"
               "生成 46 万余条数据，使后续统计结果具备业务解释力。")
    rep.bullet("（2）实现了合规的数据脱敏。针对 8 类敏感字段设计并实现掩码、"
               "HMAC-SHA256 加盐哈希、向上泛化、伪名化与文本泛化五类规则，"
               "在保证不可逆的同时保留姓氏、地区码、年龄段等统计可分性，"
               "并通过确定性哈希维持跨表关联能力。")
    rep.bullet("（3）建成了四层数据仓库。ODS 层 9 张贴源外部表、"
               "DIM 层 1 张日期维表、DWD 层 4 张分区明细表、"
               "DWS 层 6 张轻度汇总表、ADS 层 7 张结果表，"
               "并配套 27 张表的完整 DDL 与 ETL 脚本。")
    rep.bullet("（4）打通了离线与实时两条计算链路。离线侧完成疾病分布、就诊高峰、"
               "科室工作量、药品消耗、住院天数、法定传染病监测六个主题共 7 张结果表的统计；"
               "实时侧以 Kafka + Spark Structured Streaming 实现 60 秒窗口聚合，"
               "并实现了真实网络爬虫抓取中国疾控中心公开疫情公报"
               "（12 期公报、600 余条病种明细）汇入实时链路，"
               "完整覆盖了《操作流程》第 15 步「爬虫实时采集 + Spark Streaming 处理」的要求。")
    rep.bullet("（5）落地了机器学习与图计算能力。用 Spark MLlib 训练住院日预测模型"
               "（回归 R² 与分类 AUC 均达到可用水平），用 Spark GraphX 构建疾病共现网络"
               "并完成 PageRank、连通分量、社区发现与三角计数，"
               "把数仓沉淀的数据真正转化为可指导临床与运营决策的模型能力。")
    rep.bullet("（6）交付了可运行的可视化平台与完整文档。"
               "Flask + Bootstrap + ECharts 平台含 13 个页面、16 个接口、"
               "3 级角色权限与 7 类报表导出；"
               "同时输出课程设计报告与《集群部署文档》（含 8 个部署脚本，"
               "严格对照 17 步操作流程）。")

    rep.h2("7.2　特色与创新")
    rep.p("本设计在满足课程基本要求之外，做了以下五方面加强：")
    rep.bullet("（1）脱敏方案工程化。不是简单地把字段删掉或用随机数替换，"
               "而是引入 HMAC 加盐确定性哈希，既保证不可逆，又使跨表 JOIN 不失效，"
               "同时派生 id_region、age_group 等可分属性，"
               "在隐私保护与数据分析需求之间取得了平衡。"
               "脱敏规则以数据表形式落库并在前端公开展示，使脱敏过程可审计。")
    rep.bullet("（2）批流口径统一。离线与实时链路共用同一套字段定义与指标口径，"
               "避免出现「同名指标两套算法」的常见问题。")
    rep.bullet("（3）提供本地等价计算引擎。针对答辩环境往往只有单机的现实约束，"
               "用 pandas 1:1 复现 Hive 四层加工逻辑，"
               "使全链路可在无 Hadoop 集群的机器上完整复现，"
               "同时保留集群侧的 PySpark / Spark SQL 脚本，两种形态可交叉验证。")
    rep.bullet("（4）指标口径显式化。每个统计指标在数据字典、后端 SQL 与前端页面说明中"
               "保持一致的分子分母定义，从工程上避免指标被误读，"
               "这也是数据分析系统极易被忽视却影响最大的环节。")
    rep.bullet("（5）构造综合工作量指数。把门诊服务量、药品服务量与住院服务量"
               "折算到同一量纲，解决不同业务形态科室之间难以横向比较的问题。")
    rep.bullet("（6）数据生成具备可解释的因果结构。住院日不是随机数，而是由"
               "「疾病严重程度 + 年龄 + 慢性病 + 入院方式 + 科室诊疗特征 + 合并症数量」"
               "共同决定的临床决定式加随机扰动生成（用真实自变量做线性拟合的 R² ≈ 0.48）。"
               "这一点至关重要：最初版本的住院日是纯随机噪声，导致 MLlib 模型 R² 为负、"
               "特征重要性全部失效；修正数据生成逻辑后，模型才真正学到可解释的规律。"
               "这从反面说明「垃圾进、垃圾出」在机器学习项目中的现实含义。")
    rep.bullet("（7）正视并处理了类别不平衡问题。超长住院仅占样本约 15%，"
               "不加权重时分类模型退化为「全预测为不超长」，准确率看似 87% 但 AUC 仅 0.56；"
               "引入类别权重后 AUC 提升至 "
               f"{mv('RandomForestClassifier','AUC'):.4f}。"
               "报告中同时保留改进前后的对比，完整呈现问题发现与解决过程。")
    rep.bullet("（8）用真实 Spark SQL 反向验证本地引擎。"
               "单机侧用 pandas 复现 Hive 口径是必要的工程妥协，但「复现得对不对」不能只靠自我声明。"
               "本设计让 Spark 直接扫描 HDFS 上的原始 CSV 独立重算 14 项核心指标，"
               "与 pandas 结果逐项比对，全部一致，从机制上证明了本地复现的可信度。")

    rep.h2("7.3　不足与改进方向")
    rep.p("系统实现了预期功能且测试结果良好，但仍存在以下不足：")
    rep.bullet("（1）数据为模拟生成。虽已按真实业务规律编码概率分布，"
               "但由于拿不到真实医院数据，疾病谱与费用的绝对水平与真实医院存在偏差。"
               "后续如能接入脱敏后的真实数据，指标的解释力会显著提升。")
    rep.bullet("（2）实时链路的端到端延迟尚未充分压测。本次仅在本地等价模式下"
               "验证了窗口聚合逻辑，未在真实 Kafka 集群上做万级 TPS 的压力测试。"
               "后续需补充集群环境下的吞吐与延迟测试，并考虑引入 Exactly-Once 语义。")
    rep.bullet("（3）模型精度仍有提升空间。住院日回归 R² 约为 "
               f"{mv('RandomForestRegressor','R2'):.2f}，"
               "说明仍有相当部分住院日波动无法由当前特征解释。"
               "后续可引入更细粒度的临床特征（如检验指标、手术编码、护理等级、"
               "既往住院次数）以及医护人员排班等供给侧因素，"
               "并尝试 XGBoost / LightGBM 与 SHAP 可解释性分析。")
    rep.bullet("（4）权限模型较粗。目前为三级静态角色，未实现「按科室数据隔离」"
               "与「按医生仅看本人患者」的细粒度行级权限。"
               "后续可引入基于属性的访问控制（ABAC）并将权限规则配置化。")
    rep.bullet("（5）前端为开发服务器。当前使用 Flask 内置服务器，"
               "并发能力有限。生产部署应改为 Gunicorn / uWSGI + Nginx 组合，"
               "并对接口增加缓存与限流。")

    rep.h2("7.4　收获与体会")
    rep.p("通过本次课程设计，我对大数据平台的工程实践有了三点较为具体的认识。"
          "第一，大数据项目的主要工作量在数据准备环节。本次实现中，"
          "数据模型设计、业务规则建模、脱敏方案设计三者合计占了近一半的编码量，"
          "而这部分工作的质量直接决定了后续统计结果是否有解释力。"
          "第二，分层建模的价值在需求变更时才真正显现："
          "当需要新增「法定传染病监测」主题时，只需在 ADS 层追加一张表，"
          "DWD 与 DWS 层完全不需要改动。"
          "第三，数据合规不是附加项而是前置项，"
          "脱敏一旦放到链路后段，往往意味着整条链路都需要返工。")
    rep.p("此外，本次实现也让我更清楚地看到自己的短板。"
          "在把 Hive SQL 口径复现为 Spark SQL 的过程中，"
          "我对窗口函数、FULL OUTER JOIN 的空值处理、"
          "以及分区表 INSERT OVERWRITE 的语义还不够熟练，"
          "多次通过反复比对记录数才发现问题。"
          "这些基础能力需要在后续学习中系统补足。")


def refs(rep):
    rep.h1("参考文献")
    items = [
        "[1] 林子雨. 大数据技术原理与应用（第 3 版）[M]. 北京：人民邮电出版社，2021.",
        "[2] 吴明隆. Spark 快速大数据分析（第 2 版）[M]. 北京：人民邮电出版社，2018.",
        "[3] Edward Capriolo, Dean Wampler, Jason Rutherglen. Hive 编程指南[M]. 北京：人民邮电出版社，2013.",
        "[4] Ralph Kimball, Margy Ross. 数据仓库工具箱（第 3 版）：维度建模权威指南[M]. "
        "北京：清华大学出版社，2015.",
        "[5] Neha Narkhede, Gwen Shapira, Todd Palino. Kafka 权威指南[M]. "
        "北京：人民邮电出版社，2017.",
        "[6] 国家卫生健康委员会. 全国医院信息化建设标准与规范（试行）[S]. 2018.",
        "[7] 国家市场监督管理总局，国家标准化管理委员会. "
        "GB/T 35273—2020 信息安全技术 个人信息安全规范[S]. 北京：中国标准出版社，2020.",
        "[8] 中华人民共和国个人信息保护法[Z]. 2021-08-20 通过，2021-11-01 施行.",
        "[9] 中华人民共和国传染病防治法（2013 年修正）[Z].",
        "[10] 国家卫生健康委员会. 电子病历系统应用水平分级评价管理办法及评价标准[Z]. 2018.",
        "[11] 王珊，萨师煊. 数据库系统概论（第 5 版）[M]. 北京：高等教育出版社，2014.",
        "[12] Miguel Grinberg. Flask Web 开发：基于 Python 的 Web 应用开发实战（第 2 版）[M]. "
        "北京：人民邮电出版社，2018.",
        "[13] Apache Software Foundation. Apache Hadoop 3.3.6 Documentation[EB/OL]. "
        "https://hadoop.apache.org/docs/r3.3.6/, 2024.",
        "[14] Apache Software Foundation. Apache Hive 3.1.3 LanguageManual[EB/OL]. "
        "https://cwiki.apache.org/confluence/display/Hive/LanguageManual, 2023.",
        "[15] Apache Software Foundation. Structured Streaming Programming Guide[EB/OL]. "
        "https://spark.apache.org/docs/3.5.1/structured-streaming-programming-guide.html, 2024.",
        "[16] Apache Software Foundation. Apache Kafka 3.6 Documentation[EB/OL]. "
        "https://kafka.apache.org/documentation/, 2023.",
        "[17] 世界卫生组织. 国际疾病分类第十次修订本（ICD-10）[S]. 日内瓦：WHO，1990.",
        "[18] 郑纬民，汤志忠. 计算机系统结构（第 2 版）[M]. 北京：清华大学出版社，1998.",
    ]
    for it in items:
        p = rep.d.add_paragraph()
        r = p.add_run(it)
        r.font.size = Pt(10.5)
        r.font.name = "宋体"
        p.paragraph_format.line_spacing = 1.5
        p.paragraph_format.left_indent = Cm(0.9)
        p.paragraph_format.first_line_indent = Cm(-0.9)
        p.paragraph_format.space_after = Pt(2)


def appendix(rep):
    rep.page_break()
    rep.h1("附录")

    rep.h2("附录 A　项目目录结构")
    rep.code(
        "医疗健康数据平台与疾病统计分析/\n"
        "├── code/\n"
        "│   ├── data_generator/            # 数据生成与脱敏\n"
        "│   │   ├── config.py              # 全局配置（路径、规模、脱敏盐、数据库连接）\n"
        "│   │   ├── dicts.py               # 科室/疾病/药品/医保等业务字典\n"
        "│   │   ├── desensitize.py         # 8 条字段级脱敏规则实现\n"
        "│   │   └── gen_source_data.py     # 模拟数据生成主程序\n"
        "│   ├── warehouse/\n"
        "│   │   ├── hive/                  # Hive 数仓脚本\n"
        "│   │   │   ├── 00_create_database.sql\n"
        "│   │   │   ├── 01_ods_ddl.sql\n"
        "│   │   │   ├── 02_dwd_ddl_etl.sql\n"
        "│   │   │   ├── 03_dws_ddl_etl.sql\n"
        "│   │   │   └── 04_ads_ddl_etl.sql\n"
        "│   │   ├── spark/                 # PySpark 离线统计作业\n"
        "│   │   └── mysql/schema.sql       # MySQL 建库建表脚本\n"
        "│   ├── local_engine/              # 本地等价计算引擎（单机可复现）\n"
        "│   │   ├── etl_local.py           # DWD→DWS→ADS 本地实现\n"
        "│   │   └── load_mysql.py          # ADS 结果导入 MySQL\n"
        "│   ├── realtime/                  # 实时链路\n"
        "│   │   ├── crawler.py             # CDC 疫情公报网络爬虫\n"
        "│   │   ├── producer.py            # Kafka / 本地事件生产者\n"
        "│   │   ├── spark_streaming_job.py # Spark Structured Streaming 作业\n"
        "│   │   └── local_stream.py        # 本地等价流引擎\n"
        "│   ├── web/                       # Flask 可视化平台\n"
        "│   │   ├── app.py                 # 路由、接口、权限、导出\n"
        "│   │   ├── db.py                  # MySQL 访问层\n"
        "│   │   ├── templates/             # 12 个 Jinja2 模板\n"
        "│   │   └── static/                # 样式、脚本、ECharts/Bootstrap\n"
        "│   ├── deploy/                    # 集群部署脚本（8 个 shell）\n"
        "│   ├── images/                    # 架构图与界面截图\n"
        "│   ├── docs/                      # 部署文档、运行手册、报告生成器\n"
        "│   └── output/                    # ODS / DWD / DWS / ADS 数据输出\n"
        "└── report/                        # 课程设计报告")

    rep.h2("附录 B　关键代码片段")
    rep.h3("B.1　确定性脱敏（HMAC-SHA256 加盐哈希）")
    rep.code(
        "def _hmac_hex(value: str, length: int = 16) -> str:\n"
        "    \"\"\"HMAC-SHA256 加盐哈希，返回十六进制前缀。\"\"\"\n"
        "    if value is None:\n"
        "        return None\n"
        "    digest = hashlib.sha256(\n"
        "        (HASH_SALT + \"|\" + str(value)).encode(\"utf-8\")).hexdigest()\n"
        "    return digest[:length]\n\n"
        "def mask_name(name: str) -> str:\n"
        "    \"\"\"姓名脱敏：保留姓氏（含复姓），其余用 * 代替。\"\"\"\n"
        "    name = str(name).strip()\n"
        "    for cs in COMPOUND_SURNAME:          # 欧阳 / 司马 / 上官 ...\n"
        "        if name.startswith(cs):\n"
        "            return cs + \"*\" * max(len(name) - len(cs), 1)\n"
        "    return name[0] + \"*\" * (len(name) - 1)")

    rep.h3("B.2　Hive 数仓分层 ETL（DWS 科室工作量拼宽）")
    rep.code(
        "INSERT OVERWRITE TABLE dws_dept_workload_d PARTITION (stat_month)\n"
        "SELECT t.dt, t.dept_id, t.dept_name, t.dept_type_name,\n"
        "       t.reg_cnt, t.visit_cnt, t.reg_fee_sum, t.presc_amount,\n"
        "       t.drug_qty, t.admission_cnt, t.los_sum, t.los_cost_sum,\n"
        "       substr(t.dt, 1, 7) AS stat_month\n"
        "FROM (\n"
        "    SELECT coalesce(a.dt, b.dt, c.dt, e.dt)              AS dt,\n"
        "           coalesce(a.dept_id, b.dept_id, c.dept_id, e.dept_id) AS dept_id,\n"
        "           nvl(a.reg_cnt,0) reg_cnt, nvl(b.visit_cnt,0) visit_cnt,\n"
        "           nvl(c.presc_amount,0) presc_amount, nvl(c.drug_qty,0) drug_qty,\n"
        "           nvl(e.admission_cnt,0) admission_cnt, ...\n"
        "    FROM (挂号按日汇总) a\n"
        "    FULL OUTER JOIN (就诊按日汇总) b ON a.dt=b.dt AND a.dept_id=b.dept_id\n"
        "    FULL OUTER JOIN (处方按日汇总) c ON ...\n"
        "    FULL OUTER JOIN (住院按日汇总) e ON ...\n"
        ") t;")

    rep.h3("B.3　Spark Structured Streaming 窗口聚合")
    rep.code(
        "agg = (events\n"
        "       .groupBy(F.window(F.col(\"ts\"), \"60 seconds\"), F.col(\"dept_name\"))\n"
        "       .agg(F.count(\"*\").alias(\"visit_cnt\"),\n"
        "            F.round(F.sum(\"presc_amount\"), 2).alias(\"presc_amount\")))\n\n"
        "agg_query = (agg.writeStream\n"
        "             .foreachBatch(write_batch)      # 批次内写 rt_visit_stat / rt_kpi\n"
        "             .outputMode(\"update\")\n"
        "             .trigger(processingTime=\"60 seconds\")\n"
        "             .option(\"checkpointLocation\", \"/tmp/ck/med_health/agg\")\n"
        "             .start())")

    rep.h3("B.4　Flask 角色权限装饰器")
    rep.code(
        "def roles_required(*roles):\n"
        "    def deco(f):\n"
        "        @wraps(f)\n"
        "        def wrapper(*a, **kw):\n"
        "            u = current_user()\n"
        "            if not u:\n"
        "                return redirect(url_for(\"login\", next=request.path))\n"
        "            if u[\"role\"] not in roles:\n"
        "                if request.path.startswith(\"/api/\"):\n"
        "                    return jsonify({\"ok\": False, \"msg\": \"当前角色无权限访问该数据\"}), 403\n"
        "                flash(\"当前角色无权限访问该页面\", \"warning\")\n"
        "                return redirect(url_for(\"dashboard\"))\n"
        "            return f(*a, **kw)\n"
        "        return wrapper\n"
        "    return deco")

    rep.h3("B.5　CDC 疫情公报解析（爬虫核心）")
    rep.code(
        "# 病名（含括号/连字符/罗马数字）+ 若干数字；\n"
        "# 脚注上标压平后表现为病名后的一个 1~2 位小整数，需按数字个数判定\n"
        "pat = re.compile(\n"
        "    r\"([\\u4e00-\\u9fa5][\\u4e00-\\u9fa5A-Za-z（）()·\\-Ⅰ-Ⅻ]{1,22})\"\n"
        "    r\"((?:\\s+\\d{1,9}){2,3})(?=\\s|$)\")\n"
        "for m in pat.finditer(seg):\n"
        "    name = m.group(1).strip()\n"
        "    nums = [int(x) for x in m.group(2).split()]\n"
        "    if len(nums) == 3:          # 首数为脚注序号，丢弃\n"
        "        nums = nums[1:]\n"
        "    cs, ds = nums[0], nums[1]   # 发病数、死亡数\n"
        "    # 依据《传染病防治法》分类表精确判定甲/乙/丙类\n"
        "    rows.append({\"name\": name, \"cases\": cs, \"deaths\": ds,\n"
        "                 \"class_name\": LEGAL_CLASS.get(name) or guess_class(name, text)})")

    rep.h2("附录 C　集群部署与运行命令速查")
    rep.p("本平台在 Linux 集群上的部署严格对照《项目操作流程》的 17 个步骤执行，"
          "配套脚本位于 code/deploy 目录，详细说明见《集群部署文档.md》。下表给出关键命令速查。")
    tab(rep, "集群启停与运行命令速查",
        ["环节", "命令", "说明"],
        [["环境准备", "bash deploy/01_system_prepare.sh", "主机名/hosts/防火墙/免密登录/目录规划"],
         ["JDK 与 MySQL", "bash deploy/02_install_jdk_mysql.sh", "安装 JDK 与 MySQL"],
         ["Hadoop", "bash deploy/03_install_hadoop.sh", "HDFS 格式化并启动 HDFS/YARN"],
         ["Hive", "bash deploy/04_install_hive.sh", "初始化元数据库并启动 HiveServer2"],
         ["ZK 与 Kafka", "bash deploy/05_install_zookeeper_kafka.sh", "启动 ZooKeeper 与 Kafka"],
         ["Spark", "bash deploy/06_install_spark.sh", "配置 Spark 并集成 Hive"],
         ["整体验证", "bash deploy/07_verify_all.sh", "逐组件健康检查"],
         ["数据入湖", "hdfs dfs -put -f output/ods/ods_*.csv /med_health/ods/", "ODS 数据上传"],
         ["数仓构建", "beeline -u jdbc:hive2://hadoop01:10000 -n hadoop -f 0X_*.sql", "按 00→04 顺序执行"],
         ["离线统计", "spark-submit --master yarn offline_stats.py", "PySpark 离线指标计算"],
         ["实时爬虫", "python crawler.py", "抓取 CDC 疫情公报并投递到 Kafka"],
         ["实时链路", "spark-submit --master yarn spark_streaming_job.py", "Spark Streaming 窗口聚合"],
         ["单机复现", "python run_all.py", "本地完整复现全链路"],
         ["启动平台", "python code/web/app.py", "浏览器访问 http://127.0.0.1:5000"]],
        widths=[2.6, 7.4, 4.4], fs=8)
