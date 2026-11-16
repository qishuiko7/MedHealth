# -*- coding: utf-8 -*-
"""
实时数据爬虫 —— 爬取中国疾控中心「全国法定传染病疫情情况」公开通报
====================================================================
对应《项目操作流程》第 15 步：
    「同时使用爬虫技术实时爬取数据，将数据交给 spark streaming 进行实时处理」

数据源（官方公开，无隐私风险）：
    中国疾病预防控制中心 · 健康数据 · 全国法定传染病疫情情况
    https://www.chinacdc.cn/jksj/jksj01/

爬取内容：
    每月公报正文中的「法定传染病报告发病、死亡统计表」，
    含**真实**的病名 / 发病数 / 死亡数 / 传染病类别（甲类/乙类/丙类）。

输出：
    与 producer.py 完全同构的 JSON 事件，写入同一批 Kafka 主题：
      med_registration / med_visit / med_prescription
    → 下游 spark_streaming_job.py / local_stream.py 一行不用改。

运行：
    python crawler.py                     # 抓取最新一期，循环投放（默认）
    python crawler.py --pages 12          # 抓取最近 12 期公报
    python crawler.py --once              # 只投放一轮后退出
    python crawler.py --rate 20           # 每秒投放事件数
    python crawler.py --local             # 写本地 jsonl（无 Kafka 时降级）
    python crawler.py --dump out.json     # 仅抓取并落盘，不投放（调试用）

合规说明：
    仅抓取 CDC 官网公开发布的疫情通报，不含任何个人隐私信息；
    遵守 robots 约定，请求间隔默认 2 秒，仅用于课程设计教学演示。
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from datetime import datetime
from urllib.parse import urljoin

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data_generator"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config as C

# ---------------------------------------------------------------------------
# 爬虫配置
# ---------------------------------------------------------------------------
LIST_URL = "https://www.chinacdc.cn/jksj/jksj01/"
BASE_URL = "https://www.chinacdc.cn/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
REQUEST_INTERVAL = 2.0        # 两次请求间隔（秒），遵守爬虫礼仪
TIMEOUT = 20

LOCAL_STREAM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stream_events.jsonl")
CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crawl_cache.json")

# 传染病类别（公报正文中出现的分区）
CLASS_CAT = {"甲类": "甲类传染病", "乙类": "乙类传染病", "丙类": "丙类传染病"}

# 法定传染病分类表（依据《中华人民共和国传染病防治法》2020 修订版）
# 用途：公报表格未逐行标注类别，用本表精确判定，避免正文分区启发式误判
LEGAL_CLASS = {}
for _n in ("鼠疫", "霍乱"):
    LEGAL_CLASS[_n] = "甲类传染病"
for _n in ("新型冠状病毒感染", "传染性非典型肺炎", "艾滋病", "病毒性肝炎", "甲型肝炎",
           "乙型肝炎", "丙型肝炎", "丁型肝炎", "戊型肝炎", "未分型肝炎", "脊髓灰质炎",
           "人感染新亚型流感", "麻疹", "流行性出血热", "狂犬病", "流行性乙型脑炎",
           "登革热", "猴痘", "基孔肯雅热", "发热伴血小板减少综合征", "炭疽",
           "细菌性和阿米巴性痢疾", "痢疾", "肺结核", "伤寒和副伤寒", "伤寒", "副伤寒",
           "流行性脑脊髓膜炎", "百日咳", "白喉", "新生儿破伤风", "猩红热", "布鲁氏菌病",
           "淋病", "梅毒", "钩端螺旋体病", "血吸虫病", "疟疾"):
    LEGAL_CLASS[_n] = "乙类传染病"
for _n in ("流行性感冒", "流行性腮腺炎", "风疹", "急性出血性结膜炎", "麻风病",
           "流行性和地方性斑疹伤寒", "黑热病", "包虫病", "丝虫病", "手足口病",
           "其他感染性腹泻病"):
    LEGAL_CLASS[_n] = "丙类传染病"

# 疾病类别映射（把疫情公报里的病种归入项目既有疾病类别，便于与离线口径联动）
CATEGORY_MAP = [
    (("新型冠状病毒感染", "流行性感冒", "麻疹", "风疹", "腮腺炎", "水痘", "手足口病",
      "急性出血性结膜炎", "其他感染性腹泻病", "流行性感冒"), "呼吸系统疾病"),
    (("病毒性肝炎", "甲型肝炎", "乙型肝炎", "丙型肝炎", "丁型肝炎", "戊型肝炎",
      "未分型肝炎", "肝吸虫病", "痢疾", "伤寒", "副伤寒", "霍乱"), "消化系统疾病"),
    (("肺结核", "结核性胸膜炎", "百日咳", "白喉", "猩红热", "流行性脑脊髓膜炎",
      "人感染新亚型流感", "传染性非典型肺炎", "麻风病"), "呼吸系统疾病"),
    (("艾滋病", "梅毒", "淋病", "生殖道沙眼衣原体感染", "猴痘"), "感染性疾病"),
    (("狂犬病", "流行性乙型脑炎", "登革热", "基孔肯雅热", "发热伴血小板减少综合征",
      "布鲁氏菌病", "炭疽", "流行性出血热", "钩端螺旋体病", "血吸虫病"), "感染性疾病"),
    (("鼠疫",), "感染性疾病"),
]
DEFAULT_CATEGORY = "感染性疾病"


# ---------------------------------------------------------------------------
# 爬取层
# ---------------------------------------------------------------------------
def fetch(url, retries=3):
    """带重试的 GET，返回 HTML 文本。"""
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            r.raise_for_status()
            r.encoding = r.apparent_encoding or "utf-8"
            return r.text
        except Exception as e:
            last = e
            time.sleep(REQUEST_INTERVAL * (i + 1))
    print(f"  [警告] 抓取失败 {url}：{last}")
    return None


def parse_list(html, page_url):
    """从列表页解析出 [(期次标题, 详情页绝对URL), ...]，按期次倒序。"""
    items, seen = [], set()
    for m in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.S):
        href, title = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        title = re.sub(r"\s+", "", title)
        # 标题形如：2026年8月全国传染病疫情概况2026-09-10
        if not re.search(r"\d{4}年.*(传染病|疫情)概况", title):
            continue
        if href.startswith(("http", "//")):
            continue
        url = urljoin(page_url, href)
        if url in seen:
            continue
        seen.add(url)
        ym = re.search(r"(\d{4})年(\d{1,2})月", title)
        items.append({
            "title": title,
            "url": url,
            "year": int(ym.group(1)) if ym else 0,
            "month": int(ym.group(2)) if ym else 0,
        })
    return items


def parse_article(html, title, url):
    """
    解析单篇公报，返回结构化结果：
      {period, total, deaths, by_class:{甲类:..,乙类:..,丙类:..},
       rows:[{name, cases, deaths, class_name}], top_*: [...]}
    """
    body = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    body = re.sub(r"<style.*?</style>", " ", body, flags=re.S)
    text = re.sub(r"<[^>]+>", " ", body)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ")
    text = re.sub(r"\s+", " ", text)

    ym = re.search(r"(\d{4})年(\d{1,2})月", title)
    period = f"{ym.group(1)}-{int(ym.group(2)):02d}" if ym else ""

    # 总量
    total, total_deaths = 0, 0
    m = re.search(r"全国共报告法定传染病\s*([\d,]+)\s*例[，,]\s*死亡\s*([\d,]+)\s*人", text)
    if m:
        total = int(m.group(1).replace(",", ""))
        total_deaths = int(m.group(2).replace(",", ""))

    # 甲乙丙分类
    by_class = {}
    for cls, label in CLASS_CAT.items():
        mc = re.search(rf"{cls}传染病共报告发病\s*([\d,]+)\s*例[，,]\s*死亡\s*([\d,]+)\s*人", text)
        if mc:
            by_class[label] = {"cases": int(mc.group(1).replace(",", "")),
                               "deaths": int(mc.group(2).replace(",", ""))}

    # 病种明细表：从「统计表」之后开始，形如「[序号] 病名 [脚注号] 发病数 死亡数」
    # 注意：CDC 公报 HTML 中的脚注上标（¹²³...）被压平后表现为病名后的一个 1~2 位小整数，
    #       例如「新型冠状病毒感染 2 770671 6」实际含义是 病名=新型冠状病毒感染, 发病=770671, 死亡=6，
    #       其中「2」是脚注序号而非发病数。因此按「病名 + 数字序列」整体匹配后再判定：
    #         · 2 个数字 → 发病数, 死亡数
    #         · 3 个数字 → 第一个是脚注序号，取后两个
    rows = []
    seg = text
    k = seg.find("统计表")
    if k > 0:
        seg = seg[k:]
    # 先定位「病名 发病数 死亡数」表头，其后的内容才是明细区
    hdr = seg.find("病名")
    if hdr >= 0:
        seg = seg[hdr:]
    # 病名（含括号/连字符/罗马数字等）+ 若干数字
    pat = re.compile(
        r"([\u4e00-\u9fa5][\u4e00-\u9fa5A-Za-z（）()·\-Ⅰ-Ⅻ]{1,22})"
        r"((?:\s+\d{1,9}){2,3})(?=\s|$)"
    )
    started = False
    for m in pat.finditer(seg):
        name = m.group(1).strip()
        nums = [int(x) for x in m.group(2).split()]
        if "总计" in name or "合计" in name:
            started = True                          # 表头行，其后开始记录
            continue
        if not started:
            continue
        if name in ("甲类", "乙类", "丙类"):
            continue
        if len(nums) == 3:                          # 首数为脚注序号，丢弃
            nums = nums[1:]
        cs, ds = nums[0], nums[1]
        rows.append({"name": name, "cases": cs, "deaths": ds})

    # 归纳病种所属类别：优先查法定分类表，再退回正文分区启发式
    for r in rows:
        r["class_name"] = LEGAL_CLASS.get(r["name"]) or guess_class(r["name"], text)

    # 乙类/丙类 Top5 病种（正文显式给出，优先采用）
    top_b = re.findall(r"乙类传染病[^。]*?居前\s*5\s*位的病种依次为(.{5,120}?)和(.{2,20}?)[，,]占", text)
    top_list = []
    mt = re.search(r"报告发病数居前\s*5\s*位的病种依次为(.+?)，?占", text)
    if mt:
        parts = re.split(r"[、和]", mt.group(1))
        top_list = [p.strip() for p in parts if p.strip()]

    return {
        "period": period,
        "title": title,
        "url": url,
        "total": total,
        "total_deaths": total_deaths,
        "by_class": by_class,
        "rows": rows,
        "top": top_list,
        "crawled_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def guess_class(name, text):
    """按名称关键词推断病种所属传染病类别，兜底按正文分区判断。"""
    for keys, cat in CATEGORY_MAP:
        for k in keys:
            if k in name:
                return cat
    # 兜底：看该病名在正文哪个分区的片段里出现过
    for cls, label in CLASS_CAT.items():
        i = text.find(f"{cls}传染病共报告发病")
        j = text.find("同期，重点监测", i)
        if i > 0 and j > i and name in text[i:j]:
            return label
    return DEFAULT_CATEGORY


def crawl(pages=12, use_cache=True):
    """爬取最近 N 期公报，返回 list[dict]。带本地缓存，避免重复请求。"""
    if use_cache and os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
            if cache.get("records"):
                print(f"[爬虫] 使用本地缓存 {CACHE_FILE}（{len(cache['records'])} 期）")
                return cache["records"]
        except Exception:
            pass

    print(f"[爬虫] 开始抓取列表页 {LIST_URL}")
    html = fetch(LIST_URL)
    if not html:
        print("[爬虫] 列表页抓取失败，退出")
        return []
    items = parse_list(html, LIST_URL)
    print(f"[爬虫] 列表页解析到 {len(items)} 篇公报，取最近 {pages} 篇")

    # 按年月倒序
    items.sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    items = items[:pages]

    records = []
    for i, it in enumerate(items, 1):
        print(f"  [{i}/{len(items)}] {it['title'][:40]} …", flush=True)
        h = fetch(it["url"])
        if not h:
            continue
        rec = parse_article(h, it["title"], it["url"])
        if rec["rows"] or rec["total"]:
            records.append(rec)
            print(f"        期次={rec['period']} 总量={rec['total']:,} 明细={len(rec['rows'])} 病种")
        time.sleep(REQUEST_INTERVAL)     # 爬虫间隔

    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"records": records,
                       "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                      f, ensure_ascii=False, indent=1)
        print(f"[爬虫] 结果已缓存 -> {CACHE_FILE}")
    except Exception as e:
        print(f"[爬虫] 缓存写入失败：{e}")
    return records


# ---------------------------------------------------------------------------
# 事件构造（与 producer.py 同构，下游零改动）
# ---------------------------------------------------------------------------
DEPT_BY_CAT = {
    "呼吸系统疾病": ["呼吸内科", "感染科", "急诊科", "儿科"],
    "消化系统疾病": ["消化内科", "感染科", "急诊科"],
    "感染性疾病": ["感染科", "急诊科", "内科"],
}


def build_events(records, max_rows=400):
    """把爬到的公报明细展开成实时事件列表。"""
    events = []
    for rec in records:
        for r in rec.get("rows", []):
            cat = r["class_name"]
            depts = DEPT_BY_CAT.get(cat, ["感染科", "内科"])
            dept = random.choice(depts)
            events.append({
                "event_type": "visit",
                "event_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "period": rec["period"],
                "patient_id": 0,
                "gender": "-",
                "age": 0,
                "dept_id": depts.index(dept) + 1,
                "dept_name": dept,
                "diagnosis_code": "",
                "diagnosis_name": r["name"],
                "disease_category": cat,
                "is_infectious": 1,
                "case_cnt": r["cases"],
                "death_cnt": r["deaths"],
                "presc_items": [],
                "presc_amount": 0.0,
                "source": "CDC-crawler",
                "source_url": rec["url"],
            })
    random.shuffle(events)
    return events[:max_rows] if max_rows else events


# ---------------------------------------------------------------------------
# 投放
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="实时数据爬虫（CDC 官方公报）")
    ap.add_argument("--pages", type=int, default=12, help="抓取最近 N 期公报")
    ap.add_argument("--rate", type=int, default=15, help="每秒投放事件数")
    ap.add_argument("--once", action="store_true", help="只投放一轮后退出")
    ap.add_argument("--local", action="store_true", help="写本地 jsonl 而非 Kafka")
    ap.add_argument("--no-cache", action="store_true", help="忽略本地缓存，强制重新爬取")
    ap.add_argument("--dump", type=str, default="", help="仅抓取并落盘到指定 json 文件")
    args = ap.parse_args()

    records = crawl(args.pages, use_cache=not args.no_cache)
    if not records:
        print("[爬虫] 未获取到数据，退出")
        return

    if args.dump:
        with open(args.dump, "w", encoding="utf-8") as f:
            json.dump(records, f, ensure_ascii=False, indent=1)
        print(f"[爬虫] 已落盘 -> {args.dump}（{len(records)} 期）")
        return

    events = build_events(records)
    print(f"[爬虫] 由 {len(records)} 期公报生成 {len(events)} 条事件")

    try:
        from kafka import KafkaProducer
        has_kafka = True
    except Exception:
        has_kafka = False

    if args.local or not has_kafka:
        mode = "本地文件" if args.local else "本地文件（未装 kafka-python，自动降级）"
        print(f"[爬虫] 运行模式：{mode} -> {LOCAL_STREAM_FILE}")
        n = 0
        tick = 0
        while True:
            for ev in events[:args.rate]:
                with open(LOCAL_STREAM_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(ev, ensure_ascii=False) + "\n")
                n += 1
            tick += 1
            if tick % 5 == 0:
                print(f"[爬虫] 已投放 {n:,} 条事件 ({datetime.now():%H:%M:%S})", flush=True)
            if args.once:
                break
            time.sleep(1)
        print(f"[爬虫] 退出，共投放 {n:,} 条")
        return

    print(f"[爬虫] 运行模式：Kafka -> {C.KAFKA_BOOTSTRAP}")
    producer = KafkaProducer(
        bootstrap_servers=C.KAFKA_BOOTSTRAP.split(","),
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        key_serializer=lambda k: k.encode("utf-8"),
        acks=1, linger_ms=200)
    n, tick = 0, 0
    while True:
        batch = events[:args.rate] if len(events) >= args.rate else events
        for ev in batch:
            key = str(ev["diagnosis_name"])
            producer.send(C.KAFKA_TOPICS["visit"], key=key, value=ev)
            producer.send(C.KAFKA_TOPICS["registration"], key=key,
                          value={"event_type": "registration", "event_time": ev["event_time"],
                                 "period": ev["period"], "dept_name": ev["dept_name"],
                                 "diagnosis_name": ev["diagnosis_name"], "source": "CDC-crawler"})
            n += 1
        producer.flush()
        tick += 1
        if tick % 5 == 0:
            print(f"[爬虫] 已投递 {n:,} 条事件到 Kafka ({datetime.now():%H:%M:%S})", flush=True)
        if args.once:
            break
        time.sleep(1)
    producer.flush()
    producer.close()
    print(f"[爬虫] 退出，共投递 {n:,} 条")


if __name__ == "__main__":
    main()
