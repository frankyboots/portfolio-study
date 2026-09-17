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

# BM implied duration with tiny threshold
dgs = np.diff(GS)/100.0
rp = (BM[1:]-1)-GS[1:]/1200
k = -rp/dgs
valid = (np.abs(dgs) > 1e-4) & np.isfinite(k)
import statistics
def era(yr0,yr1):
    yrs = np.array([int(dt//1) for dt in dates[1:]])
    sel = k[valid & (yrs>=yr0) & (yrs<=yr1)]
    if len(sel)==0: return None
    return f"n={len(sel)} med={np.median(sel):.2f} p10={np.percentile(sel,10):.2f} p90={np.percentile(sel,90):.2f} min={sel.min():.2f} max={sel.max():.2f}"
for yr0,yr1 in [(1871,1899),(1900,1929),(1930,1969),(1970,1979),(1980,1989),(1990,1999),(2000,2009),(2010,2026)]:
    print(f"BM implied duration {yr0}-{yr1}: {era(yr0,yr1)}")

# recovered price level from BM, corr with Z10 and Z30
Pb=np.empty(n); Pb[0]=1.0
for i in range(1,n):
    if np.isnan(BM[i]) or np.isnan(GS[i]): Pb[i]=Pb[i-1]
    else: Pb[i]=Pb[i-1]*BM[i]-GS[i]/1200
Z10=(1+GS/100)**-10
corr = np.corrcoef(Z10, Pb)[0,1]
Z30=(1+GS/100)**-30
corr30 = np.corrcoef(Z30, Pb)[0,1]
print(f"\n[BM] corr(recovered price, Z10) = {corr:.4f}; corr(Z30) = {corr30:.4f}")
print(f"     Pb first/last: {Pb[0]:.4f} {Pb[-1]:.4f}; Z10 first/last: {Z10[0]:.4f} {Z10[-1]:.4f}")
# also try: coupon = previous month GS (lagged coupon)
Pb2=np.empty(n); Pb2[0]=1.0
for i in range(1,n):
    if np.isnan(BM[i]): Pb2[i]=Pb2[i-1]
    else: Pb2[i]=Pb2[i-1]*BM[i]-GS[i-1]/1200
print(f"     (lagged coupon) corr Z10 = {np.corrcoef(Z10,Pb2)[0,1]:.4f}")

# BR implied real returns vs proper 10y par bond real returns
dgs2 = np.diff(GS)/100.0
infl = np.diff(CPI)/CPI[:-1]
g = BR[1:]/BR[:-1]
for D in (7.5, 8.0, 8.26, 9.0):
    rnom = GS[1:]/1200 - D*dgs2
    pred = (1+rnom)/(1+infl)
    e = np.abs(g-pred)/pred
    bad = (e>1e-8).sum()
    print(f"[BR] proper 10y par D={D}: mismatches {bad}/{len(e)}, maxrel {e.max():.3e}")

# What if BR real return uses arith deflation: r_real = r_nom - infl
for D in (7.5, 8.0):
    rnom = GS[1:]/1200 - D*dgs2
    pred = 1 + rnom - infl
    e = np.abs(g-pred)/pred
    bad = (e>1e-8).sum()
    print(f"[BR] arith deflation D={D}: mismatches {bad}/{len(e)}, maxrel {e.max():.3e}")

# print BR g and components for the worst months
order = np.argsort(-np.abs(g - (1+GS[1:]/1200-8.0*dgs2)/(1+infl)))[:12]
print("\nworst-12 months for D=8.0 proper model:")
for j in order:
    i=j+1
    print(f"  {ym(i)}: g={g[j]:.4f} pred={(1+GS[i]/1200-8.0*dgs[j])/(1+infl[j]):.4f} GS={GS[i]} dGS={dgs[j]*100:.2f}bp infl={infl[j]*100:.2f}% BM={BM[i]}")
