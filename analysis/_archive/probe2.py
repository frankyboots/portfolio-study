import xlrd, math

wb = xlrd.open_workbook('ie_data.xls')
d = wb.sheet_by_name('Data')
nrows = d.nrows

def num(v):
    if isinstance(v,(int,float)): return v
    if isinstance(v,str):
        s = v.strip()
        if s == '' or s.upper() == 'NA': return None
        try: return float(s)
        except: return v
    return None

rows = []
for r in range(8, nrows):
    vals = d.row_values(r)
    rows.append([num(v) for v in vals])

data = rows[:-1]  # last row = notes
print("data rows:", len(data))

dates = [row[0] for row in data]
print("first:", dates[0], "last:", dates[-1])

def ym(dt):
    yr = int(math.floor(dt + 1e-9))
    mo = int(round((dt - yr) * 12 + 1e-9)) + 1
    return (yr, mo)
seq = [ym(dt) for dt in dates]
gaps = []
for i in range(1,len(seq)):
    py, pm = seq[i-1]; cy, cm = seq[i]
    expected = (py+1,1) if pm==12 else (py,pm+1)
    if (cy,cm) != expected:
        gaps.append((seq[i-1], seq[i]))
print("gaps/out-of-order count:", len(gaps), gaps[:10])
print("duplicate dates:", len(seq)-len(set(seq)))

names = ['Date','P','D','E','CPI','Frac','GS10','RealP','RealD','RealTR','RealE','RealTRE','CAPE','_','TRCAPE','_','ExcessYield','BndM','BndR','A10s','A10b','A10ex']
for c in range(1,22):
    col = [row[c] for row in data]
    numidx = [i for i,v in enumerate(col) if isinstance(v,(int,float))]
    strs = set(str(v).strip() for i,v in enumerate(col) if isinstance(v,str))
    first = dates[numidx[0]] if numidx else None
    last = dates[numidx[-1]] if numidx else None
    if numidx:
        print(f"col {c:2d} {names[c]:12s} n={len(numidx):5d} first={first} last={last} min={min(col[i] for i in numidx):.8g} max={max(col[i] for i in numidx):.8g} strs={strs if strs else ''}")
    else:
        print(f"col {c:2d} {names[c]:12s} n=0 strs={strs}")
