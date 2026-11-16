# -*- coding: utf-8 -*-
"""
医疗健康数据平台与疾病统计分析 —— Flask 可视化服务
==================================================================
对应《项目操作流程》第 14 / 17 步：
    「将存储的离线数据展示到 flask 前端中」
    「将存储的实时数据展示到 flask 前端中」

技术栈：Flask + PyMySQL + Bootstrap 5 + ECharts 5
数据来源：MySQL 库 med_health（由 ADS 结果表与维度表构成）

启动：
    python app.py
浏览器访问： http://127.0.0.1:5000
内置账号： admin/admin123（管理员） doctor/doctor123（医师） viewer/viewer123（访客）
"""
from __future__ import annotations

import io
import os
import sys
from datetime import datetime, timedelta
from functools import wraps

import pandas as pd
from flask import (Flask, Response, flash, jsonify, redirect, render_template,
                   request, send_file, session, url_for)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))

import config as C
import db

app = Flask(__name__)
app.secret_key = C.WEB_SECRET_KEY

# ---------------------------------------------------------------------------
# 权限矩阵：页面 / 接口 / 导出
#    admin  管理员：全部功能
#    doctor 医师  ：可看全部分析页与实时页，不允许导出批量数据
#    viewer 访客  ：仅可看概览、疾病分布、就诊高峰，不可导出
# ---------------------------------------------------------------------------
PAGES = {
    "dashboard":   {"label": "综合概览大屏", "icon": "◧", "roles": {"admin", "doctor", "viewer"}},
    "disease":     {"label": "疾病分布分析", "icon": "◈", "roles": {"admin", "doctor", "viewer"}},
    "peak":        {"label": "就诊高峰分析", "icon": "◐", "roles": {"admin", "doctor", "viewer"}},
    "dept":        {"label": "科室工作量",   "icon": "▤", "roles": {"admin", "doctor"}},
    "drug":        {"label": "药品消耗分析", "icon": "◆", "roles": {"admin", "doctor"}},
    "los":         {"label": "住院天数分析", "icon": "▥", "roles": {"admin", "doctor"}},
    "infectious":  {"label": "传染病监测",   "icon": "✦", "roles": {"admin", "doctor"}},
    "desensitize": {"label": "数据脱敏规则", "icon": "⛨", "roles": {"admin", "doctor", "viewer"}},
    "realtime":    {"label": "实时数据监控", "icon": "◉", "roles": {"admin", "doctor"}},
    "ml":          {"label": "住院日预测模型", "icon": "◎", "roles": {"admin", "doctor"}},
    "network":     {"label": "疾病共现网络", "icon": "⬡", "roles": {"admin", "doctor"}},
    "report":      {"label": "报表导出",     "icon": "⬇", "roles": {"admin"}},
    "about":       {"label": "平台说明",     "icon": "ℹ", "roles": {"admin", "doctor", "viewer"}},
}


def current_user():
    return session.get("user")


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper


def roles_required(*roles):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                return redirect(url_for("login", next=request.path))
            if u["role"] not in roles:
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "msg": "当前角色无权限访问该数据"}), 403
                flash("当前角色无权限访问该页面", "warning")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return wrapper
    return deco


def visible_pages():
    u = current_user()
    if not u:
        return []
    return [{"key": k, **v} for k, v in PAGES.items() if u["role"] in v["roles"]]


@app.context_processor
def inject_globals():
    return {"nav_pages": visible_pages(), "user": current_user(), "now": datetime.now()}


def ok(data):
    return jsonify({"ok": True, "data": data})


