# -*- coding: utf-8 -*-
"""申万指数每日增量更新（GitHub Actions 15:30 运行）
1) 拉官网全量日K（trend接口无日期参数）→ 取最近30天 → 合并 delta/{当月}.json（防漏）
2) 用 sw/{code}.json 全量日K + delta 当月 聚合 → 重算 quarter/{code}.json + year/{code}.json
3) 更新 meta.json（最新价/日期）
"""
import requests, json, os, time
import warnings; warnings.filterwarnings('ignore')
H = {"User-Agent":"Mozilla/5.0"}
BASE = "https://www.swsresearch.com/institute-sw/api/index_publish/trend/"
OUT = "."
os.makedirs(f"{OUT}/quarter", exist_ok=True)
os.makedirs(f"{OUT}/year", exist_ok=True)

# 1) 读 meta 拿 code 清单
meta_path = "meta.json"
meta = json.load(open(meta_path, encoding='utf-8')) if os.path.exists(meta_path) else []
codes = [m["code"] for m in meta]
if not codes:
    codes = [f[:-5] for f in os.listdir("sw") if f.endswith(".json")]
print(f"指数数: {len(codes)}")

ym = time.strftime("%Y-%m")
delta_path = f"delta/{ym}.json"
delta = json.load(open(delta_path, encoding='utf-8')) if os.path.exists(delta_path) else {}

today = int(time.strftime("%Y%m%d"))
month6 = int(time.strftime("%Y%m"))
start_ymd = today - 40  # 最近40天起点（跨月覆盖）

changed = 0
for i, code in enumerate(codes):
    try:
        r = requests.get(BASE, params={"swindexcode": code, "period": "DAY"}, headers=H, timeout=30, verify=False)
        rows = r.json().get('data') or []
        if not rows:
            continue
        # 取最近30个交易日
        recent = rows[-30:]
        dlist = delta.setdefault(code, [])
        dates = {str(x[0]) for x in dlist}
        for x in recent:
            dt = int(str(x.get('bargaindate'))[:10].replace('-', ''))
            if str(dt) not in dates:
                try:
                    dlist.append([dt, round(float(x.get('openindex')),2), round(float(x.get('maxindex')),2),
                                  round(float(x.get('minindex')),2), round(float(x.get('closeindex')),2)])
                    changed += 1
                except Exception:
                    pass
        dlist.sort(key=lambda x: x[0])
        # 截断 delta 只留当月（避免跨月膨胀）
        dlist = [x for x in dlist if str(x[0])[:6] == ym.replace('-', '')]
        delta[code] = dlist
    except Exception as e:
        print(f"{code} ERR {repr(e)[:40]}", flush=True)
    time.sleep(0.08)
    if i % 100 == 0:
        print(f"day {i}/{len(codes)} done", flush=True)

json.dump(delta, open(delta_path, 'w', encoding='utf-8'), ensure_ascii=False)
print(f"delta/{ym}.json: 新增 {changed} 条")

# 2) 聚合 季K/年K（sw day 全量 + delta 当月 合并）
def agg(days, gran):
    groups, order = {}, []
    for r in days:
        d = r[0]
        key = (d // 10000, (d % 10000 - 1) // 300 + 1) if gran == 'Q' else (d // 10000,)
        if key not in groups:
            groups[key] = [r[0], r[1], r[2], r[3], r[4]]
            order.append(key)
        else:
            g = groups[key]
            g[2] = max(g[2], r[2]); g[3] = min(g[3], r[3]); g[4] = r[4]; g[0] = r[0]
    return [groups[k] for k in order]

_ALL_DAYS = {}
for i, code in enumerate(codes):
    try:
        e = json.load(open(f"sw/{code}.json", encoding='utf-8'))
        dmap = {}
        for x in e.get("day") or []:
            dmap[x[0]] = x
        for x in delta.get(code) or []:
            dmap[x[0]] = x
        days = [dmap[k] for k in sorted(dmap)]
        if not days:
            continue
        _ALL_DAYS[code] = days
        q = agg(days, 'Q')
        y = agg(days, 'Y')
        json.dump(q, open(f"quarter/{code}.json", 'w', encoding='utf-8'), ensure_ascii=False)
        json.dump(y, open(f"year/{code}.json", 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception as ex:
        pass
print("quarter/year 重算完成")

# 3) 更新 meta 最新价 + 日/周涨跌幅 + 高低点统计（30/40日×高低×天/周/月）
import datetime as _dt
def _hstat(days, n, is_high):
    recent = days[-n:]
    if len(recent) < 2: return None
    t = max(recent, key=lambda x: x[2]) if is_high else min(recent, key=lambda x: x[3])
    last = days[-1]
    ti = days.index(t)
    dn = len(days) - 1 - ti
    d1, d2 = t[0], last[0]
    dt1 = _dt.date(d1//10000, (d1%10000)//100, d1%100)
    dt2 = _dt.date(d2//10000, (d2%10000)//100, d2%100)
    wn = max(0, (dt2 - dt1).days // 7)
    mn = max(0, (d2//10000 - d1//10000)*12 + ((d2%10000)//100 - (d1%10000)//100))
    return dn, wn, mn
def _week_pct(days):
    weeks = {}
    for d in days:
        dt = _dt.date(d[0]//10000, (d[0]%10000)//100, d[0]%100)
        weeks[dt.isocalendar()[:2]] = d[4]
    ks = sorted(weeks)
    if len(ks) >= 2 and weeks[ks[-2]]:
        return round((weeks[ks[-1]]/weeks[ks[-2]]-1)*100, 2)
    return None
for m in meta:
    code = m["code"]
    days = _ALL_DAYS.get(code) or []
    if days:
        last = days[-1]
        m["price"], m["date"] = last[4], last[0]
        if len(days) >= 2:
            m["day_pct"] = round((days[-1][4]/days[-2][4]-1)*100, 2)
        wp = _week_pct(days)
        if wp is not None: m["week_pct"] = wp
        for pn, keyn in ((30,'30'), (40,'40')):
            for is_high, hn in ((True,'hi'), (False,'lo')):
                r = _hstat(days, pn, is_high)
                if r:
                    m[f"h{keyn}{hn}_days"], m[f"h{keyn}{hn}_weeks"], m[f"h{keyn}{hn}_months"] = r
json.dump(meta, open(meta_path, 'w', encoding='utf-8'), ensure_ascii=False)
print("完成")
