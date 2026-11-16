# -*- coding: utf-8 -*-
"""
项目全局配置 —— 医疗健康数据平台与疾病统计分析
《大数据平台架构与应用开发课程设计》
"""
import os

# ---------------------------------------------------------------------------
# 路径配置
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../code
PROJECT_DIR = os.path.dirname(BASE_DIR)                                   # 项目根目录
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

ODS_DIR = os.path.join(OUTPUT_DIR, "ods")
DWD_DIR = os.path.join(OUTPUT_DIR, "dwd")
DWS_DIR = os.path.join(OUTPUT_DIR, "dws")
ADS_DIR = os.path.join(OUTPUT_DIR, "ads")
SQL_DIR = os.path.join(BASE_DIR, "warehouse", "hive")
IMG_DIR = os.path.join(BASE_DIR, "images")

for _d in (ODS_DIR, DWD_DIR, DWS_DIR, ADS_DIR):
    os.makedirs(_d, exist_ok=True)

# ---------------------------------------------------------------------------
# 数据规模（"10 万级"）
# ---------------------------------------------------------------------------
RANDOM_SEED = 20261008

N_DEPARTMENT = 20
N_DOCTOR = 300
N_DRUG = 200
N_DISEASE = 120
N_PATIENT = 20000
N_REGISTRATION = 120000          # 主事实表：10 万级
VISIT_RATE = 0.95                # 挂号后实际就诊比例
N_ADMISSION = 14000              # 住院记录
PRESC_LINES_MIN, PRESC_LINES_MAX = 1, 4   # 单次就诊处方明细行数（1~4 行）

DATE_START = "2025-01-01"
DATE_END = "2026-09-30"

# ---------------------------------------------------------------------------
# 脱敏配置
# ---------------------------------------------------------------------------
# 哈希加盐值（用于病历号 / 身份证等不可逆脱敏）
HASH_SALT = "MED_PLATFORM_2026_JLAU"

# ---------------------------------------------------------------------------
# MySQL 配置（本地）
# ---------------------------------------------------------------------------
MYSQL = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "med_health",
    "charset": "utf8mb4",
}

# ---------------------------------------------------------------------------
# Flask 配置
# ---------------------------------------------------------------------------
WEB_HOST = "127.0.0.1"
WEB_PORT = 5000
WEB_SECRET_KEY = "med-health-platform-secret-key-2026"

# 平台账号（用户名 -> 密码, 显示名, 角色）
# 角色：admin 管理员（全部权限）/ doctor 医师（不可导出敏感明细）/ viewer 访客（只读）
USERS = {
    "admin":  {"password": "admin123",  "display": "系统管理员", "role": "admin"},
    "doctor": {"password": "doctor123", "display": "临床医师",   "role": "doctor"},
    "viewer": {"password": "viewer123", "display": "数据访客",   "role": "viewer"},
}

# ---------------------------------------------------------------------------
# Kafka / 实时链路配置
# ---------------------------------------------------------------------------
KAFKA_BOOTSTRAP = "hadoop01:9092"
KAFKA_TOPICS = {
    "registration": "med_registration",
    "visit": "med_visit",
    "prescription": "med_prescription",
}

# 实时指标窗口（秒）
STREAM_WINDOW_SECONDS = 60
