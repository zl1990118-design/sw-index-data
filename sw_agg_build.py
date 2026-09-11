# -*- coding: utf-8 -*-
"""从日K聚合生成 季K/年K（全量），输出 quarter/{code}.json + year/{code}.json
用法: python3 sw_agg_build.py
"""
import json, os, glob
OUT = "."
os.makedirs(f"{OUT}/quarter", exist_ok=True)
os.makedirs(f"{OUT}/year", exist_ok=True)

def agg(days, gran):
    """days: [[YYYYMMDD,o,h,l,c],...] 升序; gran: 'Q'/'Y' -> 返回 [[YYYYMMDD,o,h,l,c],...]"""
    groups = {}
    order = []
    for r in days:
        d = r[0]
        if gran == 'Q':
            key = (d // 10000, (d % 10000 - 1) // 300 + 1)  # (year, q)
        else:
            key = (d // 10000,)
        if key not in groups:
            groups[key] = None
            order.append(key)
        g = groups[key]
        if g is None:
            groups[key] = [r[0], r[1], r[2], r[3], r[4]]
        else:
            g[1] = r[1] if g[1] is None else g[1]  # open 取季首根（保留首根）
            g[2] = max(g[2], r[2])
            g[3] = min(g[3], r[3])
            g[4] = r[4]  # close 取末根
            g[0] = r[0]  # date 取末根日期
    return [groups[k] for k in order]

total_q = total_y = 0
for fp in glob.glob(f"{OUT}/sw/*.json"):
    code = os.path.basename(fp)[:-5]
    try:
        e = json.load(open(fp, encoding='utf-8'))
        days = e.get("day") or []
        if not days:
            continue
        q = agg(days, 'Q')
        y = agg(days, 'Y')
        if q:
            json.dump(q, open(f"{OUT}/quarter/{code}.json", 'w', encoding='utf-8'), ensure_ascii=False)
            total_q += 1
        if y:
            json.dump(y, open(f"{OUT}/year/{code}.json", 'w', encoding='utf-8'), ensure_ascii=False)
            total_y += 1
    except Exception as ex:
        print(f"{code} ERR {repr(ex)[:40]}")

print(f"完成: quarter {total_q} 个, year {total_y} 个")
