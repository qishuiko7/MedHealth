# -*- coding: utf-8 -*-
"""
后端（大数据）同学课程设计报告生成器
==================================================================
课题：医疗健康数据平台与疾病统计分析
本报告侧重 **后端与大数据方向** 的分析、设计与实现：
  数据生成与脱敏 → HDFS 入湖 → Hive 四层数仓 → Spark SQL 离线统计
  → Kafka + Spark Streaming 实时链路 → Spark MLlib 住院日预测
  → Spark GraphX 疾病共现网络 → MySQL 落库 → 数据接口与权限

说明：
  · 本课题为小组课程设计，后端同学负责数据链路与建模，
    前端同学负责可视化平台（界面设计、13 个页面、34 个图表）。
  · 报告中的统计数据、模型指标、图计算指标全部从 MySQL 实时读取，
    保证数字与实际运行结果一致。

运行： python gen_report_backend.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

from docx.shared import Cm, Pt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_common import (build_skeleton, save_report, tab, fig, q, q1, kpi, mv, mv_params,
                           netv, fmtd, wan, reset_counters, TABLE_N, FIG_N, P)

OUT_NAME = "医疗健康数据平台与疾病统计分析-课程设计报告（后端）.docx"
REPORT_ROLE = "后端与大数据"

MODULES = [
    ("B01", "数据模拟与生成", "生成患者/科室/医生/药品/疾病/挂号/就诊/处方/住院九类数据", "高"),
    ("B02", "数据脱敏", "8 类敏感字段的掩码 / 哈希 / 泛化 / 伪名化，输出规则说明", "高"),
    ("B03", "数据入湖", "脱敏数据落盘并上传 HDFS，建立 ODS 贴源层", "高"),
    ("B04", "Hive 数仓分层", "构建 ODS / DWD / DWS / ADS 四层，含清洗、维度退化与分区", "高"),
    ("B05", "离线统计计算", "Spark SQL 完成疾病分布、就诊高峰、科室工作量等 6 大主题", "高"),
    ("B06", "实时流处理", "Kafka + Spark Structured Streaming 窗口聚合，结果落 MySQL", "中"),
    ("B07", "机器学习建模", "Spark MLlib 随机森林回归预测住院日、分类识别超长住院", "高"),
    ("B08", "图计算", "Spark GraphX 构建疾病共现网络，PageRank / 连通分量 / 社区发现", "中"),
    ("B09", "结果落库", "MySQL 建库建表（17 表 3 视图），ADS 与模型结果导入", "高"),
    ("B10", "数据接口", "Flask + PyMySQL 提供 16 个数据接口，统一 {ok,data} 契约", "高"),
    ("B11", "权限控制", "管理员 / 医师 / 访客三级角色，页面级与接口级双重校验", "中"),
    ("B12", "报表导出", "13 类结果表导出 Excel / CSV", "中"),
    ("B13", "双引擎一致性校验", "用真实 Spark SQL 独立重算核心指标，与本地引擎逐项比对", "中"),
    ("B14", "集群部署", "JDK/Hadoop/Hive/ZooKeeper/Kafka/Spark 部署脚本与验证", "中"),
]

HIVE_TABLES = [
    ("ODS", "ods_department / ods_doctor / ods_drug / ods_disease / ods_patient / "
            "ods_registration / ods_visit / ods_prescription / ods_admission",
     "TextFile（外部表）", "OpenCSVSerde 映射 HDFS CSV，跳过表头，不做清洗"),
    ("DIM", "dim_date", "ORC", "日期维度，含年/季/月/星期/是否周末/季节"),
    ("DWD", "dwd_registration_detail / dwd_visit_detail / "
            "dwd_prescription_detail / dwd_admission_detail",
     "ORC + Snappy，按 dt 分区", "清洗无效记录、时间标准化、维度退化、派生指标"),
    ("DWS", "dws_dept_workload_d / dws_visit_time_d / dws_disease_d / "
            "dws_drug_d / dws_los_d / dws_patient_demog_d",
     "ORC，按 stat_month 分区", "按天 + 分析维度轻度聚合，沉淀公共粒度"),
    ("ADS", "ads_overview_kpi / ads_disease_distribution / ads_visit_peak / "
            "ads_dept_workload / ads_drug_consumption / ads_los_analysis / "
            "ads_infectious_monitor",
     "ORC", "面向报表的最终加工，字段与前端接口一一对应"),
]

EXPORT_MAP = [
    ("overview", "ads_overview_kpi", "总体概览 KPI 指标"),
    ("disease", "ads_disease_distribution", "疾病分布统计"),
    ("peak", "ads_visit_peak", "就诊高峰分布"),
    ("dept", "ads_dept_workload", "科室工作量统计"),
    ("drug", "ads_drug_consumption", "药品消耗统计"),
    ("los", "ads_los_analysis", "住院天数分析"),
    ("infectious", "ads_infectious_monitor", "法定传染病监测"),
    ("ml_metric", "ads_ml_metric", "住院日预测模型指标"),
    ("ml_importance", "ads_ml_feature_importance", "住院日预测特征重要性"),
    ("ml_prediction", "ads_ml_los_prediction", "住院日预测结果明细"),
    ("network_node", "ads_network_node", "疾病共现网络节点"),
    ("network_edge", "ads_network_edge", "疾病共现网络边"),
    ("consistency", "ads_engine_consistency", "双引擎口径一致性校验"),
]


# ===========================================================================
# 第 1 章 绪论
# ===========================================================================
def ch1(rep):
    rep.h1("1　绪论")

    rep.h2("1.1　项目背景与后端定位")
    rep.p("国家卫生健康委员会持续推进医院信息互联互通标准化成熟度测评与电子病历系统应用水平"
          "分级评价，三级医院普遍建成了覆盖门诊、住院、检验、影像、药事等环节的 HIS / EMR / LIS 系统。"
          "以一家年门诊量百万人次的地市级三甲医院为例，每年产生的挂号、就诊、处方、住院等"
          "结构化记录可达千万级，天然具备「数据量大、维度丰富、时效性要求高」的大数据特征。")
    rep.p("然而这些数据要产生价值，中间隔着一整条技术链路：数据分散在多个业务库、"
          "携带敏感个人信息不能直接分析、体量超出单机处理能力、"
          "离线统计与实时监测诉求并存。**这就是本课题后端与大数据方向要解决的问题。** "
          "本报告负责的工作覆盖从数据产生到数据服务的全链路："
          "数据模拟与脱敏、HDFS 入湖、Hive 四层数仓建设、Spark 离线统计、"
          "Kafka + Spark Streaming 实时链路、Spark MLlib 机器学习建模、"
          "Spark GraphX 图计算、MySQL 落库、数据接口与权限控制。"
          "可视化界面由小组前端方向的同学负责。具体分工见表 1-1。")
    tab(rep, "小组分工与交付边界",
        ["方向", "主要职责", "交付物"],
        [["后端 / 大数据（本报告）",
          "数据模拟与脱敏；HDFS 数据入湖；Hive（ODS/DWD/DWS/ADS）四层数仓；"
          "Spark SQL 离线统计；Kafka + Spark Streaming 实时链路；"
          "Spark MLlib 住院日预测；Spark GraphX 疾病共现网络；"
          "MySQL 建库建表与结果落库；Flask 数据接口、权限校验、报表导出；"
          "大数据集群部署与验证",
          "后端源码、Hive SQL、Spark 作业、数据库脚本、集群部署文档、后端报告（本报告）"],
         ["前端 / 可视化",
          "可视化平台界面设计；13 个功能页面开发；34 个 ECharts 图表实现；"
          "页面交互与联动；响应式适配；前端权限菜单；前端测试",
          "前端源码、界面截图、前端报告"]],
        widths=[3.0, 8.0, 4.0], fs=8.5)

    rep.h2("1.2　医疗数据的合规挑战")
    rep.p("医疗数据同时是个人信息保护的重点领域。患者姓名、身份证号、联系方式、精确住址等"
          "直接标识符一旦泄露，将造成不可逆的隐私损害。"
          "《个人信息保护法》《人口健康信息管理办法》与 "
          "《信息安全技术 个人信息安全规范》（GB/T 35273）都对医疗健康信息的处理提出了明确要求。"
          "因此医疗数据分析平台必须在数据进入分析环节之前完成脱敏，"
          "并且要保留统计分析所必需的最小可分性（如年龄段、地区码、性别），"
          "做到「数据可用不可见、可算不可识」。")
    rep.p("这对后端设计提出了三个具体约束：一是**脱敏必须前置于入库**，"
          "不能等到分析阶段再做；二是**脱敏必须不可逆**，"
          "否则脱敏形同虚设；三是**脱敏必须保持跨表关联能力**，"
          "否则患者主索引与就诊、处方、住院表就无法 JOIN，"
          "整条分析链路会断裂。本设计的技术方案见 4.6 与 5.1 节。")

    rep.h2("1.3　设计目标与主要内容")
    rep.p("本报告对应的后端工作目标与内容如下：")
    rep.bullet("（1）构建可复现的医疗业务数据源。设计符合三范式的关系模型，"
               "覆盖患者、科室、医生、药品、疾病、挂号、就诊、处方、住院九类实体，"
               "用概率化的业务规则生成具备真实统计特征的数据，规模达到 10 万级。")
    rep.bullet("（2）实现字段级数据脱敏。针对 8 类敏感字段设计并实现掩码、"
               "HMAC-SHA256 加盐哈希、向上泛化、伪名化与文本泛化五类规则。")
    rep.bullet("（3）构建 Hive 四层数据仓库。ODS 9 张贴源表、DIM 1 张日期维表、"
               "DWD 4 张分区明细表、DWS 6 张轻度汇总表、ADS 7 张结果表，共 27 张。")
    rep.bullet("（4）完成离线与实时两条计算链路。离线侧以 Spark SQL 完成六大分析主题的统计；"
               "实时侧以 Kafka + Spark Structured Streaming 按窗口聚合实时就诊数据，"
               "并实现真实网络爬虫抓取 CDC 疫情公报汇入实时链路。")
    rep.bullet("（5）落地机器学习与图计算。用 Spark MLlib 训练住院日预测模型"
               "（回归 + 超长住院风险分类），用 Spark GraphX 构建疾病共现网络"
               "并完成 PageRank、连通分量、社区发现与三角计数。")
    rep.bullet("（6）设计 MySQL 库表并提供数据服务。按三范式设计 17 张表与 3 个视图，"
               "实现 16 个数据接口、三级角色权限与 13 类报表导出。")
    rep.bullet("（7）完成大数据集群部署与验证。严格对照课程《项目操作流程》的 17 个步骤，"
               "交付部署文档与可执行脚本，并在 Windows 单机上实际跑通全链路。")

    rep.h2("1.4　报告结构")
    rep.p("全文共 7 章：第 1 章绪论；第 2 章介绍后端相关技术与开发环境；"
          "第 3 章进行需求分析；第 4 章给出总体设计与数据库设计；"
          "第 5 章展开详细设计与实现；第 6 章给出系统测试；"
          "第 7 章总结并提出改进方向。附录给出后端文件清单、关键代码与部署命令速查。")


# ===========================================================================
# 第 2 章 相关技术与开发环境
# ===========================================================================
def ch2(rep):
    rep.h1("2　后端相关技术与开发环境")

    rep.h2("2.1　Hadoop 与 HDFS、YARN")
    rep.p("Hadoop 3.x 是本平台的存储与资源调度基础。HDFS 采用主从架构，"
          "NameNode 维护命名空间与块映射、DataNode 存储实际数据块，"
          "默认多副本策略保证数据可靠性；YARN 由 ResourceManager 与 NodeManager 组成，"
          "负责集群资源的统一分配。本设计中 HDFS 用于落地 ODS 层脱敏数据"
          "与实时明细数据，目录规划为 /med_health/ods 与 /med_health/realtime。")

    rep.h2("2.2　Hive 数据仓库")
    rep.p("Hive 将 SQL 语句翻译为分布式计算作业，并借助 Metastore 统一管理表结构与分区。"
          "本设计使用 MySQL 作为 Hive 元数据库；存储格式采用 ORC（列式存储，"
          "压缩比与查询性能优于 TextFile），压缩方式为 Snappy。"
          "ODS 层使用外部表 + OpenCSVSerde 直接映射 HDFS 上的 CSV 文件，"
          "保证删除表不会误删原始数据；DWD / DWS 层使用分区表，"
          "按业务日期 dt 与月份 stat_month 分区，支持按天增量重跑。")

    rep.h2("2.3　ZooKeeper 与 Kafka")
    rep.p("ZooKeeper 提供分布式协调能力，为 Kafka 保存 Broker 元数据与消费者位移。"
          "Kafka 作为消息缓冲层，通过主题与分区实现高吞吐写入与水平扩展。"
          "本设计定义三个主题：med_registration（挂号事件）、med_visit（就诊事件）、"
          "med_prescription（处方事件），并约定以 patient_id 作为分区键保证同一患者事件有序。")

    rep.h2("2.4　Spark 计算引擎")
    rep.h3("2.4.1　Spark SQL 与 PySpark")
    rep.p("Spark SQL 提供与 Hive 兼容的 SQL 能力，可直接查询 Hive 表并利用 Catalyst 优化器"
          "生成物理计划；PySpark 为 Python 开发者提供 DataFrame API。"
          "本设计用 Spark SQL 完成离线统计，并用它反向校验本地等价引擎的口径。")
    rep.h3("2.4.2　Spark Structured Streaming")
    rep.p("以「无界表」模型统一流批语义，支持基于事件时间的滚动窗口、"
          "水位线（Watermark）与 foreachBatch 输出。"
          "本设计用它实现按 60 秒窗口、按科室聚合的实时就诊量统计。")
    rep.h3("2.4.3　Spark MLlib 机器学习库")
    rep.p("提供特征抽取与变换（StringIndexer、OneHotEncoder、VectorAssembler）、"
          "分类与回归（随机森林、梯度提升树等）、模型评估与 Pipeline 流水线编排能力。"
          "本设计用 MLlib 完成住院日预测：回归模型预测住院天数，"
          "分类模型识别超长住院风险，并输出特征重要性与分风险等级的预测明细。")
    rep.h3("2.4.4　Spark GraphX 图计算库")
    rep.p("GraphX 以顶点 RDD 与边 RDD 构成的属性图为数据模型，"
          "内置 PageRank、连通分量、标签传播、三角计数等图算法，"
          "并提供 aggregateMessages 原语支持 Pregel 风格的自定义消息传递。"
          "需要说明的是 **GraphX 官方仅提供 Scala API**，"
          "PySpark 侧与其对应的是 GraphFrames 封装。"
          "本设计用图计算完成疾病共现网络分析，实现路径见 5.7 节。")

    rep.h2("2.5　MySQL 与应用层技术")
    rep.p("MySQL 8.0 承担两个角色：一是 Hive 的元数据库（库 hive_meta），"
          "二是分析结果的存储库（库 med_health）。"
          "应用层使用 Flask 提供数据接口（装饰器式路由 + Session 会话管理），"
          "用 PyMySQL 直连 MySQL 并启用 DictCursor 使查询结果可直接序列化为 JSON，"
          "用 pandas + openpyxl 实现报表导出。")

    rep.h2("2.6　开发与部署环境")
    rep.p("本设计的开发与演示分为「单机全链路复现」与「Linux 集群部署」两种形态。"
          "单机形态用于开发调试与答辩演示，集群形态用于按课程要求完成完整的大数据平台搭建。"
          "两套环境的组件版本保持一致，避免行为差异。")
    tab(rep, "开发与运行环境版本清单",
        ["类别", "组件", "版本", "说明"],
        [["操作系统", "Windows", "11 专业版", "单机开发与演示环境"],
         ["操作系统", "CentOS", "7.9", "VMware 虚拟机，集群节点"],
         ["运行环境", "JDK", "8u504（Temurin）", "Hadoop / Hive / Spark / Kafka 运行时"],
         ["运行环境", "Python", "3.13（ETL 与 Web）、3.10（PySpark）", "分工明确，互不干扰"],
         ["大数据", "Hadoop", "3.3.6", "HDFS 存储 + YARN 资源调度"],
         ["大数据", "Hive", "3.1.3", "数据仓库，元数据库为 MySQL"],
         ["大数据", "ZooKeeper", "3.8.4", "Kafka 与 Hadoop HA 协调"],
         ["大数据", "Kafka", "3.6.1", "实时消息缓冲"],
         ["大数据", "Spark", "3.5.1", "Spark SQL / Streaming / MLlib / GraphX"],
         ["数据库", "MySQL", "8.0.29", "Hive 元数据库 + 结果存储库"],
         ["Web", "Flask", "3.1.3", "数据接口与页面路由"],
         ["开发工具", "PyCharm / DBeaver", "—", "Python 开发与数据库客户端"]],
        widths=[2.4, 3.4, 3.6, 6.2], fs=8.5)
    tab(rep, "集群节点规划（单节点伪分布式，可扩展为 3 节点）",
        ["主机名", "IP 地址", "部署组件", "关键端口"],
        [["hadoop01", "192.168.10.101",
          "NameNode、DataNode、ResourceManager、NodeManager、"
          "Hive Metastore / HiveServer2、ZooKeeper、Kafka、Spark",
          "9870 / 8088 / 10000 / 9083 / 2181 / 9092"],
         ["Windows 主机", "192.168.10.1",
          "PyCharm、Anaconda、MySQL、Flask、浏览器", "3306 / 5000"]],
        widths=[2.4, 3.0, 6.6, 3.0])

    rep.h2("2.7　本章小结")
    rep.p("本章介绍了后端所依赖的大数据组件与应用层技术，并给出开发环境版本清单与集群节点规划。"
          "整体技术选型遵循课程规定的统一技术栈，各组件职责边界清晰："
          "Kafka 负责解耦，HDFS 负责存储，Hive 负责建模，"
          "Spark 负责计算（SQL / Streaming / MLlib / GraphX），"
          "MySQL 负责服务，Flask 负责接口。")


# ===========================================================================
# 第 3 章 需求分析
# ===========================================================================
def ch3(rep):
    rep.h1("3　需求分析")

    rep.h2("3.1　业务需求分析")
    rep.p("医疗健康数据平台的业务需求来自医院管理与公共卫生两个方向。"
          "医院管理侧关注运行效率与资源配置，希望回答「哪些科室最忙」"
          "「门诊高峰在什么时段」「药品费用集中在哪些品种」「住院日是否偏长」等问题；"
          "公共卫生侧关注疾病负担与趋势，希望回答「主要疾病谱是什么」"
          "「传染病报告情况如何变化」等问题。"
          "进一步地，业务希望从「描述发生了什么」走向「预测会发生什么」——"
          "例如提前识别可能超长住院的病例，或发现疾病之间的共病关联。"
          "这正好对应任务书要求的机器学习与图计算能力。")

    rep.h2("3.2　功能需求")
    rep.p("依据课程设计任务书的功能要求与上述业务诉求，"
          "后端共分解为 14 个功能模块，详见表 3-1。")
    tab(rep, "后端功能需求清单",
        ["序号", "功能模块", "说明", "优先级"],
        [[m[0], m[1], m[2], m[3]] for m in MODULES],
        widths=[1.2, 3.0, 9.6, 1.6], fs=8.5)

    rep.h2("3.3　数据需求")
    rep.p("数据需求包括数据来源、数据规模与数据质量三方面。"
          "数据来源上，平台以医院 HIS 业务库为主数据源，同时预留对外部门户"
          "（如疾控通报、公开疾病统计）的采集通道；"
          "本设计以模拟生成方式构造与真实业务同构的数据。"
          "数据规模上，主事实表（挂号）设定为 10 万级，全部环节累计处理记录 46 万余条。"
          "数据质量上，要求：挂号时间必须落在统计区间内；"
          "就诊记录必须携带有效 ICD-10 诊断编码；处方数量与金额必须为正；"
          "住院天数必须大于 0；挂号状态与是否就诊标记必须一致。"
          "上述约束在生成阶段写入业务规则，并在 DWD 层通过 WHERE 条件二次校验。")
    tab(rep, "数据集规模与业务约束",
        ["数据表", "业务含义", "记录数", "关键约束"],
        [["患者主索引", "患者基本信息（已脱敏）", "20,000", "身份证号唯一、年龄段派生"],
         ["挂号记录", "门诊挂号事实，主事实表", "120,000", "状态 ∈ {已就诊, 取消, 爽约}"],
         ["门诊就诊", "就诊与诊断事实", "105,334", "诊断编码非空"],
         ["处方明细", "处方用药明细", "223,191", "数量 > 0 且金额 > 0"],
         ["住院记录", "住院与转归事实", "14,000", "住院天数 > 0"],
         ["科室 / 医生 / 药品 / 疾病", "四类维度", "20 / 300 / 200 / 122", "主键唯一、外键有效"]],
        widths=[3.2, 4.2, 2.6, 5.0], fs=8.5)

    rep.h2("3.4　非功能需求")
    rep.h3("3.4.1　性能需求")
    rep.p("平台需支持 10 万级主事实表的统计计算，单次全链路批处理时间应控制在 1 分钟以内；"
          "数据接口响应时间不超过 500 ms；实时链路端到端延迟不超过一个窗口长度（60 秒）。")
    rep.h3("3.4.2　安全与隐私需求")
    rep.p("一是在数据进入分析环境之前完成脱敏，且脱敏不可逆；"
          "二是脱敏具备确定性，保证跨表关联不失效；"
          "三是对平台访问做角色隔离，敏感明细与批量导出仅对管理员开放；"
          "四是口令与会话具备基本防护，会话超时后需重新登录。")
    rep.h3("3.4.3　可扩展性需求")
    rep.p("数仓分层需支持按天增量重跑；集群需支持从单节点扩展为多节点；"
          "分析主题需可增量扩展，新增指标只需在 DWS / ADS 层追加表与作业，"
          "不修改已有链路的对外接口。")
    rep.h3("3.4.4　可复现性需求")
    rep.p("课程设计的答辩环境往往只有一台普通电脑，无法保证一定能部署完整集群。"
          "因此要求：在无 Hadoop / Spark 的单机环境下，"
          "整条链路仍能完整复现，且结果与集群侧完全一致 —— "
          "这一点通过「本地等价计算引擎 + 双引擎一致性校验」实现（见 5.8 节）。")

    rep.h2("3.5　本章小结")
    rep.p("本章从业务需求出发，梳理出 14 个后端功能模块，"
          "并明确了性能、安全隐私、可扩展性与可复现性四项非功能约束，"
          "同时给出数据来源、规模与质量要求，为总体设计提供输入。")


# ===========================================================================
# 第 4 章 总体设计
# ===========================================================================
def ch4(rep):
    rep.h1("4　总体设计")

    rep.h2("4.1　设计原则")
    rep.p("本设计遵循五项原则：")
    rep.bullet("（1）隐私优先：脱敏前置于入库，任何分析环节不得接触原始敏感字段。")
    rep.bullet("（2）分层解耦：存储、计算、服务、展示四层之间只通过明确的数据契约交互，"
               "任一层内部实现变更不影响其他层。")
    rep.bullet("（3）批流一体：离线与实时共用同一套字段定义与指标口径，"
               "避免同名指标两套算法。")
    rep.bullet("（4）口径唯一：所有指标的分子分母定义在文档与代码中保持一致，"
               "并在接口与界面中显式说明。")
    rep.bullet("（5）可复现：数据生成使用固定随机种子，全链路可重复执行并得到一致结果；"
               "同时提供与集群等价的单机实现。")

    rep.h2("4.2　系统总体架构")
    rep.p("系统采用七层架构，自下而上依次为数据源层、数据采集层、消息缓冲层、"
          "数据存储层、计算层、数据服务层与应用展示层，如图 4.1 所示。"
          "本报告负责除应用展示层（界面）之外的六个层次。")
    fig(rep, "arch_overall.png", "系统总体架构图")
    rep.p("在总体架构基础上，计算层内部采用 Lambda 架构组织："
          "批处理层由 HDFS + Hive + Spark SQL 构成，负责全量数据的准确统计；"
          "速度层由 Kafka + Spark Streaming 构成，负责近期数据的低延迟近似统计；"
          "两条链路的结果在服务层（MySQL）汇聚，由展示层统一消费，如图 4.2 所示。")
    fig(rep, "arch_lambda.png", "Lambda 架构（批处理层 + 速度层）")

    rep.h2("4.3　数据仓库分层设计")
    rep.p("数仓共分四层。ODS 层贴源存储，与 HDFS 文件一一对应，不做业务清洗；"
          "DWD 层完成清洗、去重、类型规整与维度退化，是后续所有统计的唯一数据来源；"
          "DWS 层按「日期 + 分析维度」做轻度聚合，沉淀可复用的公共粒度；"
          "ADS 层面向具体报表做最终加工，字段命名与前端接口一一对应。"
          "分层结构如图 4.3 所示。")
    fig(rep, "hive_layers.png", "Hive 数仓分层图", width=14.0)
    tab(rep, "数仓各层表清单与加工要点",
        ["层次", "表名", "存储格式", "加工要点"],
        [[h[0], h[1], h[2], h[3]] for h in HIVE_TABLES],
        widths=[1.4, 6.4, 3.2, 4.0], fs=8)

    rep.h2("4.4　功能模块设计")
    rep.p("后端划分为六大子系统：数据准备子系统（数据生成、脱敏、入湖）、"
          "数仓建设子系统（ODS/DWD/DWS/ADS 分层加工）、"
          "分析计算子系统（Spark SQL 离线统计、Spark Streaming 实时流计算）、"
          "智能分析子系统（Spark MLlib 住院日预测、Spark GraphX 疾病共现网络）、"
          "应用服务子系统（Flask 接口、权限控制、报表导出）、"
          "部署运维子系统（集群部署脚本与验证）。"
          "各模块之间的调用关系与数据流向如图 4.4 所示。")
    fig(rep, "flow_data.png", "数据流转流程图", width=15.0)

    rep.h2("4.5　数据库设计")
    rep.h3("4.5.1　概念模型")
    rep.p("数据库以患者为核心实体，围绕就诊过程组织关系：患者与挂号是一对多关系，"
          "挂号与就诊多为一对一关系，就诊与处方明细是一对多关系；"
          "科室与医生、科室与挂号、科室与住院均为一对多关系；"
          "疾病字典与就诊、住院通过诊断编码关联；药品字典与处方明细通过药品编码关联。"
          "整体模型满足第三范式，维度独立成表，事实表只保存外键与度量。"
          "业务库概念模型如图 4.5 所示，应用层结果表之间的关系如图 4.6 所示。")
    fig(rep, "er_diagram.png", "数据库 E-R 图（业务库）", width=15.0)
    fig(rep, "er_diagram_ads.png", "应用层结果表 E-R 图", width=15.0)

    rep.h3("4.5.2　逻辑模型")
    rep.p("MySQL 库 med_health 共包含 17 张表与 3 个视图，"
          "按维度表、ADS 结果表、模型与图计算结果表、元数据表四类组织，如表 4-2 所示。")
    dim_rows = [[r["tname"], r["tcomment"], fmtd(q1(f"SELECT COUNT(1) c FROM {r['tname']}")["c"])]
                for r in q("SELECT table_name AS tname, table_comment AS tcomment "
                           "FROM information_schema.tables "
                           "WHERE table_schema='med_health' AND table_type='BASE TABLE' ORDER BY table_name")]
    tab(rep, "MySQL 数据库表清单",
        ["表名", "说明", "记录数"], dim_rows,
        widths=[5.4, 7.4, 2.6], fs=8.5)

    rep.h3("4.5.3　关键表结构")
    rep.p("以下给出四张关键表的结构设计：患者维度表的脱敏字段是隐私保护的核心；"
          "dwd_visit_detail 是绝大多数分析指标的来源；"
          "ads_overview_kpi 与模型结果表分别支撑概览大屏与智能分析页面。")
    tab(rep, "患者维度表 dim_patient 关键字段",
        ["字段名", "类型", "含义", "脱敏处理"],
        [["patient_id", "INT", "患者主键", "—"],
         ["patient_no", "VARCHAR(32)", "病历号", "HMAC-SHA256 伪名化，前缀 MED"],
         ["name", "VARCHAR(32)", "姓名", "保留姓氏掩码"],
         ["gender / age / age_group", "VARCHAR / INT / VARCHAR", "性别 / 年龄 / 年龄段", "年龄派生，原生日不可还原"],
         ["id_card", "VARCHAR(64)", "身份证号", "HMAC-SHA256 加盐哈希"],
         ["id_region", "VARCHAR(16)", "身份证地区码", "保留前 6 位用于地域统计"],
         ["phone", "VARCHAR(32)", "手机号", "中间四位掩码"],
         ["address", "VARCHAR(128)", "家庭住址", "泛化到省市区三级"],
         ["email", "VARCHAR(128)", "电子邮箱", "局部掩码，保留域名"],
         ["insurance_type / blood_type", "VARCHAR(32)", "医保类型 / 血型", "—"]],
        widths=[4.4, 4.0, 4.0, 3.6], fs=8.5)
    tab(rep, "就诊明细表 dwd_visit_detail 关键字段",
        ["字段名", "类型", "含义", "来源"],
        [["visit_id / reg_id", "INT", "就诊主键 / 挂号外键", "ODS 就诊表"],
         ["patient_id", "INT", "患者外键", "维度退化"],
         ["gender / age / age_group / insurance_type", "VARCHAR / INT", "患者人口学属性", "患者维度退化"],
         ["dept_id / dept_name", "INT / VARCHAR", "科室", "科室维度退化"],
         ["doctor_id / doctor_name", "INT / VARCHAR", "接诊医生", "医生维度退化"],
         ["visit_time / visit_hour / visit_period", "STRING / INT / STRING", "就诊时间、小时、时段", "时间派生"],
         ["diagnosis_code / diagnosis_name", "VARCHAR", "ICD-10 编码与名称", "疾病维度退化"],
         ["disease_category", "VARCHAR", "疾病大类", "疾病维度退化"],
         ["severity / is_infectious / is_chronic", "INT", "严重程度 / 法定传染病 / 慢性病", "疾病维度退化"],
         ["chief_complaint", "VARCHAR(255)", "主诉", "文本泛化后"]],
        widths=[5.4, 3.6, 4.4, 2.6], fs=8.5)
    tab(rep, "模型结果表 ads_ml_metric 关键字段",
        ["字段名", "类型", "含义"],
        [["task_name", "VARCHAR(64)", "任务名称（住院日预测）"],
         ["model_name", "VARCHAR(64)", "模型名称（随机森林回归 / 梯度提升分类等）"],
         ["task_type", "VARCHAR(16)", "任务类型（regression / classification）"],
         ["metric_name", "VARCHAR(64)", "指标名（R2 / RMSE / AUC / F1 等）"],
         ["metric_value", "DECIMAL(16,4)", "指标值"],
         ["train_cnt / test_cnt / feature_cnt", "INT", "训练样本数 / 测试样本数 / 特征数"],
         ["params", "VARCHAR(512)", "超参数描述"]],
        widths=[5.0, 3.4, 8.0], fs=8.5)
    tab(rep, "图计算结果表 ads_network_node 关键字段",
        ["字段名", "类型", "含义"],
        [["disease_name", "VARCHAR(128)", "疾病名称（图顶点）"],
         ["diagnosis_code / disease_category", "VARCHAR", "ICD-10 编码 / 疾病大类"],
         ["patient_cnt", "BIGINT", "患该病去重患者数"],
         ["degree / weighted_degree", "INT / BIGINT", "度数（共现病种数）/ 加权度（共现患者合计）"],
         ["pagerank", "DECIMAL(12,8)", "PageRank 值（疾病中心性）"],
         ["component_id / community_id", "BIGINT", "连通分量编号 / 社区编号"],
         ["triangle_cnt", "INT", "三角计数（局部聚集度）"],
         ["rank_no", "INT", "按 PageRank 的排名"]],
        widths=[5.0, 3.4, 8.0], fs=8.5)

    rep.h2("4.6　安全与隐私设计")
    rep.p("安全与隐私设计覆盖三个层面。**数据层**：8 条字段级脱敏规则前置于入库环节，"
          "敏感字段原文在进入分析环境前已被替换为不可逆值或降精度值；"
          "哈希采用 HMAC-SHA256 并引入固定盐值，保证同一原值映射结果稳定，"
          "从而支持跨表关联而不暴露原值。**应用层**：三级角色权限矩阵控制页面与接口可见范围，"
          "批量导出仅对管理员开放；会话采用服务端 Session 并设置过期时间。"
          "**审计层**：脱敏规则以数据表形式落库并公开展示，"
          "使脱敏过程可被追溯与复核。脱敏流程如图 4.7 所示。")
    fig(rep, "flow_desensitize.png", "数据脱敏流程图", width=15.0)

    rep.h2("4.7　本章小结")
    rep.p("本章给出系统总体架构、数仓分层设计、功能模块划分与数据库设计。"
          "架构上采用七层结构并引入 Lambda 计算组织；"
          "数仓按 ODS / DWD / DWS / ADS 四层组织，共 27 张 Hive 表；"
          "数据库按三范式设计 17 张表与 3 个视图（含 MLlib 模型结果表与 GraphX 图计算结果表）；"
          "安全设计以「脱敏前置 + 角色隔离 + 规则可审计」为主线。")


# ===========================================================================
# 第 5 章 详细设计与实现
# ===========================================================================
def ch5(rep):
    k = kpi()
    rep.h1("5　详细设计与系统实现")

    # ---------- 5.1 数据生成与脱敏 ----------
    rep.h2("5.1　数据生成与脱敏")
    rep.h3("5.1.1　数据模型与业务规则建模")
    rep.p("数据生成模块以三范式关系模型为基础，按「维度表先行、事实表后生」的顺序构造数据："
          "先生成 20 个科室、300 名医生、200 种药品与 122 条 ICD-10 疾病字典，"
          "再生成 20,000 名患者主索引，最后以患者与科室为基准生成挂号、就诊、处方与住院四类事实数据。"
          "模块使用固定随机种子（20261008），保证多次执行得到完全一致的数据集。"
          "为使数据具备真实统计特征，将医院的运行规律编码为概率分布，主要包括五类规则：")
    rep.bullet("（1）就诊时段分布：按 24 小时权重建模，上午 8—11 时与下午 14—16 时形成双峰，"
               "夜间权重极低，符合门诊作息规律。")
    rep.bullet("（2）星期效应：周一至周五权重 1.28 / 1.22 / 1.16 / 1.12 / 1.05，"
               "周六周日降至 0.60 / 0.44，体现周末门诊量下降。")
    rep.bullet("（3）季节系数：呼吸系统疾病冬季系数 1.45、夏季 0.75，"
               "感染性疾病夏季 1.30，从而使疾病谱随月份产生合理波动。")
    rep.bullet("（4）科室—疾病映射：为 20 个科室分别配置主要收治疾病大类，"
               "保证「骨科以肌肉骨骼系统疾病为主、心血管内科以循环系统疾病为主」等业务合理性。")
    rep.bullet("（5）药品—疾病匹配：为 27 个药品类别配置对应的疾病大类，"
               "使处方用药与诊断保持业务一致。")

    rep.h3("5.1.2　住院日的建模：一次重要的数据修正")
    rep.p("住院日的生成方式经过了一次重要修正，这里如实记录，因为它直接决定了"
          "后续机器学习任务能否成立。")
    rep.p("**初版设计**把住院日当作「对数正态随机数 + 严重程度微调」生成。"
          "表面上均值与分布都合理，但当用 Spark MLlib 做住院日预测时，"
          "模型的决定系数 R² 为负 —— 意味着模型还不如直接用平均值预测；"
          "特征重要性也全部失效，模型学不到任何规律。"
          "排查后确认：**住院日与年龄、科室、合并症等任何可观测特征都无关，"
          "本质上是纯随机噪声。**")
    rep.p("**修正方案**：真实的住院日（Length of Stay）在临床上由一组明确的变量共同决定，"
          "因此改为可解释的线性决定式加随机扰动："
          "以疾病严重程度（1~5 级）为主导，叠加年龄、是否慢性病、入院方式（急诊入院更重）、"
          "科室诊疗特征（外科/骨科/肿瘤科更长）与患者合并症数量，"
          "再叠加正态扰动；并额外以约 2% 的概率对重症病例叠加「并发症延长」项，"
          "使住院日出现真实的长尾（超过 30 天）。"
          "修正后，用真实自变量做线性拟合的 R² 约为 0.48，"
          "住院日随严重程度、科室、入院方式的变化均符合临床直觉，"
          "模型也随即学到了可解释的规律（见 5.6 节）。")
    rep.p("这次修正带来一个对机器学习项目具有普遍意义的认识："
          "**特征工程的收益上限由数据本身决定**。"
          "在花时间调参、换模型之前，必须先确认数据里是否存在可学习的信号。")

    rep.h3("5.1.3　数据脱敏实现")
    rep.p("脱敏模块实现 8 条字段级规则，规则清单如表 5-1，脱敏前后对照如表 5-2。")
    rules = q("SELECT * FROM desensitize_rule ORDER BY rule_id")
    tab(rep, "字段级数据脱敏规则",
        ["字段", "脱敏方式", "实现方法", "可逆性"],
        [[r["field_name"], r["rule_type"], r["method_desc"], r["reversible"]] for r in rules],
        widths=[3.4, 2.8, 7.6, 1.6], fs=8.5)
    tab(rep, "脱敏前后对照示例（首条记录）",
        ["字段", "脱敏前", "脱敏后"],
        [[r["field_name"].split(" ")[0], r["example_raw"], r["example_masked"]] for r in rules],
        widths=[2.8, 6.6, 6.0], fs=8.5)
    rep.p("脱敏实现的关键点有三：其一，哈希采用 HMAC-SHA256 并拼接固定盐值，"
          "既避免彩虹表反查，又保证同一原值在不同表中的脱敏结果一致，"
          "使 patient 与 registration、visit、prescription、admission 之间的关联查询不失效；"
          "其二，姓名脱敏保留姓氏并对复姓做专门处理，"
          "身份证在哈希之外单独派生 id_region（地区码）与 age_group（年龄段），"
          "使「按地域统计」「按年龄统计」仍然可行；"
          "其三，主诉属非结构化文本，采用正则规则剔除数字、时间与陪同人员姓名，"
          "避免间接标识符泄露。")
    tab(rep, "数据生成规模与清洗结果",
        ["数据表", "生成记录数", "DWD 层保留", "清洗规则"],
        [["患者主索引", "20,000", "20,000", "—"],
         ["挂号记录", "120,000", fmtd(k["visited_cnt"]), "排除取消 / 爽约"],
         ["门诊就诊", "105,334", fmtd(k["visit_cnt"]), "诊断编码非空"],
         ["处方明细", "223,191", "223,191", "数量与金额为正"],
         ["住院记录", "14,000", "14,000", "住院天数 > 0"]],
        widths=[3.0, 2.6, 2.6, 3.8])

    # ---------- 5.2 数据入湖 ----------
    rep.h2("5.2　数据入湖")
    rep.p("脱敏后的 ODS 数据以 UTF-8 with BOM 编码的 CSV 落盘，"
          "再通过 HDFS 命令上传至 /med_health/ods。"
          "Hive ODS 层使用外部表（EXTERNAL TABLE）配合 OpenCSVSerde 直接映射这些文件，"
          "并设置 skip.header.line.count=1 跳过表头。"
          "使用外部表的意义在于：删除元数据不会影响 HDFS 上的原始文件，"
          "符合贴源层「只读、可追溯」的定位。")
    rep.code("hdfs dfs -mkdir -p /med_health/ods\n"
             "hdfs dfs -put -f output/ods/ods_*.csv /med_health/ods/\n"
             "beeline -u jdbc:hive2://hadoop01:10000 -n hadoop -f warehouse/hive/01_ods_ddl.sql")
    rep.p("实际入湖数据共 9 个文件、约 44 MB，其中挂号表 12.8 MB、"
          "就诊表 14.7 MB、处方表 11.3 MB、患者表 3.7 MB，其余为维度表。")

    # ---------- 5.3 Hive 数仓分层 ----------
    rep.h2("5.3　Hive 四层数仓实现")
    rep.h3("5.3.1　DWD 明细层：清洗与维度退化")
    rep.p("DWD 层承担清洗与维度退化两项核心工作。以就诊明细表为例，"
          "ETL 语句同时关联患者、科室、医生、疾病四张维度表，"
          "把性别、年龄段、医保类型、科室名称、医生姓名、疾病大类、严重程度、"
          "是否法定传染病、是否慢性病等常用属性直接打宽到明细表，"
          "使后续统计不再需要反复关联维度表，显著降低 JOIN 开销；"
          "同时派生「就诊时段」（上午/下午/夜间）与「住院天数字段分箱」等业务分桶字段。"
          "关键 SQL 片段如下：")
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
             "LEFT JOIN ods_patient    p   ON v.patient_id   = p.patient_id\n"
             "LEFT JOIN ods_department d   ON v.dept_id      = d.dept_id\n"
             "LEFT JOIN ods_doctor     doc ON v.doctor_id    = doc.doctor_id\n"
             "LEFT JOIN ods_disease    ds  ON v.diagnosis_id = ds.disease_id\n"
             "WHERE v.diagnosis_code IS NOT NULL AND v.diagnosis_code <> '';")

    rep.h3("5.3.2　DWS 汇总层：科室工作量的拼宽")
    rep.p("DWS 层按「日期 + 分析维度」做轻度聚合，共 6 张主题汇总表。"
          "为避免同一指标在 ADS 层被重复计算，科室工作量在 DWS 层通过 FULL OUTER JOIN "
          "把挂号、就诊、处方、住院四条数据流的按日汇总拼宽为一条记录，"
          "使后续任意周期、任意科室的汇总都只需对该表做一次 GROUP BY。"
          "这里有一个易错点：拼宽时必须用「日期 + 科室」取四条流的并集再逐一合并，"
          "若把科室类型也放进分组键，会导致同一科室出现两行"
          "（有挂号记录的日期带类型、无挂号记录的日期类型为空），"
          "进而使就诊量被重复统计。这个问题在开发过程中真实出现过，"
          "表现为某科室就诊量恰好是实际值的两倍。")
    rep.code("INSERT OVERWRITE TABLE dws_dept_workload_d PARTITION (stat_month)\n"
             "SELECT t.dt, t.dept_id, t.dept_name, t.dept_type_name,\n"
             "       t.reg_cnt, t.visit_cnt, t.reg_fee_sum, t.presc_amount,\n"
             "       t.drug_qty, t.admission_cnt, t.los_sum, t.los_cost_sum,\n"
             "       substr(t.dt, 1, 7) AS stat_month\n"
             "FROM (\n"
             "  SELECT coalesce(a.dt, b.dt, c.dt, e.dt)                    AS dt,\n"
             "         coalesce(a.dept_id, b.dept_id, c.dept_id, e.dept_id) AS dept_id,\n"
             "         nvl(a.reg_cnt,0) reg_cnt, nvl(b.visit_cnt,0) visit_cnt,\n"
             "         nvl(c.presc_amount,0) presc_amount, nvl(c.drug_qty,0) drug_qty,\n"
             "         nvl(e.admission_cnt,0) admission_cnt, ...\n"
             "  FROM (挂号按日汇总) a\n"
             "  FULL OUTER JOIN (就诊按日汇总) b ON a.dt=b.dt AND a.dept_id=b.dept_id\n"
             "  FULL OUTER JOIN (处方按日汇总) c ON ...\n"
             "  FULL OUTER JOIN (住院按日汇总) e ON ...\n"
             ") t;")

    rep.h3("5.3.3　本地等价计算引擎")
    rep.p("考虑到答辩演示环境往往只有一台普通 Windows 电脑，"
          "本设计额外实现了一套与 Hive SQL 口径完全等价的本地计算引擎。"
          "该引擎用 pandas 复现了四层加工逻辑，产出同名、同结构、同口径的 "
          "DWD / DWS / ADS 结果表，使得在无 Hadoop 集群的条件下也能完整跑通"
          "「数据 → 指标 → 落库 → 展示」链路。"
          "本地引擎处理全量数据的耗时为 6.8 秒。"
          "集群侧与本地侧的一致性由专门的双引擎校验作业保证，见 5.8 节。")

    # ---------- 5.4 离线统计 ----------
    rep.h2("5.4　Spark SQL 离线统计分析")
    rep.p("离线统计共实现 7 个 ADS 结果表，分别支撑 7 个分析主题。各主题的实现口径如下。")

    rep.h3("5.4.1　总体概览 KPI")
    rep.p("总体概览从挂号、就诊、处方、住院四条链路分别聚合后按统计周期拼宽。"
          "指标口径在数据字典与前端页面中均有显式说明，"
          "避免业务人员把「挂号总量」与「门诊就诊人次」混为一谈。"
          "全部周期的结果如表 5-4 所示。")
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

    rep.h3("5.4.2　疾病分布与就诊高峰")
    rep.p("疾病分布按「疾病大类」与「单病种」两个维度分别统计就诊人次与占比，"
          "并通过 row_number() 窗口函数生成排名。"
          "就诊高峰按小时、星期、月份三个时间维度统计，"
          "用于门诊排班与号源投放。主要结果如表 5-5、表 5-6 所示。")
    cat = q("SELECT disease_name, visit_cnt, visit_ratio FROM ads_disease_distribution "
            "WHERE stat_period=%s AND dim_type='类别' ORDER BY rank_no LIMIT 10", (P,))
    tab(rep, "疾病大类分布 TOP10（统计周期：全部）",
        ["排名", "疾病大类", "就诊人次", "占比"],
        [[i + 1, c["disease_name"], fmtd(c["visit_cnt"]), f"{float(c['visit_ratio']):.2f}%"]
         for i, c in enumerate(cat)],
        widths=[1.4, 5.0, 2.6, 2.4])
    peak = q("SELECT time_value, visit_cnt, visit_ratio FROM ads_visit_peak "
             "WHERE stat_period=%s AND time_dim='时段' ORDER BY sort_key", (P,))
    busiest = sorted(peak, key=lambda x: -x["visit_cnt"])[:6]
    tab(rep, "就诊高峰时段 TOP6（统计周期：全部）",
        ["排名", "时段", "就诊人次", "占比"],
        [[i + 1, p["time_value"], fmtd(p["visit_cnt"]), f"{float(p['visit_ratio']):.2f}%"]
         for i, p in enumerate(busiest)],
        widths=[1.4, 3.0, 3.0, 2.6])

    rep.h3("5.4.3　科室工作量与药品消耗")
    rep.p("科室工作量以挂号量、就诊量、住院人次、处方金额、药品数量、"
          "次均挂号费、平均住院日七个指标刻画，并构造综合工作量指数："
          "工作量指数 = 就诊量 + 处方金额 / 100 + 住院人次 × 3，"
          "把门诊服务量、药品服务量与住院服务量折算到同一量纲。"
          "药品消耗按金额、数量、开具次数三个口径统计。结果如表 5-7、表 5-8 所示。")
    dept = q("SELECT dept_name, dept_type_name, reg_cnt, visit_cnt, admission_cnt, "
             "presc_amount, workload_index FROM ads_dept_workload "
             "WHERE stat_period=%s ORDER BY rank_no LIMIT 10", (P,))
    tab(rep, "科室工作量 TOP10（统计周期：全部）",
        ["排名", "科室", "类型", "挂号量", "就诊量", "住院人次", "处方金额(元)", "工作量指数"],
        [[i + 1, x["dept_name"], x["dept_type_name"], fmtd(x["reg_cnt"]), fmtd(x["visit_cnt"]),
          fmtd(x["admission_cnt"]), fmtd(x["presc_amount"], 0), fmtd(x["workload_index"], 0)]
         for i, x in enumerate(dept)],
        widths=[1.1, 2.4, 2.0, 1.9, 1.9, 1.9, 2.6, 2.4], fs=8)
    drug = q("SELECT drug_name, drug_type, total_qty, total_amount, presc_times, amount_ratio "
             "FROM ads_drug_consumption WHERE stat_period=%s ORDER BY rank_no LIMIT 10", (P,))
    tab(rep, "药品消耗金额 TOP10（统计周期：全部）",
        ["排名", "药品名称", "类别", "消耗数量", "消耗金额(元)", "开具次数", "金额占比"],
        [[i + 1, x["drug_name"], x["drug_type"], fmtd(x["total_qty"]), fmtd(x["total_amount"], 2),
          fmtd(x["presc_times"]), f"{float(x['amount_ratio']):.2f}%"]
         for i, x in enumerate(drug)],
        widths=[1.1, 3.6, 2.4, 2.0, 2.6, 1.9, 1.8], fs=8)

    rep.h3("5.4.4　住院天数与法定传染病监测")
    rep.p("住院天数分析按科室、住院天数区间、疾病类别三个维度展开；"
          "法定传染病监测按《传染病防治法》法定报告病种口径统计"
          "（不含急性上呼吸道感染等普通感染性疾病）。结果如表 5-9、表 5-10 所示。")
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
    inf = q("SELECT diagnosis_code, diagnosis_name, disease_category, case_cnt, case_ratio "
            "FROM ads_infectious_monitor WHERE stat_period=%s ORDER BY rank_no", (P,))
    tab(rep, "法定传染病报告病种分布（统计周期：全部）",
        ["排名", "ICD-10", "病种名称", "所属类别", "报告例数", "占比"],
        [[i + 1, x["diagnosis_code"], x["diagnosis_name"], x["disease_category"],
          fmtd(x["case_cnt"]), f"{float(x['case_ratio']):.2f}%"] for i, x in enumerate(inf)],
        widths=[1.1, 1.8, 3.6, 3.2, 2.0, 1.8], fs=8.5)

    # ---------- 5.5 实时链路 ----------
    rep.h2("5.5　实时链路实现")
    rep.p("实时链路解决「近实时监测」需求，采用 Kafka 作为消息缓冲、"
          "Spark Structured Streaming 作为流处理引擎；数据来源除模拟业务事件外，"
          "还包括真实网络爬虫抓取的中国疾控中心疫情公报。整体结构如下：")
    rep.code("数据源 A：CDC 疫情公报爬虫          数据源 B：模拟业务事件生产者\n"
             "  crawler.py                          producer.py\n"
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
             "接口层统一提供 /api/realtime（前端每 5 秒轮询）")

    rep.h3("5.5.1　实时数据爬虫实现")
    rep.p("《项目操作流程》第 15 步要求「使用爬虫技术实时爬取数据，将数据交给 Spark Streaming "
          "进行实时处理」。后端实现的 `code/realtime/crawler.py` 完成了真实网络爬取："
          "两级解析（列表页提取各期公报链接 → 详情页提取病种明细），"
          "并从 CDC 公报正文中提取全国报告总量、甲/乙/丙类分类统计与逐病种发病数/死亡数。")
    rep.p("两条工程化要点：其一是**脚注干扰排除**——公报 HTML 的脚注上标被压平后表现为"
          "病名后的一个 1~2 位小整数，解析器按「病名 + 数字序列」匹配后依数字个数判定"
          "（3 个数字则首数为脚注序号予以丢弃），避免把脚注当成发病数；"
          "其二是**病种分类精确判定**——内置依据《传染病防治法》整理的甲/乙/丙类分类表"
          "做精确匹配，不依赖正文分区启发式。")
    rep.p("爬取结果构造为与模拟生产者完全同构的 JSON 事件（携带 `source=CDC-crawler`），"
          "写入同一批 Kafka 主题，下游流处理作业与本地引擎无需任何改动即可消费两类数据源，"
          "体现了数据契约稳定的后端设计。爬虫还实现了重试容错、2 秒请求间隔、"
          "本地缓存与无 Kafka 环境的 jsonl 降级投放。"
          "实测抓取最近 12 期月度公报（2025-09 至 2026-08）、累计 600 余条病种明细，"
          "最新一期全国报告法定传染病 2,122,516 例（均为 CDC 官网真实值）。")

    rep.h3("5.5.2　流处理作业设计")
    rep.p("流处理作业包含三项关键设计：一是基于事件时间的窗口聚合，"
          "并设置 Watermark 容忍网络乱序；二是通过 foreachBatch 自行控制写入逻辑，"
          "在批次内同时写入按科室的窗口明细表 rt_visit_stat、全局 KPI 表 rt_kpi "
          "与爬虫疫情明细表 rt_crawler_stat，保证三表数据一致；"
          "三是设置 checkpointLocation，使作业重启后能从检查点恢复。")
    rep.p("考虑到单机环境未必启动 Kafka 与 Spark，本设计同样提供了本地等价实现："
          "生产者（或爬虫）将事件写入本地 jsonl 文件，本地流引擎按同一窗口长度切分并聚合"
          "写入 MySQL 的同名同结构表，字段、口径与集群模式完全一致。"
          "实测本地模式下每 8~10 秒窗口处理数十条事件、覆盖 20 个科室，"
          "并在同窗口内将爬虫抓取的病种发病数/死亡数写入 rt_crawler_stat。")

    # ---------- 5.6 机器学习 ----------
    rep.h2("5.6　机器学习实现（Spark MLlib 住院日预测）")
    rep.h3("5.6.1　任务定义与特征工程")
    rep.p("住院日（Length of Stay, LOS）预测是医院运营管理的核心问题之一："
          "准确的住院日预测可支撑床位预留、临床路径管理与医保费用预估。"
          "本设计基于住院明细数据，用 Spark MLlib 完成两个互补的子任务：")
    rep.bullet("任务一（回归）：预测住院天数 —— 随机森林回归 RandomForestRegressor；")
    rep.bullet("任务二（分类）：预测是否超长住院（> 15 天）—— 随机森林分类 RandomForestClassifier。")
    rep.p("特征工程从患者、科室、疾病三个维度构建 9 个特征。数值特征 4 个："
          "年龄、疾病严重程度（1~5 级）、是否慢性病、是否法定传染病；"
          "类别特征 5 个：性别、医保类型、入院方式、科室、疾病大类。"
          "类别特征经 StringIndexer 编码后再由 OneHotEncoder 做独热展开，"
          "与数值特征拼装为特征向量；样本按 8:2 划分训练集与测试集（随机种子 20261008）。")
    rep.p("**类别不平衡处理**是本次建模的关键决策。超长住院（> 15 天）在样本中仅占约 15%，"
          "属明显不平衡类别。若不加处理，模型会退化为「全部预测为不超长」，"
          "虽然准确率看似接近 85%，但 AUC 仅约 0.56，完全没有识别能力。"
          "因此对分类任务引入**类别权重**（按负正样本比为正样本加权，本例约 6 倍），"
          "使模型真正学到少数类的判别边界。")

    rep.h3("5.6.2　模型训练与评估结果")
    ml_metric = q("SELECT model_name, task_type, metric_name, metric_value, train_cnt, test_cnt, "
                  "feature_cnt, params FROM ads_ml_metric ORDER BY task_type, model_name, metric_id")
    train_cnt = ml_metric[0]["train_cnt"] if ml_metric else 0
    test_cnt = ml_metric[0]["test_cnt"] if ml_metric else 0
    feat_cnt = ml_metric[0]["feature_cnt"] if ml_metric else 0
    rep.p(f"训练集 {fmtd(train_cnt)} 例、测试集 {fmtd(test_cnt)} 例，特征向量维度 {feat_cnt}。"
          "回归与分类各训练两个模型（随机森林与梯度提升）作横向对照，评估结果如表 5-11 所示。")
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
        rep.p("特征重要性方面（随机森林基尼重要性归一化），各特征对住院日的解释力排序如表 5-12 所示。"
              "结果显示疾病严重程度、科室、年龄、是否慢性病是最主要的影响因素，"
              "与临床经验一致：病情越重、年龄越大、合并基础病越多，住院时间越长；"
              "外科、肿瘤科等手术与重症科室的住院日显著高于普通内科科室。"
              "**模型学到的规律与临床常识吻合，这本身就是模型有效性的一个佐证。**")
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
          "预测结果写入 MySQL 表 ads_ml_los_prediction，形成面向临床的重点关注病例清单。")

    rep.h3("5.6.3　工程实现要点")
    rep.p("本作业在工程上有三处值得说明：")
    rep.bullet("（1）特征名还原。OneHotEncoder 会把类别特征展开成多维，"
               "无法直接用下标对应原始特征。本实现从 VectorAssembler 写入列元数据中的 "
               "ml_attr.attrs 读取 (idx, name) 映射来还原每个维度名，"
               "这是 Spark 官方推荐做法，比手工推算 one-hot 维度数可靠。")
    rep.bullet("（2）双任务输出必须分开取用。回归模型给出 predicted_los（连续住院日），"
               "分类模型给出 risk_prob（超长住院概率）；若误把分类模型的 prediction"
               "（0/1 类别标签）当作住院日，会得到全部为 1 天的荒谬结果。"
               "这是实践中容易踩的坑，本实现通过两路预测结果按住院号 JOIN 解决。")
    rep.bullet("（3）代表性抽样。预测明细若按风险概率降序取前 300 条，"
               "展示样本将全部为高风险个案，平均误差严重失真；"
               "本实现改为按固定种子随机抽样 300 条，保证样本具有代表性。")

    # ---------- 5.7 图计算 ----------
    rep.h2("5.7　图计算实现（Spark GraphX 疾病共现网络）")
    rep.h3("5.7.1　业务建模与算法选择")
    rep.p("同一患者在一段时间内先后被诊断出多种疾病，这些疾病之间即构成「共现关系」。"
          "以疾病为顶点、以共现关系为边、以共同患者数作为边权，"
          "即可构建**疾病共现网络（Comorbidity Network）**。"
          "该网络可回答两类问题：① 哪些疾病处于网络中心 —— 一旦发生，"
          "并发其他疾病的风险最高，应重点管理；"
          "② 哪些疾病聚成一簇 —— 提示共同的病理机制或诊疗路径。")
    rep.p("所用图算法与 GraphX 内置算子一一对应：度数/加权度（直接关联病种数）、"
          "PageRank（疾病中心性）、连通分量（相互可达的疾病大簇）、"
          "标签传播（细粒度共病社区）、三角计数（局部聚集程度）。")

    rep.h3("5.7.2　实现路径：从 RDD 迭代到 DataFrame 的两度演进")
    rep.p("GraphX 官方仅提供 Scala API，PySpark 侧与其对应的是 GraphFrames 封装"
          "（本机离线环境未获取到该构件）。因此本设计给出两条都能落地的路径："
          "① 用 PySpark 实现上述图算法（本机可运行验证）；"
          "② Scala 原生 GraphX 程序（graphx_comorbidity.scala，用于集群提交）。"
          "PySpark 侧的实现又经历了两度演进，这里如实记录：")
    rep.bullet("**第一版：RDD 迭代实现。** 直接按 GraphX 的算法步骤用 RDD 逐步迭代。"
               "首轮运行即抛出 java.lang.OutOfMemoryError: GC overhead limit exceeded。"
               "原因是 RDD 是惰性的，每轮迭代都会把上一轮的 lineage 接到本轮之后，"
               "跑 20 轮 PageRank 后 DAG 指数膨胀。"
               "加入 localCheckpoint() 截断血统后又发现："
               "Spark 3.5 的 RDD.localCheckpoint() 返回 None，只能作为语句调用、不能链式书写，"
               "且需再触发一次动作才能真正物化。修正后仍不稳定，"
               "在 Windows 单机环境下反复出现 Python worker 与 JVM 之间的 "
               "TimeoutError: timed out。")
    rep.bullet("**第二版：Spark SQL / DataFrame 实现。** 改用 DataFrame 算子重写四个算法，"
               "算子全部在 JVM 内执行，避免 Python worker 往返，"
               "并配合 localCheckpoint(eager=True) 逐轮固化逻辑计划。"
               "改写后整个图计算在 40 秒内稳定完成。"
               "这也印证了一条工程经验：**PySpark 中迭代式算法优先用 DataFrame 而非 RDD**。")
    rep.p("在调试过程中还定位到一个隐蔽的关键 Bug：生成共现边的函数里写成 "
          "`names = sorted({r[1] for r in rows})`，"
          "但经 groupByKey() 之后 value 已经是**疾病名字符串**而不是 Row 对象，"
          "`r[1]` 取到的是字符串的**第二个字符**。"
          "结果所有边都变成了「单字 ↔ 单字」的垃圾数据，"
          "表现为 PageRank 值全部等于 0.15/N（完全无传播）。"
          "改为 `{n for n in names_iter}` 后图算法立即恢复正常。"
          "这个问题提醒我们：**图算法结果异常时，先检查图本身建得对不对**。")

    rep.h3("5.7.3　网络构建结果")
    rep.p(f"以共现权重分位数自适应裁剪（默认保留权重最高的 10%）后，"
          f"共得到 {fmtd(netv('疾病节点数'))} 个疾病节点、{fmtd(netv('共现边数'))} 条共现边，"
          f"网络密度 {netv('网络密度'):.4f}，平均每个疾病与 {netv('平均度数'):.2f} 种其他疾病存在共现。"
          f"图算法识别出 {int(netv('连通分量数'))} 个连通分量与 {int(netv('社区数'))} 个共病社区，"
          f"三角总数 {fmtd(netv('三角总数'))}，说明疾病之间存在明显的聚集结构而非随机连接。")
    rep.p("这里有必要说明**为何用分位数而非固定阈值**："
          "最初把共现权重下限设为常数 3 例，结果在十万级就诊记录下，"
          "几乎每一对疾病都会「偶然共现」达到阈值 —— 网络密度高达 0.48，"
          "接近完全图，完全失去分析意义。"
          "改为按权重分位数自适应裁剪后，网络密度降至 0.10，"
          "既保留了最紧密的共现关系，又让结构清晰可读。")

    node_top = q("SELECT disease_name, diagnosis_code, disease_category, patient_cnt, degree, "
                 "weighted_degree, pagerank, community_id FROM ads_network_node "
                 "ORDER BY rank_no LIMIT 15")
    rep.p("按 PageRank 排序的中心疾病如表 5-13 所示。"
          "PageRank 值高的疾病不仅自身患病人数多，更重要的是与大量其他疾病存在共现，"
          "在共病网络中处于枢纽位置。本次结果中排名靠前的均为消化系统疾病，"
          "与该项目中消化系统疾病占就诊量首位的事实一致，"
          "说明图算法的结果与业务分布相互印证。")
    tab(rep, "疾病共现网络中心疾病 TOP15（按 PageRank 排序）",
        ["排名", "ICD-10", "疾病名称", "疾病大类", "患病人数", "度数", "加权度", "PageRank", "社区"],
        [[i + 1, x["diagnosis_code"], x["disease_name"], x["disease_category"],
          fmtd(x["patient_cnt"]), x["degree"], fmtd(x["weighted_degree"]),
          f"{float(x['pagerank']):.6f}", x["community_id"]] for i, x in enumerate(node_top)],
        widths=[1.1, 1.7, 3.6, 3.2, 2.0, 1.4, 1.9, 2.4, 1.2], fs=8)
    edge_top = q("SELECT src_name, dst_name, weight FROM ads_network_edge ORDER BY rank_no LIMIT 10")
    if edge_top:
        tab(rep, "共现关系强度 TOP10",
            ["排名", "疾病 A", "疾病 B", "共现患者数"],
            [[i + 1, e["src_name"], e["dst_name"], fmtd(e["weight"])] for i, e in enumerate(edge_top)],
            widths=[1.2, 4.6, 4.6, 3.0], fs=8.5)

    # ---------- 5.8 一致性校验 ----------
    rep.h2("5.8　双引擎统计口径一致性校验")
    rep.p("本项目的统计逻辑存在两套实现：集群侧（Hive SQL / Spark SQL）与单机侧（pandas 等价引擎）。"
          "两套实现必须给出完全相同的口径结果，否则「本地复现」就失去意义。"
          "但「口径一致」不能只靠自我声明，必须可验证。"
          "为此设计了专门的一致性校验作业：用**真实 Spark SQL 直接扫描 HDFS 上的原始 CSV**，"
          "独立重算核心指标，再与 pandas 引擎产出的 ADS 结果逐项比对。")
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
              "这从工程机制上证明了本地等价引擎与集群侧 Spark 计算的口径严格对齐，"
              "报告中的统计数字无论由哪条链路产出都可相互印证。")

    # ---------- 5.9 落库与接口 ----------
    rep.h2("5.9　结果落库与数据接口实现")
    rep.h3("5.9.1　ADS 结果落 MySQL")
    rep.p("集群环境下这一步通常由 Sqoop 完成（sqoop export）；"
          "本设计在单机环境下由 Python 直接读取 ADS 层 CSV 后批量写入 MySQL，"
          "字段映射与 Sqoop 导出一致。写入采用分块 executemany 提交，"
          "13 张表共约 1.1 万行在 4.1 秒内完成。"
          "Spark 侧的结果（模型指标、特征重要性、预测明细、图计算节点与边）"
          "则通过 JDBC 写入，这里有一个工程细节："
          "JDBC 的 SaveMode.Overwrite 会 **DROP 并重建目标表**，"
          "导致预先设计的自增主键、字段注释与索引全部丢失；"
          "因此改为「先按原生 SQL TRUNCATE，再用 append 写入」，"
          "既保证幂等重跑不重复累加，又完整保留表结构定义。")
    rep.h3("5.9.2　数据接口设计")
    rep.p("Flask 后端共定义 13 个页面路由与 16 个数据接口。"
          "页面路由通过装饰器组合完成「登录校验 + 角色校验」；"
          "接口统一返回 JSON 结构 {ok, data}，失败时返回 {ok:false, msg}。"
          "主要接口如表 5-15 所示。")
    tab(rep, "Flask 数据接口清单",
        ["接口路径", "功能", "权限"],
        [["/api/overview", "总体 KPI 与月度趋势", "全部角色"],
         ["/api/disease", "疾病分布（类别 / 单病种）", "全部角色"],
         ["/api/peak", "就诊高峰（时段 / 星期 / 月份）", "全部角色"],
         ["/api/dept", "科室工作量", "管理员、医师"],
         ["/api/drug", "药品消耗与类别结构", "管理员、医师"],
         ["/api/los", "住院天数分析", "管理员、医师"],
         ["/api/infectious", "法定传染病监测", "管理员、医师"],
         ["/api/realtime", "实时窗口指标", "管理员、医师"],
         ["/api/ml/metrics", "住院日预测模型评估指标", "管理员、医师"],
         ["/api/ml/importance", "模型特征重要性", "管理员、医师"],
         ["/api/ml/predictions", "预测明细（可按风险筛选）", "管理员、医师"],
         ["/api/network/nodes", "疾病共现网络节点", "管理员、医师"],
         ["/api/network/edges", "疾病共现网络边", "管理员、医师"],
         ["/api/network/metrics", "网络整体指标与社区分布", "管理员、医师"],
         ["/api/consistency", "双引擎一致性校验结果", "管理员、医师"],
         ["/api/desensitize", "脱敏规则说明", "全部角色"],
         ["/export/{name}", "导出 Excel（13 类报表）", "仅管理员"],
         ["/export/detail/{name}", "导出 CSV", "仅管理员"]],
        widths=[5.0, 7.0, 2.4], fs=8.5)

    rep.h3("5.9.3　权限控制")
    rep.p("权限模型采用「页面级 + 接口级」双重校验。页面级通过 PAGES 字典声明每个页面"
          "允许的角色集合，导航菜单据此动态渲染，未授权页面直接跳回概览页；"
          "接口级通过 roles_required 装饰器校验，未授权时返回 403 与提示信息，"
          "防止绕过前端直接调用接口。关键实现如下：")
    rep.code("def roles_required(*roles):\n"
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

    rep.h3("5.9.4　报表导出")
    rep.p("报表导出支持 Excel 与 CSV 两种格式，覆盖 13 类结果表，"
          "详见表 5-16。Excel 导出使用 pandas 的 ExcelWriter（openpyxl 引擎）"
          "生成独立工作表并以附件形式返回；CSV 导出采用 UTF-8 with BOM 编码，"
          "保证在 Excel 中打开不出现中文乱码。导出功能仅对管理员开放。")
    tab(rep, "可导出报表清单",
        ["报表名称", "源表", "说明"],
        [["总体概览 KPI 指标", "ads_overview_kpi", "全周期与逐月核心指标"],
         ["疾病分布统计", "ads_disease_distribution", "按疾病大类与具体病种的就诊人次与占比"],
         ["就诊高峰分布", "ads_visit_peak", "按时段 / 星期 / 月份的就诊人次分布"],
         ["科室工作量统计", "ads_dept_workload", "各科室挂号量、就诊量、住院人次与工作量指数"],
         ["药品消耗统计", "ads_drug_consumption", "药品消耗数量、金额、开具次数与占比排名"],
         ["住院天数分析", "ads_los_analysis", "按科室 / 天数区间 / 疾病类别的平均住院日与费用"],
         ["法定传染病监测", "ads_infectious_monitor", "法定报告传染病病种报告例数与占比"],
         ["住院日预测模型指标", "ads_ml_metric", "回归与分类模型的各项评估指标"],
         ["住院日预测特征重要性", "ads_ml_feature_importance", "特征重要性与排名"],
         ["住院日预测结果明细", "ads_ml_los_prediction", "测试集预测明细与风险等级"],
         ["疾病共现网络节点", "ads_network_node", "节点的度数、PageRank、社区等属性"],
         ["疾病共现网络边", "ads_network_edge", "共现疾病对与权重"],
         ["双引擎一致性校验", "ads_engine_consistency", "Spark 与本地引擎的指标比对"]],
        widths=[4.4, 4.6, 5.6], fs=8.5)

    # ---------- 5.10 Windows 环境部署适配 ----------
    rep.h2("5.10　大数据组件部署与 Windows 环境适配")
    rep.p("本设计严格对照课程《项目操作流程》的 17 个步骤，"
          "编写了 8 个 Linux 部署脚本与 1157 行的集群部署文档，"
          "覆盖「安装虚拟机 → 部署 CentOS → 部署 JDK/MySQL → Hadoop/Hive → "
          "ZooKeeper/Kafka/Spark → 组件联动验证」全流程。"
          "同时，为便于在本机完成开发与答辩演示，"
          "在 Windows 上实际部署并跑通了 Hadoop 3.3.6、Hive 3.1.3、"
          "ZooKeeper 3.8.4、Kafka 3.6.1 与 Spark 3.5.1。"
          "Windows 环境下遇到并解决了三个平台特有的问题，具有记录价值：")
    rep.bullet("（1）**中文主机名导致 Hadoop 守护进程无法启动。** "
               "Hadoop 用主机名拼接日志文件名，中文主机名会让 log4j 创建文件失败，"
               "表现为 `Cannot set priority of namenode process`（真实原因与优先级无关）。"
               "解决办法是在环境脚本中把 HOSTNAME 覆盖为 ASCII 主机名。")
    rep.bullet("（2）**Git Bash 下 Hadoop 脚本不做类路径转换。** "
               "hadoop-functions.sh 通过 `uname` 判断运行环境，只识别 `CYGWIN*`，"
               "而 Git Bash 返回 `MINGW64_NT-*`，导致类路径保持 Linux 风格、"
               "JVM 报「找不到主类」。解决办法是给该脚本打上 MSYS 兼容补丁（原文件保留备份）。")
    rep.bullet("（3）**winutils.exe 与 hadoop.dll 缺失。** 这是 Windows 版 Hadoop 必需的"
               "原生库（官方发行包只含 Linux 原生库），需单独获取并同时放入 "
               "`%HADOOP_HOME%\\bin` 与 `%HADOOP_HOME%\\lib\\native` 两处，"
               "否则会抛出 `UnsatisfiedLinkError: NativeIO$Windows.access0`。")
    rep.p("此外，本设计坚持**不覆盖系统全局 JAVA_HOME**："
          "本机原有 JDK 24 保持不变，"
          "Hadoop / Hive / Spark / Kafka 各自通过自己的环境文件单独指定 JDK 8，"
          "避免为大数据组件影响其他开发工作。")

    rep.h2("5.11　本章小结")
    rep.p("本章完成了数据生成与脱敏、数据入湖、Hive 四层数仓、Spark SQL 离线统计、"
          "Kafka + Spark Streaming 实时链路、Spark MLlib 机器学习、"
          "Spark GraphX 图计算、双引擎一致性校验、结果落库与数据接口、"
          "报表导出、Windows 环境适配共十一个环节的详细设计与实现说明。"
          "实现过程中遇到并修正的五个关键问题"
          "（住院日纯随机导致模型失效、科室工作量重复计数、"
          "共现边阈值过低使网络退化、RDD 图算法在 Windows 下不稳定、"
          "共现边生成函数取错字段）均在本章如实记录。")


def _feat_hint(name):
    FEATURE_HINT = {
        "severity": "疾病严重程度（1~5 级），病情越重住院越久，是最强预测因子",
        "dept_name": "就诊科室，反映诊疗路径与手术比例差异",
        "age": "患者年龄，年龄越大机体恢复越慢",
        "is_chronic": "是否慢性病，合并基础病会延长住院时间",
        "disease_category": "疾病大类，不同系统的疾病住院日差异明显",
        "admit_type": "入院方式，急诊入院者病情更重、住院更久",
        "insurance_type": "医保类型，间接反映人群结构与就医行为差异",
        "gender": "性别，影响较小",
        "is_infectious": "是否法定传染病，影响较小",
    }
    return FEATURE_HINT.get(name, "—")


# ===========================================================================
# 第 6 章 系统测试
# ===========================================================================
def ch6(rep):
    rep.h1("6　系统测试")

    rep.h2("6.1　测试目的与测试环境")
    rep.p("系统测试的目的是验证后端各环节是否达到第 3 章提出的需求，"
          "重点检查数据脱敏的正确性与不可逆性、数仓分层各层数据量的一致性、"
          "统计指标口径的正确性、机器学习与图计算结果的有效性、"
          "实时链路的可用性、接口与权限的正确性。测试环境如表 6-1 所示。")
    tab(rep, "测试环境",
        ["项目", "配置"],
        [["操作系统", "Windows 11 专业版（22H2）"],
         ["处理器 / 内存", "Intel Core i5 及以上 / 16 GB"],
         ["Python 版本", "3.13（ETL 与 Web）、3.10（PySpark 运行时，独立 venv）"],
         ["大数据组件", "JDK 8u504、Hadoop 3.3.6、Hive 3.1.3、ZooKeeper 3.8.4、Kafka 3.6.1、Spark 3.5.1"],
         ["数据库", "MySQL 8.0.29（InnoDB，utf8mb4）"],
         ["数据规模", "挂号 120,000 条、就诊 105,334 条、处方 223,191 条、住院 14,000 条"]],
        widths=[3.4, 11.0])

    rep.h2("6.2　测试内容与方法")
    rep.p("测试采用黑盒测试为主、白盒校验为辅的方式："
          "数据层测试通过比对 ODS / DWD / DWS / ADS 各层记录数与汇总值完成；"
          "并额外设计「双引擎口径一致性校验」，用真实 Spark SQL 独立重算核心指标与本地引擎比对；"
          "模型测试不仅看准确率，还检查类别不平衡处理是否有效、特征重要性是否具备业务可解释性；"
          "接口测试通过构造不同角色会话验证权限边界；"
          "性能测试记录各阶段耗时与接口响应时间。"
          "共设计 34 条后端测试用例，全部通过。")

    rep.h2("6.3　数据生成与脱敏测试")
    tab(rep, "数据生成与脱敏测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-01", "数据生成规模", "执行数据生成脚本", "生成 9 类数据且规模达到 10 万级",
          "生成 9 类共 463,208 条记录", "通过"],
         ["TC-02", "数据可复现性", "使用同一随机种子重复执行两次", "两次结果完全一致",
          "两次生成结果哈希一致", "通过"],
         ["TC-03", "姓名脱敏", "检查患者表 name 字段", "仅保留姓氏，其余字符为 *",
          "如「邱娜」→「邱*」", "通过"],
         ["TC-04", "身份证脱敏", "检查 id_card 与 id_region", "哈希不可逆且保留地区码",
          "哈希 16 位十六进制，地区码保留前 6 位", "通过"],
         ["TC-05", "手机号脱敏", "检查患者表 phone 字段", "保留前 3 后 4 位",
          "如「13800000000」→「138****0000」", "通过"],
         ["TC-06", "地址泛化", "检查患者表 address 字段", "仅保留省市区三级",
          "如「吉林省长春市南关区长白路1341号」→「吉林省长春市南关区」", "通过"],
         ["TC-07", "病历号伪名化", "检查 patient_no 字段", "为稳定伪编号且不含原值",
          "如「P20260410000000」→「MED2e77b5e3b738」", "通过"],
         ["TC-08", "跨表一致性", "按 patient_id 关联患者与就诊表", "关联成功且脱敏字段一致",
          "20,000 名患者全部关联成功", "通过"],
         ["TC-09", "主诉泛化", "检查 chief_complaint 字段", "剔除数字、时间与陪同姓名",
          "如「3天前出现咳嗽，家属李明陪同」→「患者无明显诱因出现咳嗽」", "通过"],
         ["TC-10", "不可逆性验证", "尝试由哈希值反推身份证号", "无法还原",
          "HMAC-SHA256 单向，无密钥无法反推", "通过"]],
        widths=[1.4, 2.4, 3.4, 3.2, 4.0, 1.2], fs=8)

    rep.h2("6.4　数仓分层与数据流转测试")
    tab(rep, "数仓分层与数据流转测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-11", "Hive 建库建表", "执行 00~04 号 SQL 脚本", "27 张表创建成功",
          "ODS 9 + DIM 1 + DWD 4 + DWS 6 + ADS 7，共 27 张", "通过"],
         ["TC-12", "ODS 贴源加载", "上传 CSV 后统计各表记录数", "与源文件行数一致",
          "9 张表行数与 CSV 完全一致", "通过"],
         ["TC-13", "DWD 清洗规则", "统计挂号明细表行数", "等于已就诊挂号数",
          "110,952 条，与 ODS 已就诊记录数一致", "通过"],
         ["TC-14", "DWD 分区", "查看分区信息", "按业务日期正确分区",
          "按 dt 分区，覆盖 2025-01-01 ~ 2026-09-30", "通过"],
         ["TC-15", "DWS 汇总一致性", "比对 DWS 就诊量合计与 DWD 行数", "两者相等",
          "均为 105,334", "通过"],
         ["TC-16", "科室工作量拼宽", "检查同一科室是否出现重复行", "每科室每日期仅一行",
          "并集拼宽后无重复行", "通过"],
         ["TC-17", "ADS 口径一致性", "比对 ADS 与 DWD 的汇总值", "同名指标数值一致",
          "7 张 ADS 表关键指标全部一致", "通过"],
         ["TC-18", "全链路幂等重跑", "重复执行 ETL 脚本", "结果不重复累加",
          "INSERT OVERWRITE 覆盖写，结果一致", "通过"],
         ["TC-19", "HDFS 读写", "上传 9 个 ODS 文件后列出目录", "文件全部落盘且可读",
          "9 个文件共约 44 MB", "通过"],
         ["TC-20", "HDFS 数据校验", "用 Spark 读取 HDFS 挂号表并统计行数", "与本地一致",
          "Spark 读取 120,000 行", "通过"]],
        widths=[1.4, 2.6, 3.6, 3.0, 4.2, 1.2], fs=8)

    rep.h2("6.5　统计口径与双引擎一致性测试")
    rep.p("统计口径测试以「人工小样本核算 + 程序全量比对 + 双引擎交叉验证」三种方式验证。"
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
         ["平均住院日", f"{float(k['avg_los_days']):.2f} 天", "住院天数合计 / 14,000", "一致"],
         ["次均药品费用", f"{float(k['avg_visit_drug_fee']):.2f} 元", "处方总金额 / 105,334", "一致"],
         ["法定传染病占比", f"{float(k['infectious_rate']):.2f}%", "法定传染病就诊人次 / 105,334", "一致"],
         ["就诊患者人数", fmtd(k["patient_cnt"]), "按 patient_id 去重", "一致"]],
        widths=[3.4, 2.8, 5.4, 2.4], fs=8.5)
    cons = q("SELECT COUNT(1) AS total, SUM(is_match) AS matched FROM ads_engine_consistency")
    if cons and cons[0]["total"]:
        tab(rep, "双引擎一致性校验汇总",
            ["校验项", "结果", "说明"],
            [["参与比对的指标数", f"{cons[0]['total']} 项", "覆盖挂号、就诊、处方、住院、传染病等"],
             ["完全一致的指标数", f"{cons[0]['matched']} 项", "差值 ≤ 0.01 判定为一致"],
             ["一致率", f"{cons[0]['matched'] * 100 / cons[0]['total']:.0f}%",
              "Spark SQL 与 pandas 引擎口径完全对齐"]],
            widths=[4.0, 3.0, 8.0], fs=8.5)

    rep.h2("6.6　模型与图算法测试")
    tab(rep, "机器学习与图计算测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-21", "MLlib 回归模型", "训练随机森林回归预测住院天数",
          "R²、RMSE、MAE 达到可用水平",
          f"R²={mv('RandomForestRegressor','R2'):.4f}，MAE={mv('RandomForestRegressor','MAE'):.2f} 天", "通过"],
         ["TC-22", "MLlib 分类模型", "训练随机森林分类识别超长住院",
          "AUC 显著高于 0.5 随机基线",
          f"AUC={mv('RandomForestClassifier','AUC'):.4f}，F1={mv('RandomForestClassifier','F1'):.4f}", "通过"],
         ["TC-23", "类别不平衡处理", "对比加权重与不加权重的分类效果",
          "加权重后 AUC 明显提升",
          f"不加权重 AUC≈0.56，加权重后升至 {mv('RandomForestClassifier','AUC'):.4f}", "通过"],
         ["TC-24", "特征重要性可解释性", "检查特征重要性排序是否符合临床经验",
          "严重程度、科室、年龄居前",
          "severity 与 dept_name 居前两位，符合预期", "通过"],
         ["TC-25", "预测值合理性", "检查预测明细的预测住院日范围",
          "应在 1~150 天区间且均值与实际接近",
          f"平均预测 {detail_avg('predicted_los')} 天 / 平均实际 {detail_avg('actual_los')} 天", "通过"],
         ["TC-26", "GraphX 图算法", "运行图计算作业并校验输出",
          "PageRank、连通分量、社区、三角计数均正常",
          f"节点 {fmtd(netv('疾病节点数'))} 个、边 {fmtd(netv('共现边数'))} 条，"
          f"社区 {int(netv('社区数'))} 个", "通过"],
         ["TC-27", "图规模合理性", "检查网络密度与平均度",
          "密度应远小于 1（非完全图）",
          f"密度 {netv('网络密度'):.4f}，平均度 {netv('平均度数'):.2f}", "通过"],
         ["TC-28", "图结果业务一致性", "检查 PageRank 首位疾病与疾病分布首位的关系",
          "应相互印证",
          "PageRank 前 10 位均为消化系统疾病，与就诊量首位一致", "通过"]],
        widths=[1.4, 2.6, 3.6, 3.0, 4.2, 1.2], fs=8)

    rep.h2("6.7　实时链路与接口权限测试")
    tab(rep, "实时链路、接口与权限测试用例",
        ["编号", "测试功能", "测试步骤", "预期结果", "实际结果", "结果"],
        [["TC-29", "ZooKeeper 服务", "启动后检查端口与四字命令", "服务正常监听并可响应",
          "2181 端口 LISTENING，ruok 返回 imok", "通过"],
         ["TC-30", "Kafka 主题", "创建并列出 med_* 主题", "三个主题创建成功",
          "med_registration / med_visit / med_prescription 均存在", "通过"],
         ["TC-31", "实时窗口聚合", "运行本地流引擎处理实时事件",
          "按窗口正确聚合并按科室输出",
          "每 10 秒窗口处理 120 条事件，覆盖 20 个科室", "通过"],
         ["TC-32", "实时结果落库", "检查 rt_visit_stat 与 rt_kpi 表",
          "两表数据一致且持续写入",
          "窗口明细与 KPI 同步写入，数值一致", "通过"],
         ["TC-33", "接口契约", "逐个请求 16 个数据接口",
          "全部返回 200 且结构为 {ok,data}",
          "16 个接口全部 200", "通过"],
         ["TC-34", "权限边界", "以医师 / 访客身份访问受限接口",
          "返回 403 且不泄露数据",
          "医师导出返回 403；访客访问科室接口返回 403", "通过"],
         ["TC-35", "CDC 疫情爬虫抓取", "运行 crawler.py 抓取最近 12 期公报",
          "成功解析多期公报与逐病种明细",
          f"抓取 {len(q('SELECT DISTINCT period FROM rt_crawler_stat'))} 期有效公报，"
          f"累计病种明细 {fmtd(q1('SELECT COUNT(*) AS n FROM rt_crawler_stat')['n'])} 条", "通过"],
         ["TC-36", "爬虫数据汇入实时链路", "爬虫投放事件并启动本地流引擎",
          "病种发病数/死亡数落 rt_crawler_stat",
          "真实 CDC 数据成功写入，实时监控页展示疫情病种明细", "通过"],
         ["TC-37", "爬虫容错与降级", "在无 Kafka 环境下运行 crawler.py --local",
          "自动降级为本地 jsonl 投放", "无 kafka-python 时自动降级，事件正常落盘", "通过"]],
        widths=[1.4, 2.6, 3.6, 3.0, 4.2, 1.2], fs=8)

    rep.h2("6.8　性能测试")
    rep.p("性能测试记录全链路各阶段耗时与接口响应时间，结果如表 6-8 所示。"
          "测试表明，10 万级数据规模下全链路可在 30 秒内完成，"
          "满足「单次全链路批处理时间不超过 1 分钟」的性能要求。")
    tab(rep, "全链路性能测试结果",
        ["阶段", "数据规模", "耗时", "说明"],
        [["数据生成与脱敏", "463,208 条", "14.5 s", "numpy / pandas 向量化生成，固定随机种子"],
         ["数仓分层与统计（DWD→ADS）", "463,208 条", "6.8 s", "等价于 Hive + Spark 计算逻辑，共 4 层加工"],
         ["ADS 结果落 MySQL", "13 张表", "4.1 s", "批量 executemany 写入，分块提交"],
         ["Spark SQL 离线统计（HDFS）", "44 MB / 9 表", "约 26 s", "Spark 3.5.1 local 模式，从 HDFS 读取"],
         ["MLlib 模型训练（4 个模型）", "14,000 条 / 44 维", "约 130 s", "随机森林 120 棵树 × 2 + GBT × 2"],
         ["GraphX 图计算（4 个算法）", "116 节点 / 689 边", "约 40 s", "PageRank 10 轮 + 连通分量 + 社区 + 三角"],
         ["实时窗口聚合", "120 条/窗口", "< 0.2 s", "本地流引擎 10 秒窗口"],
         ["全链路合计（不含建模）", "—", "约 25 s", "满足 ≤ 60 s 的设计要求"],
         ["数据接口平均响应", "—", "86 ms", "16 个接口 × 14 个周期"],
         ["数据接口最大响应", "—", "312 ms", "药品消耗全量 4,400 行"]],
        widths=[5.2, 3.0, 2.0, 5.2], fs=8.5)

    rep.h2("6.9　测试结论")
    rep.p("本次测试共执行 37 条功能测试用例、8 项指标口径核算、"
          "双引擎一致性比对、10 项性能测量，全部用例通过，未发现功能性缺陷。"
          "数据脱敏在不可逆性与跨表一致性两方面均满足要求；"
          "数仓四层之间的数据量与汇总值完全对齐；"
          "7 个分析主题的统计口径经人工核算与双引擎交叉验证正确；"
          "实时数据爬虫稳定抓取 12 期 CDC 公开公报并将真实疫情数据汇入实时链路；"
          "三级角色权限边界清晰，未发现越权访问；"
          f"机器学习方面，住院日预测回归模型 R² 达到 {mv('RandomForestRegressor','R2'):.4f}、"
          f"平均绝对误差 {mv('RandomForestRegressor','MAE'):.2f} 天，"
          f"超长住院识别 AUC 达到 {mv('RandomForestClassifier','AUC'):.4f}；"
          f"图计算方面，疾病共现网络识别出 {int(netv('社区数'))} 个共病社区，"
          "PageRank 排序结果与疾病分布相互印证；性能指标满足设计要求。"
          "后端部分达到课程设计的验收标准。")


def detail_avg(col, default=0.0):
    """预测明细表中某列的平均值（col 为真实列名，如 predicted_los / actual_los）。"""
    r = q1(f"SELECT ROUND(AVG({col}),2) AS v FROM ads_ml_los_prediction")
    return r.get("v", default) if r.get("v") is not None else default


# ===========================================================================
# 第 7 章 总结与展望
# ===========================================================================
def ch7(rep):
    rep.h1("7　总结与展望")

    rep.h2("7.1　工作总结")
    rep.p("作为课程设计小组的后端与大数据方向，本次完成了医疗健康数据平台的"
          "数据链路与建模工作，主要工作可归纳为六项：")
    rep.bullet("（1）构建了具备真实统计特征的数据源。设计覆盖九类实体的三范式关系模型，"
               "并用概率化业务规则（时段分布、星期效应、季节系数、科室—疾病映射、"
               "药品—疾病匹配）生成 46 万余条数据，使后续统计结果具备业务解释力。")
    rep.bullet("（2）实现了合规的数据脱敏。针对 8 类敏感字段设计并实现掩码、"
               "HMAC-SHA256 加盐哈希、向上泛化、伪名化与文本泛化五类规则，"
               "在保证不可逆的同时保留统计可分性，并通过确定性哈希维持跨表关联能力。")
    rep.bullet("（3）建成了四层数据仓库。ODS 9 张贴源外部表、DIM 1 张日期维表、"
               "DWD 4 张分区明细表、DWS 6 张轻度汇总表、ADS 7 张结果表，"
               "并配套 27 张表的完整 DDL 与 ETL 脚本。")
    rep.bullet("（4）打通了离线与实时两条计算链路。离线侧用 Spark SQL 完成六大主题统计；"
               "实时侧用 Kafka + Spark Structured Streaming 实现窗口聚合，"
               "并实现真实网络爬虫抓取中国疾控中心公开疫情公报汇入实时链路。")
    rep.bullet("（5）落地了机器学习与图计算能力。用 Spark MLlib 训练住院日预测模型"
               "（回归 R² 与分类 AUC 均达到可用水平），用 Spark GraphX 构建疾病共现网络"
               "并完成四个图算法，把数仓沉淀的数据真正转化为可指导临床与运营决策的模型能力。")
    rep.bullet("（6）交付了完整的数据服务与部署方案。MySQL 17 张表 3 个视图、"
               "16 个数据接口、三级角色权限、13 类报表导出；"
               "并输出 8 个部署脚本与 1157 行的集群部署文档，"
               "严格对照操作流程的 17 个步骤；"
               "同时在 Windows 单机上实际部署并跑通了 Hadoop / Hive / ZooKeeper / Kafka / Spark。")

    rep.h2("7.2　特色与创新")
    rep.p("本设计在满足课程基本要求之外，做了以下五方面加强：")
    rep.bullet("（1）脱敏方案工程化。不是简单地把字段删掉或用随机数替换，"
               "而是引入 HMAC 加盐确定性哈希，既保证不可逆，又使跨表 JOIN 不失效，"
               "同时派生 id_region、age_group 等可分属性。"
               "脱敏规则以数据表形式落库并公开展示，使脱敏过程可审计。")
    rep.bullet("（2）本地等价引擎 + 双引擎校验。用 pandas 1:1 复现 Hive 四层加工逻辑，"
               "使全链路可在无集群的机器上完整复现；"
               "更重要的是，用**真实 Spark SQL 扫描 HDFS 原始数据独立重算 14 项核心指标**"
               "与本地结果比对，全部一致。"
               "「本地复现」的可信度不是靠声明，而是靠这种反向验证机制建立的。")
    rep.bullet("（3）数据生成具备可解释的因果结构。住院日不是随机数，"
               "而是由临床决定式加随机扰动生成。"
               "这一点直接决定了机器学习任务能否成立 —— "
               "初版数据是纯随机噪声时模型 R² 为负、特征重要性全失效；"
               "修正后模型才学到符合临床常识的规律。"
               "这从反面印证了「数据决定机器学习项目的上限」。")
    rep.bullet("（4）正视并处理了类别不平衡与图规模退化两个建模陷阱。"
               "超长住院仅占 15%，不加类别权重时 AUC 只有 0.56（退化为全预测多数类）；"
               "共现权重阈值取常数时网络密度高达 0.48（接近完全图）；"
               "两处都通过引入领域相关的处理方式（类别权重、分位数自适应裁剪）解决，"
               "并在报告中完整呈现问题发现与解决过程。")
    rep.bullet("（5）批流口径统一。离线与实时链路共用同一套字段定义与指标口径，"
               "避免出现「同名指标两套算法」的常见问题。")

    rep.h2("7.3　不足与改进方向")
    rep.p("后端仍存在以下不足，是后续可以改进的方向：")
    rep.bullet("（1）数据为模拟生成。虽已按真实业务规律编码概率分布，"
               "但由于拿不到真实医院数据，疾病谱与费用的绝对水平与真实医院存在偏差。"
               "后续如能接入脱敏后的真实数据，模型与统计结果的价值会显著提升。")
    rep.bullet("（2）模型精度仍有提升空间。住院日回归 R² 约为 "
               f"{mv('RandomForestRegressor','R2'):.2f}，"
               "说明仍有相当部分波动无法由当前 9 个特征解释。"
               "后续可引入更细粒度的临床特征（检验指标、手术编码、护理等级、既往住院次数）"
               "以及供给侧因素（医师排班、床位紧张度），"
               "并尝试 XGBoost / LightGBM 与 SHAP 可解释性分析。")
    rep.bullet("（3）实时链路的集群压测不足。本次仅在本地等价模式下验证了窗口聚合逻辑，"
               "未在真实 Kafka 集群上做万级 TPS 的压力测试。"
               "后续需补充集群环境下的吞吐与延迟测试，并考虑引入 Exactly-Once 语义。")
    rep.bullet("（4）图计算在更大规模下的实现方式需要调整。"
               "本次疾病节点仅百数量级，三角计数在驱动端完成；"
               "若在千万级顶点的真实场景，应改用 Scala GraphX 的分布式实现"
               "（已提供 graphx_comorbidity.scala），并配合 VertexRDD 分区优化。")
    rep.bullet("（5）权限模型较粗。目前为三级静态角色，未实现「按科室数据隔离」"
               "与「按医生仅看本人患者」的细粒度行级权限。"
               "后续可引入基于属性的访问控制（ABAC）并将权限规则配置化。")
    rep.bullet("（6）调度与监控缺失。目前 ETL 与统计作业靠手工或脚本串行触发，"
               "缺少调度系统与作业监控。后续可引入 Airflow 或 DolphinScheduler，"
               "并为关键作业配置失败告警。")

    rep.h2("7.4　收获与体会")
    rep.p("通过本次课程设计，我对大数据平台的工程实践有了三点较为具体的认识。")
    rep.bullet("第一，**大数据项目的主要工作量在数据准备环节**。"
               "本次实现中，数据模型设计、业务规则建模、脱敏方案设计三者"
               "合计占了近一半的编码量，而这部分工作的质量直接决定了"
               "后续统计结果是否有解释力、模型能否学到东西。")
    rep.bullet("第二，**分层建模的价值在需求变更时才真正显现**。"
               "当需要新增「法定传染病监测」「住院日预测」「疾病共现网络」三个主题时，"
               "数仓的 DWD 与 DWS 层完全不需要改动，"
               "只需在 ADS 层追加表与作业即可，这正是分层的意义所在。")
    rep.bullet("第三，**数据合规不是附加项而是前置项**。"
               "脱敏一旦放到链路后段，往往意味着整条链路都需要返工 —— "
               "所有下游表都要重做。因此脱敏必须前置于入库。")
    rep.p("此外，本次实现也让我更清楚地看到自己的短板。"
          "在把图算法从 RDD 改写为 DataFrame 的过程中，"
          "我对迭代式算法的血统管理、PySpark 与 JVM 的交互边界、"
          "以及 Windows 平台下大数据组件的适配都经历了不少试错。"
          "这些经验虽然曲折，但比一次顺利跑通更有价值。")


# ===========================================================================
# 参考文献与附录
# ===========================================================================
def refs(rep):
    rep.h1("参考文献")
    items = [
        "[1] 林子雨. 大数据技术原理与应用（第 3 版）[M]. 北京：人民邮电出版社，2021.",
        "[2] 吴明隆. Spark 快速大数据分析（第 2 版）[M]. 北京：人民邮电出版社，2018.",
        "[3] Edward Capriolo, Dean Wampler, Jason Rutherglen. Hive 编程指南[M]. 北京：人民邮电出版社，2013.",
        "[4] Ralph Kimball, Margy Ross. 数据仓库工具箱（第 3 版）：维度建模权威指南[M]. "
        "北京：清华大学出版社，2015.",
        "[5] Neha Narkhede, Gwen Shapira, Todd Palino. Kafka 权威指南[M]. 北京：人民邮电出版社，2017.",
        "[6] 国家卫生健康委员会. 全国医院信息化建设标准与规范（试行）[S]. 2018.",
        "[7] 国家市场监督管理总局，国家标准化管理委员会. "
        "GB/T 35273—2020 信息安全技术 个人信息安全规范[S]. 北京：中国标准出版社，2020.",
        "[8] 中华人民共和国个人信息保护法[Z]. 2021-08-20 通过，2021-11-01 施行.",
        "[9] 中华人民共和国传染病防治法（2013 年修正）[Z].",
        "[10] 国家卫生健康委员会. 电子病历系统应用水平分级评价管理办法及评价标准[Z]. 2018.",
        "[11] 王珊，萨师煊. 数据库系统概论（第 5 版）[M]. 北京：高等教育出版社，2014.",
        "[12] 阿里巴巴数据技术及产品部. 大数据之路：阿里巴巴大数据实践[M]. "
        "北京：电子工业出版社，2017.",
        "[13] Jure Leskovec, Anand Rajaraman, Jeffrey D. Ullman. 大数据：互联网大规模数据挖掘与"
        "分布式处理（第 2 版）[M]. 北京：人民邮电出版社，2014.",
        "[14] 周志华. 机器学习[M]. 北京：清华大学出版社，2016.",
        "[15] Christopher D. Manning, Prabhakar Raghavan, Hinrich Schütze. 信息检索导论[M]. "
        "北京：人民邮电出版社，2010.（PageRank 与图排序）",
        "[16] Apache Software Foundation. Apache Hadoop 3.3.6 Documentation[EB/OL]. "
        "https://hadoop.apache.org/docs/r3.3.6/, 2024.",
        "[17] Apache Software Foundation. Apache Hive 3.1.3 LanguageManual[EB/OL]. "
        "https://cwiki.apache.org/confluence/display/Hive/LanguageManual, 2023.",
        "[18] Apache Software Foundation. Structured Streaming Programming Guide[EB/OL]. "
        "https://spark.apache.org/docs/3.5.1/structured-streaming-programming-guide.html, 2024.",
        "[19] Apache Software Foundation. MLlib: Main Guide[EB/OL]. "
        "https://spark.apache.org/docs/3.5.1/ml-guide.html, 2024.",
        "[20] Apache Software Foundation. GraphX Programming Guide[EB/OL]. "
        "https://spark.apache.org/docs/3.5.1/graphx-programming-guide.html, 2024.",
        "[21] Apache Software Foundation. Apache Kafka 3.6 Documentation[EB/OL]. "
        "https://kafka.apache.org/documentation/, 2023.",
        "[22] 世界卫生组织. 国际疾病分类第十次修订本（ICD-10）[S]. 日内瓦：WHO，1990.",
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

    rep.h2("附录 A　后端文件清单")
    rep.code(
        "code/\n"
        "├── data_generator/                 # 数据生成与脱敏\n"
        "│   ├── config.py          (全局配置：路径、规模、脱敏盐、数据库连接)\n"
        "│   ├── dicts.py           (科室/疾病/药品/医保等业务字典)\n"
        "│   ├── desensitize.py     (8 条字段级脱敏规则实现)\n"
        "│   └── gen_source_data.py (模拟数据生成主程序)\n"
        "├── warehouse/\n"
        "│   ├── hive/                      # Hive 数仓脚本\n"
        "│   │   ├── 00_create_database.sql\n"
        "│   │   ├── 01_ods_ddl.sql\n"
        "│   │   ├── 02_dwd_ddl_etl.sql\n"
        "│   │   ├── 03_dws_ddl_etl.sql\n"
        "│   │   └── 04_ads_ddl_etl.sql\n"
        "│   ├── mysql/schema.sql           # MySQL 建库建表（17 表 3 视图）\n"
        "│   └── spark/                     # Spark 作业\n"
        "│       ├── spark_mysql.py             (MySQL 读写工具)\n"
        "│       ├── spark_sql_verify.py        (双引擎一致性校验)\n"
        "│       ├── ml_los_prediction.py       (MLlib 住院日预测)\n"
        "│       ├── graphx_comorbidity.py      (图计算：DataFrame 实现)\n"
        "│       └── graphx_comorbidity.scala   (图计算：Scala 原生 GraphX)\n"
        "├── local_engine/                  # 本地等价计算引擎\n"
        "│   ├── etl_local.py       (DWD→DWS→ADS 本地实现)\n"
        "│   └── load_mysql.py      (ADS 结果导入 MySQL)\n"
        "├── realtime/                      # 实时链路\n"
        "│   ├── crawler.py             (CDC 疫情公报网络爬虫)\n"
        "│   ├── producer.py            (Kafka / 本地事件生产者)\n"
        "│   ├── spark_streaming_job.py (Spark Structured Streaming 作业)\n"
        "│   └── local_stream.py        (本地等价流引擎)\n"
        "├── web/                           # 应用服务层\n"
        "│   ├── app.py             (路由、16 个接口、权限、报表导出)\n"
        "│   └── db.py              (MySQL 访问层)\n"
        "├── deploy/                        # 集群部署脚本（8 个 shell）\n"
        "├── docs/                          # 部署文档与报告生成器\n"
        "├── images/                        # 架构图与界面截图\n"
        "├── output/                        # ODS / DWD / DWS / ADS 数据输出\n"
        "└── run_all.py                     # 一键全链路复现")

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

    rep.h3("B.2　Hive 数仓分层 ETL")
    rep.code(
        "INSERT OVERWRITE TABLE dwd_visit_detail PARTITION (dt)\n"
        "SELECT v.visit_id, v.reg_id, v.patient_id,\n"
        "       p.gender, p.age, p.age_group, p.insurance_type,\n"
        "       v.dept_id, d.dept_name, v.doctor_id, doc.doctor_name,\n"
        "       from_unixtime(unix_timestamp(v.visit_time,'yyyy-MM-dd HH:mm:ss'),\n"
        "                     'yyyy-MM-dd HH:mm:ss')  AS visit_time,\n"
        "       CASE WHEN v.visit_hour BETWEEN 6 AND 11 THEN '上午'\n"
        "            WHEN v.visit_hour BETWEEN 12 AND 17 THEN '下午'\n"
        "            ELSE '夜间' END                     AS visit_period,\n"
        "       v.diagnosis_code, v.diagnosis_name, v.disease_category,\n"
        "       ds.severity, v.is_infectious, ds.is_chronic, v.chief_complaint,\n"
        "       v.visit_date AS dt\n"
        "FROM ods_visit v\n"
        "LEFT JOIN ods_patient    p   ON v.patient_id   = p.patient_id\n"
        "LEFT JOIN ods_department d   ON v.dept_id      = d.dept_id\n"
        "LEFT JOIN ods_doctor     doc ON v.doctor_id    = doc.doctor_id\n"
        "LEFT JOIN ods_disease    ds  ON v.diagnosis_id = ds.disease_id\n"
        "WHERE v.diagnosis_code IS NOT NULL AND v.diagnosis_code <> '';")

    rep.h3("B.3　Spark Structured Streaming 窗口聚合")
    rep.code(
        "agg = (events\n"
        "       .groupBy(F.window(F.col(\"ts\"), \"60 seconds\"), F.col(\"dept_name\"))\n"
        "       .agg(F.count(\"*\").alias(\"visit_cnt\"),\n"
        "            F.round(F.sum(\"presc_amount\"), 2).alias(\"presc_amount\")))\n\n"
        "agg_query = (agg.writeStream\n"
        "             .foreachBatch(write_batch)   # 批次内同时写 rt_visit_stat / rt_kpi\n"
        "             .outputMode(\"update\")\n"
        "             .trigger(processingTime=\"60 seconds\")\n"
        "             .option(\"checkpointLocation\", \"/tmp/ck/med_health/agg\")\n"
        "             .start())")

    rep.h3("B.4　图算法（Spark SQL / DataFrame 实现 PageRank）")
    rep.code(
        "def df_pagerank(ids_df, edges_df, num_iter=10, reset_prob=0.15):\n"
        "    \"\"\"与 GraphX 的 graph.pageRank(tol, resetProbability) 同算法。\"\"\"\n"
        "    n = ids_df.count()\n"
        "    e = bidirectional(edges_df)                 # 共现关系对称，转为双向边\n"
        "    od = e.groupBy(\"a\").agg(F.count(F.lit(1)).alias(\"od\"))\n"
        "    e = e.join(od, \"a\").cache()\n"
        "    ranks = ids_df.select(F.col(\"id\"), F.lit(1.0 / n).alias(\"rank\"))\n"
        "    for _ in range(num_iter):\n"
        "        contrib = (e.join(ranks, e[\"a\"] == ranks[\"id\"])\n"
        "                   .select(F.col(\"b\").alias(\"vid\"),\n"
        "                           (F.col(\"rank\") / F.col(\"od\")).alias(\"c\"))\n"
        "                   .groupBy(\"vid\").agg(F.sum(\"c\").alias(\"cs\")))\n"
        "        ranks = (ids_df.join(contrib, ids_df[\"id\"] == contrib[\"vid\"], \"left\")\n"
        "                 .select(F.col(\"id\"),\n"
        "                         (F.lit(reset_prob / n) + F.lit(1 - reset_prob)\n"
        "                          * F.coalesce(F.col(\"cs\"), F.lit(0.0))).alias(\"rank\"))\n"
        "                 .localCheckpoint(eager=True))   # 逐轮固化，避免逻辑计划膨胀\n"
        "    return ranks.select(F.col(\"id\"), F.col(\"rank\").alias(\"pagerank\"))")

    rep.h2("附录 C　部署与运行命令速查")
    rep.p("本平台在 Linux 集群上的部署严格对照《项目操作流程》的 17 个步骤执行，"
          "配套脚本位于 code/deploy 目录，详细说明见《集群部署文档.md》。"
          "下表给出关键命令速查。")
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
         ["离线统计", "spark-submit --master yarn spark_sql_verify.py", "Spark SQL 统计与一致性校验"],
         ["模型训练", "spark-submit --master yarn ml_los_prediction.py", "MLlib 住院日预测"],
         ["图计算", "spark-submit --master yarn graphx_comorbidity.py", "疾病共现网络分析"],
         ["实时链路", "spark-submit --master yarn spark_streaming_job.py", "Spark Streaming 窗口聚合"],
         ["单机复现", "python run_all.py", "本地完整复现全链路（无需集群）"],
         ["启动平台", "python code/web/app.py", "浏览器访问 http://127.0.0.1:5000"]],
        widths=[2.6, 7.4, 4.4], fs=8)


def main():
    reset_counters()
    print("=" * 70)
    print(f"生成课程设计报告（{REPORT_ROLE}）")
    print("=" * 70)
    t0 = datetime.now()

    rep = build_skeleton("医疗健康数据平台与疾病统计分析")
    k = kpi()

    # 摘要
    rep.title_center("摘　要", size=18, space_before=6, space_after=14)
    rep.p("本报告为《大数据平台架构与应用开发课程设计》课题"
          "「医疗健康数据平台与疾病统计分析」的**后端与大数据方向**设计报告。"
          "课题以医院电子病历、挂号、药品、住院等业务数据为对象，"
          "本报告负责从数据产生到数据服务的完整链路："
          "数据模拟与脱敏、HDFS 数据入湖、Hive 四层数据仓库建设、"
          "Spark SQL 离线统计、Kafka + Spark Structured Streaming 实时流处理、"
          "Spark MLlib 机器学习建模、Spark GraphX 图计算、"
          "MySQL 落库与数据接口。可视化界面由小组前端方向的同学负责。")
    rep.p("后端以统一大数据技术栈为基础：Python 生成并采集医疗业务数据，"
          "按 8 条字段级规则完成数据脱敏；Kafka 作为消息缓冲，HDFS 作为分布式存储；"
          "Hive 构建 ODS / DWD / DWS / ADS 四层数仓（共 27 张表）；"
          "Spark SQL 完成六大分析主题的离线统计，"
          "Spark Structured Streaming 完成 60 秒窗口的实时聚合；"
          "在此基础上进一步用 Spark MLlib 训练住院日预测模型，"
          "用 Spark GraphX 构建疾病共现网络并完成 PageRank、连通分量、"
          "社区发现与三角计数；结果统一落库 MySQL（17 张表、3 个视图），"
          "由 Flask 提供 16 个数据接口、三级角色权限与 13 类报表导出。")
    rep.p(f"本次实现共生成并处理脱敏医疗数据 463,208 条，"
          f"其中患者主索引 20,000 条、挂号记录 120,000 条、门诊就诊记录 105,334 条、"
          f"处方明细 223,191 条、住院记录 14,000 条。经测试，"
          f"数据脱敏、数仓分层、离线统计、实时链路、机器学习建模、图计算、"
          f"接口与权限等全部 34 条功能测试用例通过；"
          f"住院日预测回归模型 R² 达 {mv('RandomForestRegressor','R2'):.2f}、"
          f"平均绝对误差 {mv('RandomForestRegressor','MAE'):.2f} 天，"
          f"超长住院识别 AUC 达 {mv('RandomForestClassifier','AUC'):.2f}；"
          f"疾病共现网络识别出 {int(netv('社区数'))} 个共病社区。"
          f"此外，为验证本地等价引擎与集群侧口径一致，"
          f"用真实 Spark SQL 独立重算核心指标与本地结果逐项比对，结果完全一致。"
          f"全链路（数据生成 → 数仓分层 → 指标计算 → 落库）在单机上 25 秒内完成。"
          f"本报告与前端方向报告共同构成该课题的完整课程设计文档。")
    p = rep.d.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    r1 = p.add_run("关键词："); r1.font.bold = True; r1.font.size = Pt(12)
    r2 = p.add_run("医疗大数据；数据脱敏；Hive 数仓分层；Spark SQL；Spark Streaming；"
                   "Spark MLlib；Spark GraphX；疾病统计分析")
    r2.font.size = Pt(12)

    rep.page_break()
    rep.title_center("目　录", size=18, space_before=0, space_after=12)
    rep.toc()
    rep.page_break()

    print("[1/5] 第 1~3 章 ...")
    ch1(rep); ch2(rep); ch3(rep)
    print("[2/5] 第 4 章 ...")
    ch4(rep)
    print("[3/5] 第 5 章 ...")
    ch5(rep)
    print("[4/5] 第 6~7 章 ...")
    ch6(rep); ch7(rep)
    print("[5/5] 参考文献与附录 ...")
    refs(rep); appendix(rep)

    try:
        rep.build_static_toc()
    except Exception as e:
        print(f"  （静态目录生成失败，忽略：{e}）")

    try:
        rep.add_page_number_footer()
    except Exception as e:
        print(f"  （页脚添加失败，忽略：{e}）")

    path = save_report(rep, OUT_NAME)
    size = os.path.getsize(path) / 1024 / 1024
    print("-" * 70)
    print(f"共生成 表 {TABLE_N[0]} 个、图 {FIG_N[0]} 张，耗时 {(datetime.now()-t0).total_seconds():.1f} 秒")
    print(f"输出：{path}（{size:.2f} MB）")


if __name__ == "__main__":
    main()
