# -*- coding: utf-8 -*-
"""申万指数每日增量更新（GitHub Actions 15:30 运行）
- 拉官网 history_home（每指数最新1条含当日OHLC）
- 追加缺失交易日到 delta/{YYYY-MM}.json
- 更新 meta.json（最新价/日期）
"""
import requests, json, os, time, re
import warnings; warnings.filterwarnings('ignore')
H = {"User-Agent":"Mozilla/5.0"}
HOME = "https://www.swsresearch.com/institute-sw/api/index_publish/history_home/"
BASE = "https://www.swsresearch.com/institute-sw/api/index_publish/trend/"

# 1) 拉全量最新列表（分页取完）
all_items = []
page, page_size = 1, 100
while True:
    r = requests.get(HOME, params={"page": page, "page_size": page_size}, headers=H, timeout=20, verify=False)
    d = r.json()
    data = d.get("data") or {}
    all_items.extend(data.get("results") or [])
    nxt = data.get("next")
    if not nxt or not data.get("results"):
        break
    page += 1
    time.sleep(0.15)
print(f"官网列表: {len(all_items)} 条")

# 2) 读 meta 拿需要的 code（只更新已在仓库的指数）
meta_path = "meta.json"
meta = json.load(open(meta_path, encoding='utf-8')) if os.path.exists(meta_path) else []
codes = {m["code"] for m in meta}
if not codes:
    # 从 sw/ 目录回退
    codes = {f[:-5] for f in os.listdir("sw") if f.endswith(".json")}

# 3) 拉每个指数当日（trend 全量取末根 = 当日，比 history_home 更稳）
now = time.strftime("%Y-%m")
ym = now
delta_path = f"delta/{ym}.json"
delta = json.load(open(delta_path, encoding='utf-8')) if os.path.exists(delta_path) else {}

changed = 0
new_meta_price = {}
for i, code in enumerate(sorted(codes)):
    try:
        r = requests.get(BASE, params={"swindexcode": code, "period": "DAY"}, headers=H, timeout=25, verify=False)
        rows = r.json().get('data') or []
        if not rows:
            continue
        last = rows[-1]
        dt = str(last.get('bargaindate'))[:10].replace('-', '')
        o = round(float(last.get('openindex')), 2)
        h = round(float(last.get('maxindex')), 2)
        lo = round(float(last.get('minindex')), 2)
        c = round(float(last.get('closeindex')), 2)
        dlist = delta.setdefault(code, [])
        # 若末日不存在则追加
        dates = {str(x[0]) for x in dlist}
        if dt not in dates:
            dlist.append([int(dt), o, h, lo, c])
            dlist.sort(key=lambda x: x[0])
            changed += 1
        new_meta_price[code] = (c, int(dt))
    except Exception as e:
        print(f"{code} ERR {repr(e)[:50]}", flush=True)
    time.sleep(0.1)
    if i % 100 == 0:
        print(f"{i}/{len(codes)} done", flush=True)

# 4) 写回 delta
json.dump(delta, open(delta_path, 'w', encoding='utf-8'), ensure_ascii=False)
print(f"delta/{ym}.json: 新增 {changed} 条, 指数数 {len(delta)}")

# 5) 更新 meta 最新价
if new_meta_price:
    for m in meta:
        if m["code"] in new_meta_price:
            m["price"], m["date"] = new_meta_price[m["code"]]
    json.dump(meta, open(meta_path, 'w', encoding='utf-8'), ensure_ascii=False)
    print("meta.json 已更新")

print("完成")
