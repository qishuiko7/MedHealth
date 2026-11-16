# -*- coding: utf-8 -*-
"""
MySQL 访问层
统一封装连接与查询，返回 dict 列表，便于 Flask 直接 jsonify。
"""
import os
import sys

import pymysql
from pymysql.cursors import DictCursor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))
import config as C


def get_conn():
    return pymysql.connect(
        host=C.MYSQL["host"], port=C.MYSQL["port"], user=C.MYSQL["user"],
        password=C.MYSQL["password"], database=C.MYSQL["database"],
        charset=C.MYSQL["charset"], cursorclass=DictCursor, autocommit=True)


def query(sql, args=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, args or ())
            return cur.fetchall()
    finally:
        conn.close()


def query_one(sql, args=None):
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql, args=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            n = cur.execute(sql, args or ())
        conn.commit()
        return n
    finally:
        conn.close()


def executemany(sql, seq):
    if not seq:
        return 0
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            n = cur.executemany(sql, seq)
        conn.commit()
        return n
    finally:
        conn.close()


def get_periods():
    """返回可选的统计周期列表（月份升序 + '全部' 置首）。"""
    rows = query("SELECT DISTINCT stat_period FROM ads_overview_kpi ORDER BY stat_period")
    ps = [r["stat_period"] for r in rows]
    months = sorted([p for p in ps if p != "全部"])
    return ["全部"] + months


def get_depts():
    return query("SELECT dept_id, dept_name, dept_type_name FROM dim_department ORDER BY dept_id")
