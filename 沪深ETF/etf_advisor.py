#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF 买入诊断器（本地网页版，纯 Python 标准库，完全免费）

用法一（网页）：
    python etf_advisor.py            # 启动后自动打开浏览器 http://127.0.0.1:8734
用法二（命令行，快速看一只）：
    python etf_advisor.py 512880             # 只给结论
    python etf_advisor.py 512880 200000      # 给结论 + 20万资金的具体金额/份数建议

数据来源（公开免费接口，无需注册、无需 key）：
    行情/日K：腾讯  qt.gtimg.cn / web.ifzq.gtimg.cn
    指数估值：蛋卷基金（雪球旗下）danjuanfunds.com/djapi/index_eva
说明：本工具只做数据分析与纪律化仓位测算，不构成投资建议。
"""

import json
import math
import re
import sys
import time
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = "127.0.0.1"
PORT = 8734
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

# ---------------------------------------------------------------- HTTP + 缓存

_cache = {}
_lock = threading.Lock()
_GATE = threading.Semaphore(4)  # 同时在飞的 HTTP 请求数上限
TTL = 600  # 10 分钟


def _get(url, referer, encoding="utf-8", ttl=TTL, key=None):
    cache_key = key or url
    now = time.time()
    with _lock:
        hit = _cache.get(cache_key)
        if hit and now - hit[0] < ttl:
            return hit[1]
    req = Request(url, headers={"User-Agent": UA, "Referer": referer, "Accept": "*/*"})
    with _GATE:
        time.sleep(0.08)
        with urlopen(req, timeout=25) as resp:
            body = resp.read().decode(encoding, "ignore")
    with _lock:
        _cache[cache_key] = (now, body)
    return body


# ------------------------------------------------------- 指数估值（蛋卷，缓存）

# 常见 ETF 代码 -> 蛋卷估值表里的指数代码（人工核对过，优先于名称匹配）
ETF_TO_INDEX = {
    "510300": "SH000300", "510310": "SH000300", "159919": "SH000300", "510330": "SH000300",
    "510050": "SH000016", "510180": "SH000010", "510010": "SH000903",
    "510500": "SH000905", "512500": "SH000905", "159922": "SH000905",
    "512100": "SH000852", "159845": "SH000852",
    "159915": "SZ399006", "159957": "SZ399006",
    "588000": "SH000688", "588080": "SH000688", "588090": "SH000688",
    "512880": "SZ399975", "512000": "SZ399975", "512900": "SZ399975",
    "512010": "SH000991", "512120": "SH000991", "159938": "SH000991", "512170": "SZ399989",
    "512690": "SZ399997", "159928": "SH000932", "510150": "SH000932", "159996": "SZ399996",
    "512990": "SZ399989", "159883": "SZ399989",
    "512480": "", "512670": "SZ399967",
    "512800": "SZ399986", "515220": "SZ399998", "510230": "",
    "512580": "SH000827", "159824": "SZ399417", "515030": "SZ399417", "159790": "",
    "515050": "CSI931079", "159811": "CSI931079", "512760": "CSI930652", "159939": "SZ399610",
    "512400": "", "512980": "SZ399971",
    "512890": "CSIH30269", "515080": "SH000922", "510900": "HKHSCEI",
    "510880": "SH000922", "515180": "SH000922", "515450": "CSIH30269", "563020": "CSIH30269",
    "512040": "SH000919", "159903": "SZ399001", "159902": "SZ399701",
    "513100": "NDX", "159941": "NDX", "513110": "NDX",
    "513500": "SP500", "159612": "SP500",
    "513050": "CSIH30533", "159607": "CSIH30533", "159792": "CSIH11136",
    "513130": "HKHSTECH", "513180": "HKHSTECH", "159740": "HKHSTECH",
    "513190": "", "159954": "HKHSI", "513630": "", "159920": "HKHSI",
    "513290": "", "159605": "CSIH30533", "513920": "HSFML25",
    "513030": "GDAXI", "513870": "NDX", "159529": "",
    "515170": "SZ399396", "159736": "SZ399396",
}

# 名称关键词 -> 指数代码（用于上表没覆盖的 ETF）
KEYWORD_TO_INDEX = [
    ("沪深300", "SH000300"), ("上证50", "SH000016"), ("中证500", "SH000905"),
    ("中证1000", "SH000852"), ("科创50", "SH000688"), ("创业板", "SZ399006"),
    ("证券公司", "SZ399975"), ("证券", "SZ399975"), ("中证银行", "SZ399986"), ("银行", "SZ399986"),
    ("中证白酒", "SZ399997"), ("酒", "SZ399997"), ("医药", "SH000991"), ("医疗", "SZ399989"),
    ("军工", "SZ399967"), ("传媒", "SZ399971"), ("新能源车", "SZ399417"), ("环保", "SH000827"),
    ("煤炭", "SZ399998"), ("地产", "SZ399393"), ("红利低波", "CSIH30269"), ("红利", "SH000922"),
    ("中概互联", "CSIH30533"), ("海外互联网", "CSIH11136"), ("恒生科技", "HKHSTECH"),
    ("纳斯达克", "NDX"), ("纳指", "NDX"), ("标普500", "SP500"), ("恒生指数", "HKHSI"),
    ("国企", "HKHSCEI"), ("德国", "GDAXI"), ("印度", "935600"), ("5G", "CSI931079"),
    ("消费", "SH000932"), ("基本面50", "SH000925"), ("央视50", "SZ399550"),
    ("食品饮料", "SZ399396"), ("食品", "SZ399396"), ("饮料", "SZ399396"),
    ("电子", "CSI930652"), ("半导体", "CSI930652"), ("芯片", "CSI930652"),
    ("红利成长", "CSI931157"), ("上证红利", "SH000015"), ("深证红利", "SZ399324"),
    ("消费红利", "CSIH30094"), ("医药100", "SH000978"),
]

_INDEX_LIST_URL = "https://danjuanfunds.com/djapi/index_eva/dj"
_INDEX_LIST_REF = "https://danjuanfunds.com/djmodule/value-center"


def index_meta(index_code):
    """返回蛋卷对某指数的估值数据；拿不到返回 None。"""
    try:
        body = _get(_INDEX_LIST_URL, _INDEX_LIST_REF, ttl=3600, key="dj_list")
        items = json.loads(body)["data"]["items"]
        for it in items:
            if it["index_code"] == index_code:
                return it
        detail = json.loads(_get(
            "https://danjuanfunds.com/djapi/index_eva/detail/" + index_code,
            _INDEX_LIST_REF, ttl=3600, key="dj_" + index_code))
        return detail.get("data")
    except Exception:
        return None


# ------------------------------------------------------------------ 行情与K线

def market_prefix(code):
    return "sh" if code[0] in "569" else "sz"


def realtime_quote(code):
    """实时行情：腾讯为主（带重试），东方财富兜底。"""
    sym = market_prefix(code) + code
    last_err = None
    for _ in range(2):
        try:
            body = _get("https://qt.gtimg.cn/q=" + sym, "https://gu.qq.com/",
                        encoding="gbk", ttl=60, key="rt_" + sym)
            m = re.search(r'"(.*?)"', body, re.S)
            if not m or not m.group(1):
                raise RuntimeError("行情返回为空")
            f = m.group(1).split("~")
            if len(f) < 10 or not f[1] or f[1].startswith("v_pv") or f[2] != code:
                raise RuntimeError("代码 %s 在场内找不到，请确认是沪深 ETF（6 位数字）" % code)
            price = float(f[3])
            if price <= 0:
                raise RuntimeError("该代码无有效报价（可能已退市或停牌）")
            prev = float(f[4])

            def _ff(i):
                try:
                    v = float(f[i]) if len(f) > i and f[i] else None
                except ValueError:
                    v = None
                return v if v and v > 0 else None
            return {
                "symbol": sym,
                "name": f[1],
                "price": price,
                "prev_close": prev,
                "open": float(f[5]),
                "change": float(f[31]) if len(f) > 31 and f[31] else round(price - prev, 4),
                "change_pct": float(f[32]) if len(f) > 32 and f[32] else round((price / prev - 1) * 100, 2),
                "high": float(f[33]) if len(f) > 33 and f[33] else price,
                "low": float(f[34]) if len(f) > 34 and f[34] else price,
                "amount_wan": float(f[37]) if len(f) > 37 and f[37] else 0,
                "time": f[30] if len(f) > 30 else "",
                "iopv": _ff(78),   # 实时参考净值（境内 ETF 盘中有效）
                "nav": _ff(81),    # 最新官方净值（QDII 通常滞后 1~2 个交易日）
            }
        except Exception as e:
            last_err = e
            if "找不到" in str(e) or "无有效报价" in str(e):
                raise RuntimeError(str(e))
            time.sleep(0.5)
    try:
        secid = ("1." if code[0] in "569" else "0.") + code
        data = json.loads(_get(
            "https://push2.eastmoney.com/api/qt/stock/get?secid=%s&fields=f43,f57,f58,f60,f170,f48" % secid,
            "https://quote.eastmoney.com/", ttl=60, key="emrt_" + code))["data"]
        price = data["f43"] / 1000.0
        return {"symbol": sym, "name": data["f58"], "price": price,
                "prev_close": data["f60"] / 1000.0, "open": price, "change": 0.0,
                "change_pct": (data.get("f170") or 0) / 100.0, "high": price, "low": price,
                "amount_wan": (data.get("f48") or 0) / 10000.0,
                "time": time.strftime("%Y%m%d%H%M%S"),
                "iopv": None, "nav": None}
    except Exception as e:
        raise RuntimeError("行情拉取失败：%s / %s" % (last_err, e))


def nav_date(code):
    """最新官方净值日期（天天基金 F10）；失败返回 None。缓存 6 小时。"""
    try:
        j = json.loads(_get(
            "https://api.fund.eastmoney.com/f10/lsjz?fundCode=%s&pageIndex=1&pageSize=1"
            % code, "https://fundf10.eastmoney.com/", ttl=21600, key="navd_" + code))
        rows = (j.get("Data") or {}).get("LSJZList") or []
        return rows[0].get("FSRQ") if rows else None
    except Exception:
        return None


def daily_kline(code, bars=1000):
    """日K（前复权优先）。腾讯为主，东方财富备用；返回 [(date, open, close, high, low, volume), ...]"""
    sym = market_prefix(code) + code
    end = time.strftime("%Y-%m-%d")
    beg = time.strftime("%Y-%m-%d", time.localtime(time.time() - 86400 * 365 * 9))
    out = []
    for count in (bars, 640):
        try:
            out = _clean_rows(_tx_rows(sym, beg, end, count))
        except Exception:
            out = []
        if len(out) >= 60:
            return out
        time.sleep(0.5)

    # 兜底：东方财富
    secid = ("1." if code[0] in "569" else "0.") + code
    try:
        url = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=%s&klt=101&fqt=1"
               "&beg=20150101&end=20500101&lmt=%d&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56"
               % (secid, bars))
        data = json.loads(_get(url, "https://quote.eastmoney.com/", ttl=600, key="emk_" + code))
        rows = [r.split(",") for r in (data.get("data") or {}).get("klines") or []]
        out = _clean_rows(rows)
    except Exception:
        pass
    if len(out) < 60:
        time.sleep(0.8)
        out = _clean_rows(_tx_rows(sym, beg, end, 500))
    if len(out) < 60:
        raise RuntimeError("K线数据不足（%d 根），可能代码不对或接口在限流，稍等重试" % len(out))
    return out


KLINE_HOSTS = [
    ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", "kline"),
    ("https://ifzq.gtimg.cn/appstock/app/fqkline/get", "kline2"),
    ("https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get", "kline3"),
]


def _tx_rows(sym, beg, end, count):
    """腾讯系日K，多主机轮询（单个主机限流时自动换）。"""
    last = []
    for host, tag in KLINE_HOSTS:
        try:
            data = json.loads(_get("%s?param=%s,day,%s,%s,%d,qfq" % (host, sym, beg, end, count),
                                   "https://gu.qq.com/", ttl=600, key=tag + sym + str(count)))
            node = data.get("data", {}).get(sym) or {}
            rows = node.get("qfqday") or node.get("day") or []
            if len(rows) >= 60:
                return rows
            last = rows or last
        except Exception:
            continue
    return last


def _clean_rows(rows):
    out = []
    for r in rows:
        try:
            out.append((str(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]),
                        float(r[5]) if len(r) > 5 and r[5] else 0.0))
        except (ValueError, IndexError, TypeError):
            continue
    return out


# ------------------------------------------------------------------ 指标计算

def pct_rank(values, x):
    """x 在 values 里的分位（0~1），越大越贵/越高。"""
    if not values:
        return 0.5
    return sum(1 for v in values if v <= x) / float(len(values))


def moving_avg(closes, n):
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / float(n)


def match_index(code, name):
    """ETF 代码/名称 -> 蛋卷估值表里的指数代码。返回 (指数代码, 命中的关键词)。"""
    idx = ETF_TO_INDEX.get(code)
    if idx:
        return idx, None
    for kw, ic in KEYWORD_TO_INDEX:
        if kw in name:
            return ic, kw
    return None, None


def build_valuation(meta, fallback_name=None):
    if not meta:
        if fallback_name:
            return {"index_name": fallback_name, "value_pct": None, "grade": "无估值数据"}
        return None
    pe_p = float(meta.get("pe_percentile") or 0)
    pb_p = float(meta.get("pb_percentile") or 0)
    use_pb = bool(meta.get("pb_flag")) or float(meta.get("pe") or 0) <= 0
    v_pct = pb_p if use_pb else round(0.6 * pe_p + 0.4 * pb_p, 4)
    return {
        "index_code": meta["index_code"],
        "index_name": meta["name"],
        "ttype": str(meta.get("ttype") or ""),
        "pe": round(float(meta["pe"]), 2) if float(meta.get("pe") or 0) > 0 else None,
        "pb": round(float(meta["pb"]), 3) if float(meta.get("pb") or 0) > 0 else None,
        "pe_pct": round(pe_p * 100, 1),
        "pb_pct": round(pb_p * 100, 1),
        "used": "PB" if use_pb else "PE+PB",
        "value_pct": round(v_pct * 100, 1),
        "grade": {"low": "低估", "mid": "适中", "high": "高估"}.get(meta.get("eva_type"), "-"),
        "roe": round(float(meta["roe"]) * 100, 1) if float(meta.get("roe") or 0) > 0 else None,
        "dividend": round(float(meta.get("yeild") or 0) * 100, 2),
    }


def analyze(code, capital=0.0, quote=None, meta=None):
    code = code.strip()
    if not re.fullmatch(r"\d{6}", code):
        raise ValueError("ETF 代码请填 6 位数字，例如 510300")

    q = quote or realtime_quote(code)
    k = daily_kline(code)
    closes = [r[2] for r in k]
    n = len(closes)
    last = q["price"] or closes[-1]

    # --- 价格位置 / 波动 / 趋势
    mt = kline_metrics(closes, last, rows=k)
    price_pct_3y, pct_window = mt["price_pct_3y"], mt["pct_window"]
    hi_52w, lo_52w = mt["hi_52w"], mt["lo_52w"]
    drawdown_from_hi, up_from_lo = mt["drawdown_from_hi"], mt["up_from_lo"]
    vol_d, vol_y = mt["vol_d"], mt["vol_y"]
    ma20, ma60, ma120, ma250 = mt["ma20"], mt["ma60"], mt["ma120"], mt["ma250"]
    mom_60, mom_120 = mt["mom_60"], mt["mom_120"]

    # --- 估值
    idx_code, idx_kw = match_index(code, q["name"])
    if meta is None:
        meta = index_meta(idx_code) if idx_code else None
    valuation = build_valuation(meta, idx_kw)

    non_stock = any(w in q["name"] for w in EXCLUDE_WORDS)

    # --- 网格参数（用波动率推间距）
    step_pct = max(1.0, round(min(6.0, vol_d * 100 * 1.6), 1))
    grids = 5
    grid_rows = []
    price_now = last
    total_grid = 2 * grids
    per_grid_money = (capital * target / total_grid) if capital > 0 else 0.0
    for i in range(-grids, grids + 1):
        p = round(price_now * (1 + step_pct / 100.0 * i), 3)
        lots = int(per_grid_money // (p * 100)) if (per_grid_money and i != 0) else 0
        grid_rows.append({
            "level": i, "price": p,
            "side": "买入" if i < 0 else ("现价基准" if i == 0 else "卖出"),
            "money": round(per_grid_money, 0) if i != 0 else 0,
            "shares": lots * 100,
        })
    lower = round(price_now * (1 - step_pct / 100.0 * grids), 3)
    upper = round(price_now * (1 + step_pct / 100.0 * grids), 3)

    first_batch = round(capital * target * 0.5, 0) if capital > 0 else 0.0

    # --- 溢价率：价格 vs 参考净值（实时 IOPV 优先，否则用官方净值）
    premium = None
    iopv, nav = q.get("iopv"), q.get("nav")
    offshore = any(w in q["name"] for w in OFFSHORE_WORDS) or code in QDII_CODES
    # 跨境品种没有盘中实时 IOPV（海外市场未开盘），字段里只是官方净值的复制
    prem_ref = (None if offshore else iopv) or nav
    if prem_ref and last > 0:
        prem_pct = round((last / prem_ref - 1) * 100, 2)
        realtime = bool(iopv) and not offshore
        nd = nav_date(code) if not realtime else None  # 只有用官方净值时才需要日期
        quote_day = (q["time"] or "")[:8]
        nav_stale = bool(nd and quote_day and
                         nd.replace("-", "") < quote_day)
        premium = {"ref": round(prem_ref, 4), "pct": prem_pct,
                   "realtime": realtime, "nav_date": nd, "stale": nav_stale}

    # --- 打分与结论（与推荐榜同一套口径）
    score, confidence, trend_note = combine_score(
        valuation, price_pct_3y, ma250, last, mom_60,
        ma20=ma20, ma60=ma60, ma120=ma120, mom_120=mom_120,
        vol_y=vol_y, amount_wan=q.get("amount_wan"),
        premium_pct=(premium["pct"] if premium else None))
    if non_stock:
        confidence = "不适用（非股票型 ETF）"
        verdict, action, target = "不适用", "本工具只针对股票型 ETF 给结论", 0.0
        trend_note.insert(0, "这是货币/债券/商品类品种，股票式的估值分位和网格仓位口径都不适用，只看价格和波动参考")
    else:
        verdict, action, target = verdict_of(score)
    risk = []
    if "ETF" not in q["name"].upper():
        risk.append("名称里没有 ETF 字样（%s），这更像股票/LOF，本工具按 ETF 口径测算，估值匹配可能不准" % q["name"])
    if q["amount_wan"] and q["amount_wan"] < 3000:
        risk.append("当日成交额 %.0f 万元，偏小，大额买卖会有冲击成本" % q["amount_wan"])
    if price_pct_3y < 0.15 and n < 400:
        risk.append("上市时间较短，历史分位参考意义有限")
    if vol_y > 35:
        risk.append("年化波动 %.0f%%，属于高波动品种，网格要拉宽、仓位要压低" % vol_y)
    if "债" in q["name"] or "货币" in q["name"] or "黄金" in q["name"]:
        risk.append("该品种不适用股票式估值，结论主要看价格分位与趋势")
    if premium:
        pp = premium["pct"]
        stale_note = "（净值日期 %s，QDII 净值滞后，溢价为近似值）" % premium["nav_date"] \
            if premium.get("stale") else ""
        if pp >= 5:
            risk.append("溢价 %.1f%%%s：比净值贵了 %.1f%%，等于多花钱买同样的资产，"
                        "高溢价回落风险大，建议等溢价收敛再买" % (pp, stale_note, pp))
        elif pp >= 2:
            risk.append("溢价 %.1f%%%s：高于参考净值，买入前先想清楚是否值得多付这部分"
                        % (pp, stale_note))
        elif pp <= -3:
            risk.append("折价 %.1f%%%s：价格低于净值，便宜可能有原因（流动性差/预期低迷），"
                        "确认不是陷阱再捡" % (abs(pp), stale_note))
    if not risk:
        risk.append("常规风险：单边下跌时网格会越买越套，务必给该品种设总仓位上限")

    return {
        "code": code, "name": q["name"], "price": last,
        "change_pct": q["change_pct"], "quote_time": q["time"],
        "amount_wan": q["amount_wan"],
        "bars": n, "history_years": round(n / 244.0, 1),
        "valuation": valuation,
        "metrics": {
            "price_pct_3y": round(price_pct_3y * 100, 1),
            "pct_window": pct_window,
            "hi_52w": hi_52w, "lo_52w": lo_52w,
            "drawdown_from_hi": round(drawdown_from_hi, 1),
            "up_from_lo": round(up_from_lo, 1),
            "ma20": round(ma20, 3) if ma20 else None,
            "ma60": round(ma60, 3) if ma60 else None,
            "ma120": round(ma120, 3) if ma120 else None,
            "ma250": round(ma250, 3) if ma250 else None,
            "vol_y": round(vol_y, 1),
            "mom_60": round(mom_60, 1), "mom_120": round(mom_120, 1),
        },
        "premium": premium,
        "score": score, "verdict": verdict, "action": action,
        "confidence": confidence, "trend_note": trend_note,
        "plan": {
            "target_ratio": round(target * 100, 0),
            "first_batch": first_batch,
            "per_batch": round(per_grid_money, 0),
            "step_pct": step_pct, "grids": grids,
            "lower": lower, "upper": upper,
            "per_grid_money": round(per_grid_money, 0),
            "grid_rows": grid_rows,
            "capital": capital,
        },
        "risk": risk,
        "spark": [round(c, 3) for c in closes[-120:]],
        "spark_dates": [r[0] for r in k][-120:],
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

def kline_metrics(closes, last, rows=None):
    """从日K收盘序列算出位置/波动/趋势指标，诊断和推荐共用同一套算法。"""
    n = len(closes)
    closes_1y = closes[-min(250, n):]
    closes_3y = closes[-min(750, n):]
    if rows:  # 52周高低用盘中最高/最低价，比收盘价更贴近真实区间
        recent = rows[-min(250, len(rows)):]
        hi = max(r[3] for r in recent)
        lo = min(r[4] for r in recent)
    else:
        hi, lo = max(closes_1y), min(closes_1y)
    rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, n)]
    rets = rets[-250:]  # 波动率取近一年样本，反映当前波动状态而非多年均值
    mean = sum(rets) / len(rets)
    vol_d = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5
    return {
        "price_pct_3y": pct_rank(closes_3y, last),
        "pct_window": round(len(closes_3y) / 244.0, 1),
        "hi_52w": hi, "lo_52w": lo,
        "drawdown_from_hi": (last / hi - 1) * 100,
        "up_from_lo": (last / lo - 1) * 100,
        "vol_d": vol_d, "vol_y": vol_d * (252 ** 0.5) * 100,
        "ma20": moving_avg(closes, 20), "ma60": moving_avg(closes, 60),
        "ma120": moving_avg(closes, 120), "ma250": moving_avg(closes, 250),
        "mom_60": (last / closes[-61] - 1) * 100 if n > 61 else 0.0,
        "mom_120": (last / closes[-121] - 1) * 100 if n > 121 else 0.0,
    }


def combine_score(valuation, price_pct_3y, ma250, last, mom_60,
                  ma20=None, ma60=None, ma120=None, mom_120=None,
                  vol_y=None, amount_wan=None, premium_pct=None):
    """综合评分：基础分（估值 40 + 价格 25 + 质量 10 + 趋势 15）+ 调整项（±10，封顶）。
    每项加减都会留 trend_note 说明，保证可解释。"""
    trend_note = []
    has_val = valuation and valuation.get("value_pct") is not None

    # --- 趋势分（0~15）：双动量 + 均线多头/空头排列
    m120 = mom_120 or 0.0
    aligned = None
    if None not in (ma20, ma60, ma120):
        if ma20 > ma60 > ma120:
            aligned = "bull"
        elif ma20 < ma60 < ma120:
            aligned = "bear"
    t = 0.0
    if mom_60 > 15 and m120 > 10:
        t += 8.0
        trend_note.append("中短期趋势向上（60日 %+.0f%% / 120日 %+.0f%%）" % (mom_60, m120))
    elif mom_60 < -10 and m120 < -10:
        t -= 5.0
        trend_note.append("短期下跌趋势明显（60日 %+.0f%% / 120日 %+.0f%%）" % (mom_60, m120))
    if aligned == "bull":
        t += 5.0
        trend_note.append("均线多头排列（MA20>MA60>MA120），趋势健康")
    elif aligned == "bear":
        t -= 7.0
        trend_note.append("均线空头排列（MA20<MA60<MA120），下跌趋势仍在延续")

    # --- 基础分（合计 90 分）
    price_score = max(0.0, min(25.0, (1 - price_pct_3y) * 25.0))
    quality_score = 0.0
    if has_val:
        val_score = 100 - valuation["value_pct"]
        value_score = val_score * 0.4
        roe = valuation.get("roe")
        div = valuation.get("dividend") or 0.0
        if roe is not None:
            if roe > 15:
                quality_score += 5.0
            elif roe >= 8:
                quality_score += 2.5
        if div > 3:
            quality_score += 3.0
        elif div > 2:
            quality_score += 1.5
        else:
            quality_score += 1.0
        score = round(max(0.0, min(40.0, value_score)) + price_score + quality_score + t, 1)
        confidence = "高（估值 + 质量 + 趋势）"
    else:
        val_score = None
        score = round(price_score * 1.8 + t * 1.5, 1)  # 无估值时按价格 vs 趋势估算
        confidence = "中（仅价格与趋势，无估值/质量）"

    # --- 调整项（±10 分封顶）
    adj = 0.0
    if vol_y is not None:
        if vol_y > 40:
            adj -= 5.0
            trend_note.append("高波动（年化 %.0f%%），风险上调，调低评分" % vol_y)
        elif vol_y > 30:
            adj -= 2.0
            trend_note.append("波动率偏高（年化 %.0f%%），调低评分" % vol_y)
    if amount_wan is not None:
        if amount_wan < 1000:
            adj -= 5.0
            trend_note.append("成交额过低（%.0f 万），流动性风险" % amount_wan)
        elif amount_wan < 3000:
            adj -= 2.0
            trend_note.append("成交额偏小（%.0f 万），流动性一般" % amount_wan)
    if premium_pct is not None and premium_pct >= 5:
        adj -= 8.0
    adj = max(-10.0, min(10.0, adj))

    # --- 原有趋势惩罚（追高与深跌）
    if ma250 and last > ma250 and mom_60 > 25:
        adj -= 5.0
        trend_note.append("近60日已涨 %.0f%%，处于强势但追高风险大，评分已下调" % mom_60)
    elif ma250 and last < ma250 * 0.85:
        adj -= 2.0
        trend_note.append("价格低于年线 %.0f%%，趋势仍向下，建议放慢分批、别一次买满" % ((1 - last / ma250) * 100))
    adj = max(-10.0, min(10.0, adj))

    score = round(max(0.0, min(100.0, score + adj)), 1)
    if mom_60 < -15 and (val_score is None or val_score > 55):
        trend_note.append("近60日下跌 %.0f%% 且估值不贵，属于典型的越跌越买区间" % abs(mom_60))
    if has_val:
        roe = valuation.get("roe")
        div = valuation.get("dividend") or 0.0
        quality_msg = []
        if roe is not None and roe > 15:
            quality_msg.append("ROE %.1f%%" % roe)
        if div > 2:
            quality_msg.append("股息 %.1f%%" % div)
        if quality_msg:
            trend_note.append("质量加分（%s）" % "，".join(quality_msg))
    return score, confidence, trend_note


def verdict_of(score):
    if score >= 80:
        return "明显低估", "可以积极买入", 0.90
    if score >= 70:
        return "低估", "建议分批买入", 0.75
    if score >= 60:
        return "偏低", "可以小仓位买，留钱补", 0.55
    if score >= 50:
        return "中性", "只适合少量试探", 0.35
    if score >= 40:
        return "偏高", "不建议新开仓，持有者可减", 0.20
    if score >= 30:
        return "高估", "不买，只卖出", 0.10
    return "明显高估", "回避", 0.00

# -------------------------------------------------- 全市场 ETF 列表与自动推荐

_UNIVERSE_URL = ("https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                 "Market_Center.getHQNodeData?page=%d&num=100&sort=amount&asc=0"
                 "&node=etf_hq_fund&symbol=&_s_r_a=init")
# 非股票型或没有估值口径的品种不进推荐榜
EXCLUDE_WORDS = ["债", "日利", "添益", "短融", "货币", "现金", "快线", "政金", "黄金",
                 "白银", "原油", "商品", "日元", "美元"]
# 指数代码 -> 额外简称关键词
EXTRA_ALIAS = {
    "SZ399975": ["证券", "券商"], "SH000922": ["红利"], "CSIH30269": ["红利低波", "低波"],
    "CSI930740": ["红利低波", "300红利"], "CSI931157": ["红利", "价值"], "SZ399997": ["白酒", "酒"],
    "SZ399986": ["银行"], "SH000991": ["医药"], "SZ399989": ["医疗", "创新药"], "SH000932": ["消费"],
    "SZ399393": ["房地产", "地产"], "SZ399417": ["新能源", "电池", "新能源车"],
    "SH000827": ["环保", "新能源"], "NDX": ["纳指", "纳斯达克"], "SP500": ["标普500", "标普"],
    "HKHSTECH": ["恒生科技", "港股通科技"], "CSIH30533": ["中概互联", "海外互联", "中国互联网"],
    "CSIH11136": ["中概", "海外互联网"], "HKHSCEI": ["恒生国企", "H股", "国企"],
    "HKHSI": ["恒生", "港股"], "HSFML25": ["香港", "港股"], "SH000688": ["科创50"],
    "SZ399006": ["创业板"], "SH000300": ["沪深300", "300ETF"], "SH000905": ["中证500", "500ETF"],
    "SH000852": ["中证1000", "1000ETF"], "SH000016": ["上证50"], "SZ399967": ["军工", "国防"],
    "SZ399971": ["传媒", "游戏", "影视"], "CSI931079": ["5G", "通信"], "CSI930652": ["电子", "芯片"],
    "CSI931087": ["科技"], "SZ399998": ["煤炭", "煤"], "SZ399812": ["养老"],
    "SZ399996": ["家电"], "SH000015": ["红利"], "SZ399324": ["深证红利", "红利"],
}


OFFSHORE_WORDS = ["港", "恒生", "中概", "海外", "境外", "美国", "纳指", "纳斯达克", "标普500",
                  "德国", "日本", "法国", "英国", "印度", "亚洲", "全球", "东南亚", "大中华",
                  "H股", "H科技", "跨境", "中经", "HK", "港股", "恒生"]
QDII_CODES = {"513030", "513870", "159529", "513290", "513100", "513110", "159941",
              "513500", "159612", "513050", "159607", "513060", "159792", "513130",
              "513180", "159740", "513190", "159920", "159954", "510900", "513630",
              "513920", "159605", "520510", "520500", "513090", "513120", "513010",
              "513260", "513330", "159687", "513750", "513350", "159529"}
OFF_INDEX_WORDS = ["恒生", "港股", "香港", "中概", "中国互联", "国企", "纳指", "纳斯达克",
                   "标普500", "德国", "印度", "美国", "全球", "亚太", "H股", "新经济", "标普"]


def is_offshore_index(index_name):
    return any(w in index_name for w in OFF_INDEX_WORDS)


def _is_stock_etf(name):
    if not name:
        return False
    return not any(w in name for w in EXCLUDE_WORDS)


def etf_universe(pages=8):
    """全市场场内股票型 ETF（按成交额从大到小），缓存 6 小时。"""
    out, seen = [], set()
    for pn in range(1, pages + 1):
        try:
            rows = json.loads(_get(_UNIVERSE_URL % pn, "https://finance.sina.com.cn/",
                                   ttl=21600, key="uni_p%d" % pn))
        except Exception:
            break
        if not rows:
            break
        for r in rows:
            code = str(r.get("code") or "")
            name = r.get("name") or ""
            if code in seen or not re.fullmatch(r"\d{6}", code):
                continue
            seen.add(code)
            try:
                price = float(r.get("trade") or 0)
                amount_wan = float(r.get("amount") or 0) / 10000.0
            except (TypeError, ValueError):
                continue
            if price <= 0 or not _is_stock_etf(name):
                continue
            out.append({
                "code": code, "name": name, "price": price, "amount_wan": amount_wan,
                "quote": {"symbol": ("sh" if code[0] in "569" else "sz") + code, "name": name,
                          "price": price, "prev_close": price, "open": price, "change": 0.0,
                          "change_pct": float(r.get("changepercent") or 0), "high": price,
                          "low": price, "amount_wan": amount_wan,
                          "time": str(r.get("ticktime") or "")}})
        if len(rows) < 100:
            break
        time.sleep(0.25)
    return out


def aliases_for(index_name, index_code):
    al = {index_name}
    for kw, ic in KEYWORD_TO_INDEX:
        if ic == index_code:
            al.add(kw)
    al |= set(EXTRA_ALIAS.get(index_code, []))
    for pre in ("中证", "国证", "全指", "沪深", "上证", "深证", "申万", "主要", "细分"):
        if index_name.startswith(pre) and len(index_name) - len(pre) >= 2:
            al.add(index_name[len(pre):])
    if index_name.endswith("指数"):
        al.add(index_name[:-2])
    return set(a for a in al if len(a) >= 2 and not a.isdigit())


def index_etf_candidates(meta, universe):
    """给一个指数，在全市场里找出跟踪它的 ETF，按成交额从大到小。"""
    aliases = aliases_for(meta["name"], meta["index_code"])
    off = is_offshore_index(meta["name"])
    hits = [e for e in universe
            if any(a in e["name"] for a in aliases)
            and (((any(w in e["name"] for w in OFFSHORE_WORDS)) or e["code"] in QDII_CODES) == off)]
    strict = [e for e in hits
              if (match_index(e["code"], e["name"])[0] or "") == meta["index_code"]]
    pool = strict if strict else hits
    return sorted(pool, key=lambda e: -e["amount_wan"])


def _score_candidate(item):
    a = analyze(item["code"], 0.0, quote=item["quote"], meta=item["meta"])
    v, m, pl = a["valuation"] or {}, a["metrics"], a["plan"]
    return {
        "code": a["code"], "name": a["name"], "price": a["price"],
        "index_name": v.get("index_name") or "-",
        "value_pct": v.get("value_pct"), "grade": v.get("grade") or "-",
        "pe": v.get("pe"), "pb": v.get("pb"), "dividend": v.get("dividend"),
        "roe": v.get("roe"),
        "price_pct": m["price_pct_3y"], "mom_60": m["mom_60"], "vol_y": m["vol_y"],
        "score": a["score"], "verdict": a["verdict"], "action": a["action"],
        "target": pl["target_ratio"], "step_pct": pl["step_pct"],
        "lower": pl["lower"], "upper": pl["upper"],
        "amount_wan": round(a["amount_wan"], 0),
        "peers": [{"code": x["code"], "name": x["name"]} for x in item.get("peers", [])[:4]],
    }


def recommend(mode="value", limit=10, min_amount=2000, only_low=False, sort="score"):
    universe = etf_universe()
    metas = json.loads(_get(_INDEX_LIST_URL, _INDEX_LIST_REF, ttl=3600,
                            key="dj_list"))["data"]["items"]
    items = []
    if mode == "hot":
        for e in sorted(universe, key=lambda x: -x["amount_wan"])[:max(limit, 20)]:
            ic, _kw = match_index(e["code"], e["name"])
            items.append({"code": e["code"], "quote": e["quote"],
                          "meta": index_meta(ic) if ic else None, "peers": []})
    else:
        for meta in metas:
            cands = index_etf_candidates(meta, universe)
            best = next((c for c in cands if c["amount_wan"] >= min_amount), None)
            if not best:
                continue
            items.append({"code": best["code"], "quote": best["quote"], "meta": meta,
                          "peers": cands[:4]})
    items = [it for it in items if not any(w in it["quote"]["name"] for w in EXCLUDE_WORDS)]
    rows, failed = [], []
    done = set()
    with ThreadPoolExecutor(max_workers=4) as pool:
        futs = [(pool.submit(_score_candidate, it), it) for it in items]
        for fu, it in futs:
            try:
                rows.append(fu.result())
                done.add(it["code"])
            except Exception as e:
                failed.append([it["code"], str(e)[:50]])
    for it in items:  # 限流造成的失败，串行补一轮
        if it["code"] in done:
            continue
        try:
            rows.append(_score_candidate(it))
        except Exception as e:
            failed.append([it["code"], "重试:%s" % str(e)[:40]])
    seen, dedup = set(), []
    for r in sorted(rows, key=lambda x: -x["score"]):
        if r["code"] in seen:
            continue
        seen.add(r["code"])
        dedup.append(r)
    if only_low:
        dedup = [r for r in dedup if r["value_pct"] is not None and r["value_pct"] <= 30]
    sorters = {"score": lambda x: -x["score"],
               "value": lambda x: x["value_pct"] if x["value_pct"] is not None else 999,
               "amount": lambda x: -x["amount_wan"]}
    dedup.sort(key=sorters.get(sort, sorters["score"]))
    avoid = sorted([r for r in dedup if r["score"] < 45], key=lambda x: x["score"])[:5]
    return {"rows": dedup[:limit], "avoid": avoid, "mode": mode, "pool": len(items),
            "universe": len(universe), "failed": failed[:8],
            "generated_at": time.strftime("%Y-%m-%d %H:%M:%S")}


# -------------------------------------------------------------------- 命令行报告

def text_report(a):
    ln = []
    ln.append("%s (%s)  现价 %.3f  涨跌 %.2f%%" % (a["name"], a["code"], a["price"], a["change_pct"]))
    ln.append("结论：%s（评分 %.1f，%s）→ %s" % (a["verdict"], a["score"], a["confidence"], a["action"]))
    if a["valuation"] and a["valuation"].get("value_pct") is not None:
        x = a["valuation"]
        ln.append("估值：跟踪 %s｜综合分位 %.1f%%（%s）PE %s 分位 %.1f%% PB %s 分位 %.1f%% 股息 %.2f%%"
                  % (x["index_name"], x["value_pct"], x["grade"], x["pe"] or "亏损/无",
                     x["pe_pct"], x["pb"] or "无", x["pb_pct"], x["dividend"]))
    m = a["metrics"]
    ln.append("价格：近 %.1f 年(样本)分位 %.1f%%｜距52周高点 %.1f%%｜年化波动 %.1f%%｜近60日 %.1f%%"
              %(m["pct_window"], m["price_pct_3y"], m["drawdown_from_hi"], m["vol_y"], m["mom_60"]))
    p = a["plan"]
    if a.get("premium"):
        pm = a["premium"]
        src = "实时IOPV" if pm["realtime"] else "官方净值@%s" % (pm["nav_date"] or "?")
        ln.append("净值：参考净值 %.4f（%s）→ %s %.2f%%"
                  % (pm["ref"], src, "溢价" if pm["pct"] >= 0 else "折价", abs(pm["pct"])))
    ln.append("仓位：建议目标 %.0f%%｜网格间距 %.1f%%，区间 %.3f~%.3f（各 %d 格）"
              % (p["target_ratio"], p["step_pct"], p["lower"], p["upper"], p["grids"]))
    if p["capital"]:
        ln.append("资金 %.0f 元：首批 %.0f 元，其后每跌 %.1f%% 补 %.0f 元（每格约 %.0f 元）"
                  % (p["capital"], p["first_batch"], p["step_pct"], p["per_batch"], p["per_grid_money"]))
    for t in a["trend_note"]:
        ln.append("· " + t)
    for t in a["risk"]:
        ln.append("! " + t)
    return "\n".join(ln)


# ------------------------------------------------------------------------ 页面

HTML = """<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETF 买入诊断器</title><style>
:root{--bg:#0f1420;--card:#18202e;--line:#243044;--tx:#e6edf7;--sub:#93a1b8;--up:#e5544c;--dn:#2fa46a;--ac:#4d8bf0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.6 "Microsoft YaHei",system-ui,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:22px 16px 60px}
h1{font-size:21px;margin:0 0 4px}.sub{color:var(--sub);font-size:13px;margin-bottom:18px}
.bar{display:flex;gap:10px;flex-wrap:wrap;background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
input{background:#0d1320;border:1px solid var(--line);color:var(--tx);padding:11px 12px;border-radius:9px;font-size:15px;width:170px}
button{background:var(--ac);border:0;color:#fff;padding:11px 22px;border-radius:9px;font-size:15px;cursor:pointer}
button:disabled{opacity:.55;cursor:wait}.tabs{display:flex;gap:8px;margin:16px 0 0}
.tabs b{background:#1c2433;border:1px solid var(--line);border-radius:9px 9px 0 0;padding:9px 18px;font-weight:400;font-size:14px;cursor:pointer;color:#9fb0c8}
.tabs b.on{background:var(--card);color:var(--tx);border-bottom-color:var(--card)}
.rec td{cursor:pointer}.rec tr:hover td{background:#1e2734}
.oneline{display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-size:13px;color:var(--sub)}
.oneline input{width:110px;padding:8px 9px;font-size:14px}.oneline select{background:#0d1320;color:var(--tx);border:1px solid var(--line);border-radius:8px;padding:8px 9px}
.quick{margin:10px 0 0;display:flex;gap:8px;flex-wrap:wrap}
.quick b{background:#1c2433;border:1px solid var(--line);border-radius:20px;padding:5px 13px;font-weight:400;font-size:13px;cursor:pointer;color:#bcc8dc}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-top:14px}
.verdict{display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.tag{font-size:27px;font-weight:700;padding:8px 20px;border-radius:10px}
.low{background:rgba(47,164,106,.16);color:#5dd39a;border:1px solid #2fa46a55}
.mid{background:rgba(226,168,60,.14);color:#f0c36a;border:1px solid #e2a83c55}
.high{background:rgba(229,84,76,.14);color:#ff8b84;border:1px solid #e5544c55}
.big{font-size:34px;font-weight:700}.k{color:var(--sub);font-size:12px}
table{width:100%;border-collapse:collapse;margin-top:6px;font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:7px 8px;text-align:right}
th:first-child,td:first-child{text-align:left}th{color:var(--sub);font-weight:400;background:#141c29}
.row2{display:flex;gap:14px;flex-wrap:wrap}.row2>div{flex:1;min-width:300px}
.note{color:#f0c36a;font-size:13px}.warn{color:#ff9b95;font-size:13px}
.foot{color:#6b7a90;font-size:12px;margin-top:16px;line-height:1.7}
canvas{width:100%;height:130px;display:block;margin-top:8px}
.grid-table td.buy{color:#5dd39a}.grid-table td.sell{color:#ff8b84}
</style></head><body><div class="wrap">
<h1>ETF 买入诊断器</h1><div class="sub">输入沪深 ETF 代码 → 告诉你要不要买、买多少、怎么分批。数据免费公开，本地运行。</div>
<div class="tabs"><b class="on" id="tb1" onclick="tab(1)">单只诊断</b><b id="tb2" onclick="tab(2)">自动推荐</b></div>
<div id="pane1">
<div class="bar" style="margin-top:12px">
<input id="code" placeholder="ETF代码 如 512880" maxlength="6">
<input id="capital" placeholder="计划投入金额(元) 可空" style="width:210px">
<button id="go" onclick="run()">诊断</button>
</div>
<div class="quick"><b onclick="q('510300')">沪深300 510300</b><b onclick="q('512880')">证券 512880</b><b onclick="q('588000')">科创50 588000</b><b onclick="q('159915')">创业板 159915</b><b onclick="q('510500')">中证500 510500</b><b onclick="q('513100')">纳指 513100</b><b onclick="q('518880')">黄金 518880</b><b onclick="q('510880')">红利 510880</b></div>
<div id="out"><div class="card" style="color:var(--sub)">等待输入。诊断一只大约需要 2~4 秒（拉行情+K线+估值）。</div></div>
</div>
<div id="pane2" style="display:none">
<div class="card" style="margin-top:12px">
<div class="oneline">
<button id="rgo" onclick="loadRec()">重新筛选</button>
<span>模式
<select id="rmode"><option value="value">估值榜（全市场找最便宜）</option><option value="hot">热度榜（成交最大 20 只）</option></select></span>
<span>排序<select id="rsort"><option value="score">按评分</option><option value="value">按估值分位</option><option value="amount">按成交额</option></select></span>
<span>数量<input id="rlimit" value="15"></span>
<span>最少成交额(万)<input id="rmin" value="2000"></span>
<label><input type="checkbox" id="rlow" style="width:auto"> 只看低估(分位≤30%)</label>
</div>
<div id="rinfo" class="k" style="margin-top:8px">第一次筛选要拉全市场列表和几十只 ETF 的日线，约 10~20 秒；之后 10 分钟内直接走缓存。</div>
<div id="rec"></div>
</div>
<div class="card"><b>怎么用这个榜</b><div class="k" style="margin-top:6px;line-height:1.9">
· 候选池 = 蛋卷有估值覆盖的约 60 个指数，在每个指数的同类 ETF 里挑成交额最大的一只做代表；<br>
· 榜单口径与单只诊断完全一致（0.65 估值分 + 0.35 价格分位，再做趋势修正），所以榜上的分数可以直接和诊断页对比；<br>
· 点任意一行 → 自动跳到诊断页出完整方案（含网格表和具体金额）；<br>
· 没有估值覆盖的品种（黄金、货币、部分冷门主题）不进榜，可在诊断页单独查。</div></div>
</div>
<div class="foot">评分口径：综合评分 = 0.65 × 估值分 + 0.35 × 价格分位（无估值数据时只看价格分位，置信度降为“中”），追高或破位再做小幅修正。<br>
仓位口径：目标仓位是把“计划投入金额”当作该 ETF 的上限来算的百分比；网格间距 = 日波动率 ×1.6（限 1%~6%）。工具不预测涨跌，只给纪律化方案。<br>
数据来源：腾讯行情 / 蛋卷基金指数估值 / 东方财富备用。不构成投资建议。</div>
</div>
<script>
const $=i=>document.getElementById(i);
function q(c){$('code').value=c;run();}
async function run(){
  const c=$('code').value.trim(), m=parseFloat($('capital').value||0);
  if(!/^\\d{6}$/.test(c)){$('out').innerHTML='<div class="card warn">代码要 6 位数字，例如 510300</div>';return;}
  $('go').disabled=true;$('out').innerHTML='<div class="card" style="color:var(--sub)">正在拉取 '+c+' 的行情、K线与估值…</div>';
  try{
    const r=await fetch('/api/etf?code='+c+'&capital='+(m||0));const j=await r.json();
    if(j.error)throw new Error(j.error);render(j,m);}
  catch(e){$('out').innerHTML='<div class="card warn">失败：'+e.message+'（接口偶尔限流，稍等再试；确认是场内 ETF 代码）</div>';}
  $('go').disabled=false;
}
function cls(s){return s>=70?'low':s>=50?'mid':'high';}
function render(a){
  const v=a.valuation, m=a.metrics, p=a.plan;
  let h='';
  h+=`<div class="card verdict">
     <div><div class="tag ${cls(a.score)}">${a.verdict}</div><div class="k" style="margin-top:6px">${a.action}</div></div>
     <div><div class="big">${a.score.toFixed(1)}</div><div class="k">综合评分（0-100，越高越值得买）</div></div>
     <div><div class="big">${a.name}</div><div class="k">${a.code} ｜ 现价 ${a.price.toFixed(3)}（${a.change_pct>0?'+':''}${a.change_pct.toFixed(2)}%）｜ 置信度：${a.confidence}</div></div>
   </div>`;
  h+=`<div class="card"><b>① 值不值得买 —— 估值</b>`;
  if(v&&v.value_pct!=null){
    h+=`<table><tr><th>跟踪指数</th><th>综合分位</th><th>判断</th><th>PE(TTM)</th><th>PE分位</th><th>PB</th><th>PB分位</th><th>股息率</th><th>ROE</th></tr>
    <tr><td>${v.index_name}</td><td><b>${v.value_pct}%</b>（用${v.used}）</td><td>${v.grade}</td><td>${v.pe==null?'-':v.pe}</td><td>${v.pe_pct}%</td><td>${v.pb==null?'-':v.pb}</td><td>${v.pb_pct}%</td><td>${v.dividend}%</td><td>${v.roe==null?'-':v.roe+'%'}</td></tr></table>
    <div class="k" style="margin-top:8px">分位=当前估值在历史中的位置，越低越便宜。${v.value_pct<30?'处于历史低位，长期买入胜率相对高':v.value_pct<70?'处于历史中段，靠估值赚差价的空间有限':'处于历史高位，安全边际薄'}</div>`;
  } else {
    h+=`<div class="note" style="margin-top:8px">该 ETF 没有可用的股票式指数估值（或数据源未覆盖）${v&&v.index_name?'，匹配到指数：'+v.index_name:''}。下面只看价格分位。</div>`;
  }
  h+=`</div>`;
  h+=`<div class="card"><b>② 现在处于什么位置 —— 价格与趋势</b>
    <table><tr><th>近${m.pct_window}年价格分位</th><th>样本${a.history_years}年</th><th>52周高/低</th><th>距高点</th><th>距低点</th><th>MA20/60/250</th><th>年化波动</th><th>近60日涨跌</th></tr>
    <tr><td><b>${m.price_pct_3y}%</b></td><td>${m.hi_52w.toFixed(3)} / ${m.lo_52w.toFixed(3)}</td>
    <td>${m.drawdown_from_hi}%</td><td>+${m.up_from_lo}%</td>
    <td>${m.ma20} / ${m.ma60} / ${m.ma250}</td><td>${m.vol_y}%</td><td>${m.mom_60>0?'+':''}${m.mom_60}%</td></tr></table>
    <canvas id="cv"></canvas>`;
  a.trend_note.forEach(t=>{h+=`<div class="note">· ${t}</div>`;});
  if(a.premium&&a.premium.pct!=null){
    const pm=a.premium, big=Math.abs(pm.pct)>=2;
    const src=pm.realtime?'实时 IOPV':'官方净值'+(pm.nav_date?' @ '+pm.nav_date:'')+(pm.stale?'（QDII 净值滞后，近似值）':'');
    h+=`<div class="${big?'warn':'note'}" style="margin-top:6px">${pm.pct>=0?'溢价':'折价'} <b>${Math.abs(pm.pct)}%</b>　参考净值 ${pm.ref}（${src}）${Math.abs(pm.pct)>=5?'　—— 偏离严重，慎买':''}</div>`;
  }
  h+=`</div>`;
  h+=`<div class="card"><b>③ 买多少 —— 仓位与分批</b>
    <table><tr><th>建议目标仓位</th><th>首批投入</th><th>每格间距</th><th>网格区间</th><th>每格金额</th></tr>
    <tr><td><b>${p.target_ratio}%</b>（占计划金额）</td><td>${p.capital?fmt(p.first_batch)+' 元':'设了金额才有'}</td>
    <td>${p.step_pct}%</td><td>${p.lower.toFixed(3)} ~ ${p.upper.toFixed(3)}</td>
    <td>${p.capital?fmt(p.per_grid_money)+' 元':'-'}</td></tr></table>
    ${p.capital?'<div class="k" style="margin-top:6px">计划金额 '+fmt(p.capital)+' 元；跌一格补一格，涨一格卖一格，走完单边就停在边界外。</div>':'<div class="note" style="margin-top:6px">填上“计划投入金额”后会直接算出每格花多少钱、买多少份。</div>'}
  </div>`;
  if(p.capital){
    h+=`<div class="card"><b>④ 网格价格表（可直接抄进券商条件单）</b><table class="grid-table"><tr><th>档位</th><th>触发价</th><th>动作</th><th>金额</th><th>份数(100份整数倍)</th></tr>`;
    p.grid_rows.forEach(r=>{const c=r.side=='买入'?'buy':'sell';
      h+=`<tr><td>${r.level>0?'+'+r.level:r.level}</td><td>${r.price.toFixed(3)}</td><td class="${c}">${r.side}</td><td>${r.money?fmt(r.money):'-'}</td><td>${r.shares?fmt(r.shares):'-'}</td></tr>`;});
    h+=`</table><div class="k" style="margin-top:6px">每格按 ${fmt(p.per_grid_money)} 元测算；场内 ETF 1 手=100 份。</div></div>`;
  }
  h+=`<div class="card"><b>⑤ 风险提示</b>`;a.risk.forEach(r=>{h+=`<div class="warn">· ${r}</div>`;});
  h+=`<div class="k" style="margin-top:6px">数据时间 ${a.generated_at}，行情时间 ${a.quote_time}，成交额 ${fmt(a.amount_wan)} 万元，样本 ${a.bars} 根日K。</div></div>`;
  $('out').innerHTML=h;
  draw(a.spark);
}
function fmt(n){return (Math.round(n)).toLocaleString('zh-CN');}
function draw(s){
  const cv=$('cv');if(!cv||s.length<2)return;
  const dpr=devicePixelRatio||1, w=cv.clientWidth*dpr, hh=130*dpr;
  cv.width=w;cv.height=hh;const x=cv.getContext('2d');
  const mn=Math.min(...s),mx=Math.max(...s),pad=12*dpr;
  const px=i=>pad+(w-2*pad)*i/(s.length-1), py=v=>hh-pad-(hh-2*pad)*(v-mn)/(mx-mn||1);
  x.strokeStyle='#1f2a3b';x.lineWidth=1;
  for(let i=1;i<4;i++){const y=hh*i/4;x.beginPath();x.moveTo(0,y);x.lineTo(w,y);x.stroke();}
  x.beginPath();x.strokeStyle='#4d8bf0';x.lineWidth=2*dpr;
  s.forEach((v,i)=>i?x.lineTo(px(i),py(v)):x.moveTo(px(i),py(v)));x.stroke();
  x.lineTo(w,hh);x.lineTo(0,hh);x.closePath();x.fillStyle='rgba(77,139,240,.12)';x.fill();
  x.fillStyle='#93a1b8';x.font=(11*dpr)+'px sans-serif';
  x.fillText('近120日走势 高'+mx.toFixed(3)+' 低'+mn.toFixed(3),pad,14*dpr);
}
$('code').addEventListener('keydown',e=>{if(e.key=='Enter')run();});
function tab(n){
  $('tb1').className=n==1?'on':'';$('tb2').className=n==2?'on':'';
  $('pane1').style.display=n==1?'':'none';$('pane2').style.display=n==2?'':'none';
  if(n==2&&!window._rec)loadRec();
}
async function loadRec(){
  const q='/api/recommend?mode='+$('rmode').value+'&sort='+$('rsort').value+'&limit='+($('rlimit').value||15)
    +'&min_amount='+($('rmin').value||2000)+'&only_low='+($('rlow').checked?1:0);
  $('rgo').disabled=true;$('rinfo').innerHTML='筛选中…';
  try{
    const r=await fetch(q);const j=await r.json();
    if(j.error)throw new Error(j.error);window._rec=j;renderRec(j);
    $('rinfo').innerHTML='候选池 '+j.pool+' 只（全市场 '+j.universe+' 只股票型 ETF）｜口径：估值榜同类里成交额最大的一只做代表｜生成 '+j.generated_at+(j.failed.length?'｜跳过 '+j.failed.length+' 只取数失败':'');
  }catch(e){$('rec').innerHTML='<div class="warn">筛选失败：'+e.message+'（接口可能限流，稍等再点一次）</div>';}
  $('rgo').disabled=false;
}
function pill(x){
  if(x==null)return '<span class="k">无估值</span>';
  const c=x<30?'low':x<70?'mid':'high';
  return '<span class="tag '+c+'" style="font-size:13px;padding:2px 9px">'+x+'%</span>';
}
function renderRec(j){
  let h='<table class="rec"><tr><th>#</th><th>ETF</th><th>跟踪指数</th><th>估值分位</th><th>价格分位</th><th>评分</th><th>结论</th><th>建议仓位</th><th>网格间距</th><th>股息率</th><th>成交额(万)</th><th>同类替代</th></tr>';
  j.rows.forEach((x,i)=>{
    h+='<tr data-c="'+x.code+'">';
    h+='<td>'+(i+1)+'</td><td><b>'+x.name+'</b><br><span class="k">'+x.code+' 现价'+x.price.toFixed(3)+' '+(x.mom_60>0?'+':'')+x.mom_60+'%/60日</span></td>';
    h+='<td>'+x.index_name+'</td><td>'+pill(x.value_pct)+'</td><td>'+x.price_pct+'%</td>';
    h+='<td><b>'+x.score+'</b></td><td>'+x.verdict+'</td><td>'+x.target+'%</td><td>'+x.step_pct+'%</td>';
    h+='<td>'+(x.dividend==null?'-':x.dividend+'%')+'</td><td>'+Math.round(x.amount_wan).toLocaleString('zh-CN')+'</td>';
    h+='<td class="k">'+x.peers.filter(y=>y.code!=x.code).map(y=>y.code).join('、')+'</td></tr>';
  });
  h+='</table>';
  if(!j.rows.length)h='<div class="note">这个条件下没有标的入选，放宽最少成交额或取消“只看低估”再试。</div>';
  if(j.avoid.length){
    h+='<div style="margin-top:14px"><b style="font-size:14px">同时，这几只评分最低（不建议新开仓，持有者可考虑减）</b><table class="rec"><tr><th>ETF</th><th>跟踪指数</th><th>估值分位</th><th>价格分位</th><th>评分</th><th>结论</th></tr>';
    j.avoid.forEach(x=>{h+='<tr data-c="'+x.code+'"><td>'+x.name+'<br><span class="k">'+x.code+'</span></td><td>'+x.index_name+'</td><td>'+pill(x.value_pct)+'</td><td>'+x.price_pct+'%</td><td><b>'+x.score+'</b></td><td>'+x.verdict+'</td></tr>';});
    h+='</table></div>';
  }
  $('rec').innerHTML=h;
  $('rec').onclick=ev=>{const tr=ev.target.closest('tr[data-c]');if(tr)pick(tr.getAttribute('data-c'));};
}
function pick(c){$('code').value=c;tab(1);run();}
</script></body></html>"""


# -------------------------------------------------------------------- HTTP 服务

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, ctype="application/json; charset=utf-8", code=200):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            self._send(HTML, "text/html; charset=utf-8")
            return
        if u.path == "/api/recommend":
            q = parse_qs(u.query)

            def num(name, dft, cast=float):
                try:
                    return cast((q.get(name) or [dft])[0])
                except (TypeError, ValueError):
                    return cast(dft)
            key = "rec_%s_%s_%s_%s_%s" % ((q.get("mode") or ["value"])[0], num("limit", 10, int),
                                          num("min_amount", 2000, int),
                                          (q.get("only_low") or ["0"])[0],
                                          (q.get("sort") or ["score"])[0])
            hit = _cache.get(key)
            if hit and time.time() - hit[0] < 600:
                self._send(json.dumps(hit[1], ensure_ascii=False))
                return
            try:
                res = recommend(mode=(q.get("mode") or ["value"])[0],
                                limit=int(num("limit", 10, int)),
                                min_amount=int(num("min_amount", 2000, int)),
                                only_low=(q.get("only_low") or ["0"])[0] == "1",
                                sort=(q.get("sort") or ["score"])[0])
            except Exception as e:
                self._send(json.dumps({"error": str(e)}, ensure_ascii=False), code=502)
                return
            if res.get("rows"):
                with _lock:
                    _cache[key] = (time.time(), res)
            self._send(json.dumps(res, ensure_ascii=False))
            return
        if u.path == "/api/etf":
            qs = parse_qs(u.query)
            code = (qs.get("code") or [""])[0]
            try:
                capital = float((qs.get("capital") or ["0"])[0] or 0)
            except ValueError:
                capital = 0.0
            try:
                self._send(json.dumps(analyze(code, capital), ensure_ascii=False))
            except Exception as e:
                self._send(json.dumps({"error": str(e)}, ensure_ascii=False), code=502)
            return
        self._send("not found", "text/plain; charset=utf-8", 404)


def main():
    if len(sys.argv) > 1 and re.fullmatch(r"\d{6}", sys.argv[1]):
        capital = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
        print(text_report(analyze(sys.argv[1], capital)))
        return
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    url = "http://%s:%d" % (HOST, PORT)
    print("ETF 诊断器已启动：%s  （Ctrl+C 退出）" % url)
    print("命令行模式：python etf_advisor.py 512880 200000")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    srv.serve_forever()


if __name__ == "__main__":
    main()
