import xlrd, math
import numpy as np
wb = xlrd.open_workbook('ie_data.xls')
d = wb.sheet_by_name('Data')
nrows = d.nrows
def num(v):
    if isinstance(v,(int,float)): return v
    if isinstance(v,str):
        s=v.strip()
        if s=='' or s.upper()=='NA': return None
        try: return float(s)
        except: return v
    return None
rows = [[num(v) for v in d.row_values(r)] for r in range(8, nrows-1)]
n=len(rows)
CPI=np.array([r[4] for r in rows]); GS=np.array([r[6] for r in rows])
BM=np.array([r[17] if r[17] is not None else np.nan for r in rows])
BR=np.array([r[18] for r in rows])
dates=[r[0] for r in rows]
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

# 1) Yearly median implied duration for BM to find the regime break
dgs = np.diff(GS)/100.0
rp = (BM[1:]-1)-GS[1:]/1200
with np.errstate(divide='ignore', invalid='ignore'):
    k = -rp/dgs
k = np.where(np.abs(dgs)>2e-4, k, np.nan)
yrs = np.array([int(dt//1) for dt in dates[1:]])
print("BM implied duration by year (median, n valid):")
prev=None
for y in range(1871, 2027):
    sel = k[yrs==y]
    sel = sel[np.isfinite(sel)]
    if len(sel)>=4:
        med = float(np.median(sel))
        flag = ""
        if prev is not None and abs(med-prev)>2.5: flag=" <<< BREAK"
        print(f"  {y}: {med:7.2f} (n={len(sel)}){flag}")
        prev=med
    else:
        print(f"  {y}:   n/a  (n={len(sel)})")