# ===========================================================================
# 登录 / 登出
# ===========================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = (request.form.get("username") or "").strip()
        p = request.form.get("password") or ""
        row = db.query_one("SELECT username, password, display, role FROM sys_user WHERE username=%s", (u,))
        if row and row["password"] == p:
            session["user"] = {"name": row["username"], "display": row["display"], "role": row["role"]}
            session.permanent = True
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("用户名或密码错误，请重新输入", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ===========================================================================
# 页面
# ===========================================================================
def page(key, template):
    @login_required
    @roles_required(*PAGES[key]["roles"])
    def view():
        return render_template(template, page_key=key,
                               periods=db.get_periods(), depts=db.get_depts())
    view.__name__ = f"page_{key}"
    return view


app.add_url_rule("/", "dashboard", page("dashboard", "dashboard.html"))
app.add_url_rule("/disease", "disease", page("disease", "disease.html"))
app.add_url_rule("/peak", "peak", page("peak", "peak.html"))
app.add_url_rule("/dept", "dept", page("dept", "dept.html"))
app.add_url_rule("/drug", "drug", page("drug", "drug.html"))
app.add_url_rule("/los", "los", page("los", "los.html"))
app.add_url_rule("/infectious", "infectious", page("infectious", "infectious.html"))
app.add_url_rule("/desensitize", "desensitize", page("desensitize", "desensitize.html"))
app.add_url_rule("/realtime", "realtime", page("realtime", "realtime.html"))
app.add_url_rule("/ml", "ml", page("ml", "ml.html"))
app.add_url_rule("/network", "network", page("network", "network.html"))
app.add_url_rule("/report", "report", page("report", "report.html"))
app.add_url_rule("/about", "about", page("about", "about.html"))


# ===========================================================================
# API
# ===========================================================================
def _p(default="全部"):
    return request.args.get("period") or default


@app.route("/api/overview")
@login_required
def api_overview():
    period = _p()
    row = db.query_one(
        "SELECT stat_period, reg_cnt, visited_cnt, visit_rate, visit_cnt, admission_cnt, "
        "avg_los_days, presc_amount, drug_qty, admission_cost, avg_reg_fee, avg_visit_drug_fee, "
        "infectious_cnt, infectious_rate, patient_cnt, dept_cnt, "
        "DATE_FORMAT(update_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS update_time "
        "FROM ads_overview_kpi WHERE stat_period=%s", (period,))
    # 月度趋势（用于大屏折线）
    trend = db.query(
        "SELECT stat_period, visit_cnt, admission_cnt, avg_los_days, presc_amount "
        "FROM ads_overview_kpi WHERE stat_period<>'全部' ORDER BY stat_period")
    return ok({"kpi": row, "trend": trend})


@app.route("/api/disease")
@login_required
def api_disease():
    period, dim = _p(), request.args.get("dim_type", "类别")
    rows = db.query(
        "SELECT disease_name, disease_category, is_infectious, visit_cnt, visit_ratio, rank_no "
        "FROM ads_disease_distribution WHERE stat_period=%s AND dim_type=%s ORDER BY rank_no",
        (period, dim))
    cats = db.query(
        "SELECT disease_name, visit_cnt, visit_ratio FROM ads_disease_distribution "
        "WHERE stat_period=%s AND dim_type='类别' ORDER BY rank_no", (period,))
    return ok({"list": rows, "categories": cats})


@app.route("/api/peak")
@login_required
def api_peak():
    period = _p()
    rows = db.query(
        "SELECT time_dim, time_value, sort_key, visit_cnt, visit_ratio FROM ads_visit_peak "
        "WHERE stat_period=%s ORDER BY time_dim, sort_key", (period,))
    out = {"时段": [], "星期": [], "月份": []}
    for r in rows:
        out.setdefault(r["time_dim"], []).append(r)
    return ok(out)


@app.route("/api/dept")
@roles_required("admin", "doctor")
def api_dept():
    period = _p()
    rows = db.query(
        "SELECT dept_name, dept_type_name, reg_cnt, visit_cnt, admission_cnt, presc_amount, "
        "drug_qty, avg_reg_fee, los_avg_days, workload_index, rank_no "
        "FROM ads_dept_workload WHERE stat_period=%s ORDER BY rank_no", (period,))
    return ok(rows)


@app.route("/api/drug")
@roles_required("admin", "doctor")
def api_drug():
    period = _p()
    rows = db.query(
        "SELECT drug_name, drug_type, total_qty, total_amount, presc_times, qty_ratio, "
        "amount_ratio, rank_no FROM ads_drug_consumption WHERE stat_period=%s ORDER BY rank_no",
        (period,))
    types = db.query(
        "SELECT drug_type, SUM(total_amount) AS amount, SUM(total_qty) AS qty "
        "FROM ads_drug_consumption WHERE stat_period=%s GROUP BY drug_type ORDER BY amount DESC",
        (period,))
    return ok({"list": rows, "by_type": types})


@app.route("/api/los")
@roles_required("admin", "doctor")
def api_los():
    period, dim = _p(), request.args.get("dim_type", "科室")
    rows = db.query(
        "SELECT dim_type, dim_value, admission_cnt, avg_los, los_max, los_min, avg_cost, "
        "total_cost, cure_rate, rank_no FROM ads_los_analysis "
        "WHERE stat_period=%s AND dim_type=%s ORDER BY rank_no", (period, dim))
    return ok(rows)


@app.route("/api/infectious")
@roles_required("admin", "doctor")
def api_infectious():
    period = _p()
    rows = db.query(
        "SELECT diagnosis_code, diagnosis_name, disease_category, case_cnt, case_ratio, rank_no "
        "FROM ads_infectious_monitor WHERE stat_period=%s ORDER BY rank_no", (period,))
    by_month = db.query(
        "SELECT stat_period, SUM(case_cnt) AS case_cnt FROM ads_infectious_monitor "
        "WHERE stat_period<>'全部' GROUP BY stat_period ORDER BY stat_period")
    return ok({"list": rows, "by_month": by_month})


@app.route("/api/desensitize")
@login_required
def api_desensitize():
    return ok(db.query("SELECT * FROM desensitize_rule ORDER BY rule_id"))


@app.route("/api/realtime")
@roles_required("admin", "doctor")
def api_realtime():
    stats = db.query(
        "SELECT DATE_FORMAT(window_start,'%%Y-%%m-%%d %%H:%%i:%%s') AS window_start, "
        "DATE_FORMAT(window_end,'%%Y-%%m-%%d %%H:%%i:%%s') AS window_end, "
        "dept_name, visit_cnt, case_cnt, death_cnt, presc_amount, "
        "DATE_FORMAT(update_time,'%%Y-%%m-%%d %%H:%%i:%%s') AS update_time "
        "FROM rt_visit_stat ORDER BY window_end DESC, visit_cnt DESC LIMIT 200")
    kpi = db.query_one(
        "SELECT DATE_FORMAT(window_end,'%%Y-%%m-%%d %%H:%%i:%%s') AS window_end, reg_cnt, visit_cnt, "
        "presc_amount, top_dept, msg_per_sec, "
        "DATE_FORMAT(update_time,'%%Y-%%m-%%d %%H:%%i:%%s') AS update_time "
        "FROM rt_kpi ORDER BY window_end DESC LIMIT 1")
    # 爬虫（CDC 公报）实时明细：按最新窗口返回病种发病/死亡数
    crawler = db.query(
        "SELECT DATE_FORMAT(window_end,'%%Y-%%m-%%d %%H:%%i:%%s') AS window_end, "
        "period, disease_name, case_cnt, death_cnt, source, source_url, "
        "DATE_FORMAT(update_time,'%%Y-%%m-%%d %%H:%%i:%%s') AS update_time "
        "FROM rt_crawler_stat "
        "WHERE window_end = (SELECT MAX(window_end) FROM rt_crawler_stat) "
        "ORDER BY case_cnt DESC LIMIT 100")
    return ok({"stats": stats, "kpi": kpi, "crawler": crawler})


# ===========================================================================
# 机器学习（Spark MLlib）结果接口
# ===========================================================================
@app.route("/api/ml/metrics")
@roles_required("admin", "doctor")
def api_ml_metrics():
    """模型评估指标，按任务类型分组返回，便于前端按模型对照展示。"""
    rows = db.query(
        "SELECT task_name, model_name, task_type, metric_name, metric_value, "
        "train_cnt, test_cnt, feature_cnt, params, "
        "DATE_FORMAT(update_time,'%%Y-%%m-%%d %%H:%%i:%%s') AS update_time "
        "FROM ads_ml_metric ORDER BY task_type, model_name, metric_id")
    return ok(rows)


@app.route("/api/ml/importance")
@roles_required("admin", "doctor")
def api_ml_importance():
    level = request.args.get("level", "column")     # column=按特征列汇总 / detail=具体取值
    model = "RandomForestRegressor" if level == "column" else "RandomForestRegressor-明细"
    rows = db.query(
        "SELECT feature_name, importance, rank_no FROM ads_ml_feature_importance "
        "WHERE model_name=%s ORDER BY rank_no", (model,))
    return ok(rows)


@app.route("/api/ml/predictions")
@roles_required("admin", "doctor")
def api_ml_predictions():
    risk = request.args.get("risk", "")
    sql = ("SELECT adm_no, dept_name, disease_category, age, severity, actual_los, "
           "predicted_los, residual, risk_prob, risk_label, is_long_stay "
           "FROM ads_ml_los_prediction ")
    args = ()
    if risk:
        sql += "WHERE risk_label=%s "
        args = (risk,)
    sql += "ORDER BY risk_prob DESC LIMIT 300"
    rows = db.query(sql, args)
    stat = db.query_one(
        "SELECT COUNT(1) AS cnt, ROUND(AVG(ABS(residual)),2) AS mae, "
        "ROUND(AVG(predicted_los),2) AS avg_pred, ROUND(AVG(actual_los),2) AS avg_actual, "
        "SUM(is_long_stay) AS long_cnt, SUM(risk_label='高风险') AS high_cnt "
        "FROM ads_ml_los_prediction")
    return ok({"list": rows, "stat": stat})


# ===========================================================================
# 图计算（Spark GraphX）结果接口
# ===========================================================================
@app.route("/api/network/nodes")
@roles_required("admin", "doctor")
def api_network_nodes():
    limit = int(request.args.get("limit", 60))
    rows = db.query(
        "SELECT diagnosis_code, disease_name, disease_category, is_infectious, patient_cnt, "
        "degree, weighted_degree, pagerank, component_id, community_id, triangle_cnt, rank_no "
        "FROM ads_network_node ORDER BY rank_no LIMIT %s", (limit,))
    return ok(rows)


@app.route("/api/network/edges")
@roles_required("admin", "doctor")
def api_network_edges():
    limit = int(request.args.get("limit", 200))
    rows = db.query(
        "SELECT src_name, dst_name, src_category, dst_category, weight, rank_no "
        "FROM ads_network_edge ORDER BY rank_no LIMIT %s", (limit,))
    return ok(rows)


@app.route("/api/network/metrics")
@roles_required("admin", "doctor")
def api_network_metrics():
    metrics = db.query("SELECT metric_name, metric_value FROM ads_network_metric")
    # 社区规模分布（用于展示共病亚群结构）
    comms = db.query(
        "SELECT community_id, COUNT(1) AS node_cnt, SUM(patient_cnt) AS patient_sum "
        "FROM ads_network_node GROUP BY community_id ORDER BY node_cnt DESC LIMIT 15")
    cats = db.query(
        "SELECT disease_category, COUNT(1) AS node_cnt, SUM(patient_cnt) AS patient_sum, "
        "ROUND(AVG(pagerank),6) AS avg_pr FROM ads_network_node "
        "GROUP BY disease_category ORDER BY avg_pr DESC")
    return ok({"metrics": metrics, "communities": comms, "categories": cats})


# ===========================================================================
# 双引擎一致性校验接口
# ===========================================================================
@app.route("/api/consistency")
@roles_required("admin", "doctor")
def api_consistency():
    rows = db.query(
        "SELECT metric_name, spark_value, pandas_value, diff, is_match, "
        "DATE_FORMAT(update_time,'%%Y-%%m-%%d %%H:%%i:%%s') AS update_time "
        "FROM ads_engine_consistency ORDER BY id")
    return ok(rows)


# ===========================================================================
# 报表导出
# ===========================================================================
@app.route("/api/export_counts")
@roles_required("admin")
def api_export_counts():
    """报表导出页展示「当前周期行数」。"""
    period = _p()
    out = {}
    for key, (table, _) in EXPORT_MAP.items():
        if period == "全部":
            row = db.query_one(f"SELECT COUNT(1) AS c FROM {table}")
        else:
            row = db.query_one(f"SELECT COUNT(1) AS c FROM {table} WHERE stat_period=%s", (period,))
        out[key] = row["c"] if row else 0
    return ok(out)


EXPORT_MAP = {
    "overview":     ("ads_overview_kpi", "总体概览KPI指标"),
    "disease":      ("ads_disease_distribution", "疾病分布统计"),
    "peak":         ("ads_visit_peak", "就诊高峰分布"),
    "dept":         ("ads_dept_workload", "科室工作量统计"),
    "drug":         ("ads_drug_consumption", "药品消耗统计"),
    "los":          ("ads_los_analysis", "住院天数分析"),
    "infectious":   ("ads_infectious_monitor", "法定传染病监测"),
    "ml_metric":    ("ads_ml_metric", "住院日预测模型指标"),
    "ml_importance": ("ads_ml_feature_importance", "住院日预测特征重要性"),
    "ml_prediction": ("ads_ml_los_prediction", "住院日预测结果明细"),
    "network_node": ("ads_network_node", "疾病共现网络节点"),
    "network_edge": ("ads_network_edge", "疾病共现网络边"),
    "consistency":  ("ads_engine_consistency", "双引擎统计口径一致性校验"),
}


def _fetch_for_export(table, period):
    """读取待导出数据（避开 pandas 对 DBAPI 连接的兼容性问题，直接用 PyMySQL 取数）。

    注意：只有带 stat_period 字段的分析结果表才按周期过滤；
    模型结果表（ads_ml_*）、图计算结果表（ads_network_*）与一致性校验表没有周期维度，
    直接全量导出。
    """
    has_period = db.query_one(
        "SELECT COUNT(1) AS c FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s AND column_name='stat_period'",
        (C.MYSQL["database"], table))
    if period != "全部" and has_period and has_period["c"] > 0:
        rows = db.query(f"SELECT * FROM {table} WHERE stat_period=%s", (period,))
    else:
        rows = db.query(f"SELECT * FROM {table}")
    df = pd.DataFrame(rows)
    return df.drop(columns=[c for c in ("id",) if c in df.columns])


@app.route("/export/<name>")
@roles_required("admin")
def export(name):
    if name not in EXPORT_MAP:
        flash("未知的报表类型", "danger")
        return redirect(url_for("report"))
    table, title = EXPORT_MAP[name]
    period = _p()
    df = _fetch_for_export(table, period)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=title[:28])
    buf.seek(0)
    fn = f"{title}_{period}_{datetime.now():%Y%m%d%H%M}.xlsx"
    return send_file(buf, as_attachment=True, download_name=fn,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/export/detail/<name>")
@roles_required("admin")
def export_csv(name):
    if name not in EXPORT_MAP:
        flash("未知的报表类型", "danger")
        return redirect(url_for("report"))
    table, title = EXPORT_MAP[name]
    period = _p()
    df = _fetch_for_export(table, period)
    csv = df.to_csv(index=False).encode("utf-8-sig")
    fn = f"{title}_{period}_{datetime.now():%Y%m%d%H%M}.csv"
    return Response(csv, mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fn}"})


# ===========================================================================
# 错误页
# ===========================================================================
@app.errorhandler(404)
def e404(e):
    return render_template("error.html", code=404, msg="页面不存在"), 404


@app.errorhandler(500)
def e500(e):
    return render_template("error.html", code=500, msg="服务器内部错误"), 500


if __name__ == "__main__":
    print("=" * 70)
    print(" 医疗健康数据平台与疾病统计分析 —— 可视化服务")
    print(f" 访问地址： http://{C.WEB_HOST}:{C.WEB_PORT}")
    print(" 账号： admin/admin123   doctor/doctor123   viewer/viewer123")
    print("=" * 70)
    app.run(host=C.WEB_HOST, port=C.WEB_PORT, debug=False)
