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
        q = agg(days, 'Q')
        y = agg(days, 'Y')
        json.dump(q, open(f"quarter/{code}.json", 'w', encoding='utf-8'), ensure_ascii=False)
        json.dump(y, open(f"year/{code}.json", 'w', encoding='utf-8'), ensure_ascii=False)
    except Exception as ex:
        pass
print("quarter/year 重算完成")

# 3) 更新 meta 最新价
for m in meta:
    code = m["code"]
    d = delta.get(code) or []
    if d:
        last = d[-1]
        m["price"], m["date"] = last[4], last[0]
json.dump(meta, open(meta_path, 'w', encoding='utf-8'), ensure_ascii=False)
print("完成")
