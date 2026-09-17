import xlrd
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
rows = [[num(v) for v in d.row_values(r)] for r in range(8, nrows)]
n=len(rows)-1  # last is notes
P=np.array([r[1] for r in rows[:n]]); GS=np.array([r[6] for r in rows[:n]])
RT=np.array([r[9] for r in rows[:n]]); CAPE=np.array([r[12] if r[12] is not None else np.nan for r in rows[:n]])
BM=np.array([r[17] if r[17] is not None else np.nan for r in rows[:n]])
BR=np.array([r[18] for r in rows[:n]])
dates=[r[0] for r in rows[:n]]
def dt(i): return f"{int(dates[i]//1)}.{int(round((dates[i]-int(dates[i]))*100)):02d}"
def idx(y,m): return (y-1871)*12+(m-1)

pr=P[1:]/P[:-1]
jumps=[(dt(i+1), round(pr[i],4)) for i in range(len(pr)) if abs(pr[i]-1)>0.15]
print("P jumps >15%:", jumps)
bmv=BM[~np.isnan(BM)]
i_min=int(np.nanargmin(BM)); i_max=int(np.nanargmax(BM))
print(f"BM min {BM[i_min]:.4f}@{dt(i_min)}; max {BM[i_max]:.4f}@{dt(i_max)}")
m=~np.isnan(BM)
print(f"corr(log growth BR vs BM)={np.corrcoef(np.log(BR[1:]/BR[:-1]), np.log(BM[1:][1:]))[0,1]:.6f}  (over {m.sum()-1} months)")
print(f"BR 2026.09 = {BR[-1]:.4f}; BR 2020.04 = {BR[idx(2020,4)]:.4f}")
print(f"RT 1871.01={RT[0]:.2f}  RT 2026.09={RT[-1]:.0f}")
print(f"P 1871.01={P[0]} P 2026.09={P[-1]}")
print(f"CAPE 1929.09={CAPE[idx(1929,9)]:.2f}  CAPE 2026.09={CAPE[-1]:.2f}")
# notes row verbatim
print("NOTES:", [str(v) for v in d.row_values(nrows-1) if str(v).strip()])
