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
rows = [[num(v) for v in d.row_values(r)] for r in range(8, nrows-1)]
n=len(rows)
P=np.array([r[1] for r in rows]); D=np.array([r[2] if r[2] is not None else np.nan for r in rows])
E=np.array([r[3] if r[3] is not None else np.nan for r in rows])
CPI=np.array([r[4] for r in rows]); GS=np.array([r[6] for r in rows])
RE=np.array([r[10] if r[10] is not None else np.nan for r in rows])
CAPE=np.array([r[12] if r[12] is not None else np.nan for r in rows])
BM=np.array([r[17] if r[17] is not None else np.nan for r in rows])
BR=np.array([r[18] for r in rows]); F=np.array([r[5] for r in rows])
dates=[r[0] for r in rows]
def idx(y,m): return (y-1871)*12+(m-1)
def dt(i):
    return f"{int(dates[i]//1)}.{int(round((dates[i]-int(dates[i]))*100)):02d}"

# 1929 crash + 1926 + 1957 context
print("1929.09-10:", [(dt(i), round(P[i],2), round(P[i]/P[i-1],4)) for i in range(idx(1929,9), idx(1929,11))])
print("1957.06-10:", [(dt(i), round(P[i],2), round(P[i]/P[i-1],4)) for i in range(idx(1957,6), idx(1957,11))])
print("CPI splice 1912.12-1913.02:", [(dt(i), round(CPI[i],3)) for i in range(idx(1912,12), idx(1913,3))])
print("CPI 2025.09-2026.09:", [(dt(i), round(CPI[i],4)) for i in range(idx(2025,9), n)])
i_min,i_max = GS.argmin(), GS.argmax()
print(f"GS10 min {GS[i_min]:.2f}@{dt(i_min)} max {GS[i_max]:.2f}@{dt(i_max)}")
ca=[i for i in range(n) if not np.isnan(CAPE[i])]
print(f"CAPE: first {dt(ca[0])} last {dt(ca[-1])}; n={len(ca)}")
print(f"CAPE min {CAPE[ca].min():.2f}@{dt(ca[int(CAPE[ca].argmin())])} max {CAPE[ca].max():.2f}@{dt(ca[int(CAPE[ca].argmax())])}")
# tail CAPE with missing earnings
i=n-1
win=[RE[j] for j in range(i-119,i+1)]; avail=[x for x in win if not np.isnan(x)]
print(f"tail {dt(i)}: stored={CAPE[i]:.4f} P/mean(avail {len(avail)})={P[i]/(sum(avail)/len(avail)):.4f}")
ok = sum(1 for i in range(n) if abs(F[i] - ((int(round((dates[i]-int(dates[i]))*100)))-0.5)/12) < 1e-9)
print(f"Fraction mid-month matches {ok}/{n}")
print(f"BM min {BM.min():.4f}@{dt(int(BM.argmin()))} max {BM.max():.4f}@{dt(int(BM.argmax()))} missing={int(np.isnan(BM).sum())}")
print(f"BR min {BR.min():.4f}@{dt(int(BR.argmin()))} max {BR.max():.4f}@{dt(int(BR.argmax()))}")
lg=np.log(BR[1:]/BR[:-1]); lb=np.log(BM[1:])
print(f"corr(log growth BR, log BM)={np.corrcoef(lg,lb)[0,1]:.6f}")
# D/E update pattern in recent years
for nm,arr in [('D',D),('E',E)]:
    chgs=[dt(i) for i in range(idx(2024,1), n) if not np.isnan(arr[i]) and not np.isnan(arr[i-1]) and arr[i]!=arr[i-1]]
    print(f"{nm} updates 2024+: {chgs}")
