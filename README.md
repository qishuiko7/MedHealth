# 医疗健康数据平台与疾病统计分析

[![CI](https://github.com/qishuiko7/MedHealth/actions/workflows/ci.yml/badge.svg)](https://github.com/qishuiko7/MedHealth/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org/)

> 基于 Hadoop 生态的大数据仓库 + 机器学习 + 实时流处理 + Web 可视化全链路项目
> 课程：《大数据平台架构与应用开发课程设计》 · 2026 年 10 月

一个完整的医疗健康数据分析平台：从**模拟数据生成与脱敏**，到 **Hive 四层数据仓库建模**，再到 **Spark SQL 统计分析 / MLlib 机器学习 / GraphX 图计算**，最终通过 **Flask Web 平台**提供 13 个页面、34 张图表的可视化展示，并附带 **Kafka + Spark Streaming 实时链路**。

---

## 目录

- [项目架构](#项目架构)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [目录结构](#目录结构)
- [核心模块](#核心模块)
- [数据仓库分层](#数据仓库分层)
- [文档索引](#文档索引)
- [说明](#说明)

---

## 项目架构

```
┌─────────────────────────────────────────────────────────────┐
│                      数据源层                                 │
│   模拟数据生成器 (Python)  →  脱敏处理  →  ODS 贴源层          │
│   实时数据源 (CDC 爬虫 / 事件生产者)                           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                   数据仓库层 (Hive)                           │
│   ODS 贴源层 → DWD 明细层 → DWS 汇总层 → ADS 应用层            │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    计算分析层                                 │
│   Spark SQL 离线统计  │  MLlib 住院时长预测  │  GraphX 共病网络 │
│   Kafka + Spark Streaming 实时监控                           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                     应用展示层                                │
│         MySQL 结果库  →  Flask Web 平台（13 页 / 34 图）       │
└─────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层次 | 技术 |
|---|---|
| **数据生成** | Python 3.10+、Faker、NumPy、Pandas |
| **数据仓库** | Apache Hive 3.x、HDFS、MySQL 8.0（元数据 + 结果库） |
| **计算引擎** | Apache Spark 3.x（Spark SQL / MLlib / GraphX / Streaming） |
| **消息队列** | Apache Kafka、ZooKeeper |
| **机器学习** | MLlib（随机森林、GBT、逻辑回归）、GraphX（共病网络） |
| **Web 平台** | Flask、Jinja2、ECharts、Bootstrap |
| **部署** | Shell 脚本、CentOS 集群、Windows 单机环境 |

---

## 快速开始

### 前置准备

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 配置环境变量（可选，不配也能跑，会使用演示默认值）
cp .env.example .env
#    然后编辑 .env，填入你自己的数据库口令等

# 3. 准备 MySQL 8.0（需可被 127.0.0.1:3306 访问）

# 4. 导入数据库备份（含全部业务数据与统计结果）
mysql -u root -p < database/med_health_数据备份.sql
```

#### 环境变量说明

所有配置项均支持**环境变量优先**，未设置时回落到代码内默认值：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `MED_MYSQL_HOST` | `127.0.0.1` | 数据库地址 |
| `MED_MYSQL_PORT` | `3306` | 数据库端口 |
| `MED_MYSQL_USER` | `root` | 数据库用户 |
| `MED_MYSQL_PASSWORD` | `123456` | 数据库口令 |
| `MED_MYSQL_DATABASE` | `med_health` | 业务库名 |
| `MED_WEB_HOST` | `127.0.0.1` | Web 监听地址 |
| `MED_WEB_PORT` | `5000` | Web 监听端口 |
| `MED_WEB_SECRET_KEY` | `dev-only-change-me` | Flask 会话密钥 |
| `MED_ADMIN_PWD` | `admin123` | 管理员口令 |
| `MED_DOCTOR_PWD` | `doctor123` | 医师口令 |
| `MED_VIEWER_PWD` | `viewer123` | 访客口令 |

> `.env` 已被 `.gitignore` 排除，不会提交到仓库，可安全填写真实口令。
> 完整模板见 [.env.example](.env.example)。

### 方式一：只看可视化平台（最常用，约 10 秒）

平台所需的统计结果、模型指标、网络数据已预置在数据库备份中，无需重跑 Spark。

```bash
# 完成上面的「前置准备」后，直接启动
cd web
python app.py
```

浏览器访问 **http://127.0.0.1:5000**

### 方式二：一条命令跑通全链路

```bash
python run_all.py --web --realtime 6
```

依次完成：**数据生成与脱敏 → 数仓四层加工 → 离线统计 → 导入 MySQL → 实时链路 → 启动 Web**

### 方式三：分步执行

```bash
# ① 生成并脱敏源数据 → output/ods
cd data_generator && python gen_source_data.py

# ② 数仓分层统计 → output/dwd|dws|ads
cd ../local_engine && python etl_local.py

# ③ 建库建表并导入 MySQL
cd ../local_engine && python load_mysql.py

# ④ 启动可视化平台
cd ../web && python app.py

# ⑤ 实时链路（另开终端）
cd ../realtime && python crawler.py --local --rate 12
cd ../realtime && python local_stream.py --window 10
```

### 方式四：完整大数据链路

需要额外启动 HDFS / YARN / ZooKeeper / Kafka / Hive / Spark，详见 [集群部署文档](docs/集群部署文档.md)。

---

## 目录结构

```
MedHealth/
├── data_generator/          # 模拟数据生成与脱敏
│   ├── gen_source_data.py   # 数据生成主程序
│   ├── dicts.py             # 字典表（疾病、药品、科室等）
│   └── config.py            # 数据库与路径配置
├── local_engine/            # 本地数仓加工引擎
│   ├── etl_local.py         # 四层 ETL 统计
│   └── load_mysql.py        # 结果导入 MySQL
├── warehouse/               # 大数据数仓脚本
│   ├── hive/                # Hive DDL 与 ETL（ODS/DWD/DWS/ADS）
│   ├── spark/               # Spark SQL / MLlib / GraphX 作业
│   └── mysql/               # MySQL 建表脚本
├── realtime/                # 实时链路
│   ├── crawler.py           # CDC 疫情公报爬虫
│   ├── local_stream.py      # 本地流式窗口计算
│   └── spark_streaming_job.py  # Spark Streaming 作业
├── web/                     # Flask 可视化平台
│   ├── app.py               # 应用入口与路由
│   ├── templates/           # 13 个页面模板
│   └── static/              # CSS / JS / ECharts / Bootstrap
├── database/                # 数据库备份
│   └── med_health_数据备份.sql  # 完整业务数据 + 统计结果（0.97 MB）
├── deploy/                  # Linux 集群部署脚本（9 个）
├── docs/                    # 项目文档
├── images/                  # 架构图与界面截图
├── report/                  # 课程设计报告（前端版 / 后端版）
├── requirements.txt         # Python 依赖清单
└── run_all.py               # 一键全链路复现脚本
```

---

## 核心模块

### 1. 数据生成与脱敏

`data_generator/` 生成符合业务语义的模拟医疗数据，并对敏感字段做脱敏：

- 姓名打码（`邱*`）、手机号打码（`135****1091`）、邮箱打码
- 身份证号哈希化存储
- 覆盖患者、挂号、就诊、处方、住院、药品、疾病等业务实体

### 2. 数据仓库四层建模

`warehouse/hive/` 提供完整的数仓分层脚本：

| 分层 | 说明 | 主要表 |
|---|---|---|
| **ODS** | 贴源层，保留原始数据 | `ods_patient`、`ods_visit`、`ods_registration`、`ods_prescription` |
| **DWD** | 明细层，清洗与维度关联 | `dwd_visit_detail`、`dwd_registration_detail`、`dwd_prescription_detail`、`dwd_admission_detail` |
| **DWS** | 汇总层，按主题聚合 | `dws_disease_d`、`dws_drug_d`、`dws_dept_d` |
| **ADS** | 应用层，直接服务展示 | 疾病统计、科室指标、药品分析、模型结果 |

### 3. 机器学习与图计算

`warehouse/spark/` 中的分析作业：

- **`ml_los_prediction.py`** — 基于 MLlib 的住院时长（LOS）预测，对比随机森林、GBT、逻辑回归等模型
- **`graphx_comorbidity.py`** — 基于 GraphX 的疾病共病网络分析，挖掘疾病关联关系
- **`spark_sql_verify.py`** — Spark SQL 统计结果校验

### 4. 实时链路

`realtime/` 实现实时数据采集与流式计算：

- `crawler.py` — 爬取 CDC 公开疫情公报作为实时数据源
- `local_stream.py` — 本地滑动窗口流式计算（无需 Kafka 即可演示）
- `spark_streaming_job.py` — Kafka + Spark Streaming 生产级流处理

### 5. Web 可视化平台

`web/` 基于 Flask + ECharts 构建，包含 **13 个页面、34 张图表**：

- 总览驾驶舱、疾病统计分析、科室分析、药品分析
- 患者画像、住院分析、模型预测结果
- 共病网络图（ECharts 关系图）、实时数据监控

---

## 数据仓库分层

```
ODS (贴源层)
  └─ 原始数据落库，保持与源系统一致
       ↓
DWD (明细层)
  └─ 数据清洗、去重、维度关联，形成业务明细宽表
       ↓
DWS (汇总层)
  └─ 按疾病 / 药品 / 科室等主题做轻度聚合
       ↓
ADS (应用层)
  └─ 面向具体分析场景的结果表，直接供 Web 平台查询
```

---

## 文档索引

| 文档 | 说明 |
|---|---|
| [交付说明.md](交付说明.md) | 完整交付物清单与验收要点 |
| [快速运行.md](快速运行.md) | 三种运行档次的操作卡片 |
| [docs/项目运行手册.md](docs/项目运行手册.md) | 单机复现与集群运行的完整命令说明 |
| [docs/集群部署文档.md](docs/集群部署文档.md) | 对照《项目操作流程》17 个步骤的集群部署 |
| [docs/按操作流程17步部署手册.md](docs/按操作流程17步部署手册.md) | 逐步部署手册 |

---

## 说明

### 数据说明

本项目所有医疗数据均为**程序生成的模拟数据**，不含任何真实个人信息：

- 姓名、手机号、邮箱均做打码处理
- 身份证号以哈希值形式存储
- 地址为虚构的行政区划组合

### 关于原始迁移包

原始迁移包约 **5.7 GB**，其中包含现成虚拟机镜像（4.86 GB）、大数据组件安装包、MySQL 免安装版等**环境素材**。本仓库保留了**工程源码、数据库备份、依赖清单、部署脚本与全部文档**，足以在新电脑上复现：

| 复现所需 | 本仓库位置 |
|---|---|
| Python 依赖 | `requirements.txt` |
| 数据库数据与统计结果 | `database/med_health_数据备份.sql` |
| 集群部署脚本 | `deploy/`（9 个脚本，含一键启动） |
| 源码与文档 | 全量保留 |

**需自行准备的环境**（这些是通用软件，不属于项目内容）：

- MySQL 8.0（或使用任意可访问的 MySQL 实例）
- 大数据环境（可选）：Hadoop 3.x + Hive 3.x + Spark 3.x + Kafka + ZooKeeper
- Python 3.10+

`output/` 目录下的数据产物（约 134 MB 的 CSV）为可再生的中间结果，未纳入版本控制，运行 `run_all.py` 即可重新生成。

### 报告说明

`report/` 中的课程设计报告分为**前端版**与**后端版**，按小组分工各自侧重。封面中的专业班级、学号、姓名等信息已留空。

---

## License

本项目基于 [MIT License](LICENSE) 开源，可自由用于学习、二次开发与商业用途。

### 数据与合规声明

本项目所有医疗数据均为**程序生成的模拟数据**，不含任何真实个人信息：

- 姓名、手机号、邮箱均做打码处理
- 身份证号以哈希值形式存储
- 地址为虚构的行政区划组合
- 代码与文档中的示例值均为占位符（如 `13800000000`、`zhangsan@example.com`）

> ⚠️ **免责声明**：本项目为课程设计作品，仅用于技术学习与交流。若用于真实医疗场景，需自行完成等级保护、数据安全法等合规评估，并替换全部演示账号与口令。

