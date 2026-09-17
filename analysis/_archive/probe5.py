import xlrd, math

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
P=[r[1] for r in rows]; D=[r[2] for r in rows]; E=[r[3] for r in rows]
CPI=[r[4] for r in rows]; GS=[r[6] for r in rows]; RP=[r[7] for r in rows]
RT=[r[9] for r in rows]; RE=[r[10] for r in rows]; RTE=[r[11] for r in rows]
CAPE=[r[12] for r in rows]; TRC=[r[14] for r in rows]; EY=[r[16] for r in rows]
BM=[r[17] for r in rows]; BR=[r[18] for r in rows]
dates=[r[0] for r in rows]
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

# ---- BM: fit BM[i] = 1 + GS[i]/1200 - x*(GS[i]-GS[i-1])/100
ys=[]; xs=[]; consts=[]
for i in range(1,n):
    if BM[i] is None or GS[i] is None or GS[i-1] is None: continue
    coupon = GS[i]/1200.0
    dgs = (GS[i]-GS[i-1])/100.0
    price = BM[i]-1-coupon
    ys.append(-price); xs.append(dgs)
m=len(xs); sx=sum(xs); sy=sum(ys); sxx=sum(a*a for a in xs); sxy=sum(x*y for x,y in zip(xs,ys))
xhat=(m*sxy-sx*sy)/(m*sxx-sx*sx)
bhat=(sy-xhat*sx)/m
resid=[abs(ys[i]-(xhat*xs[i]+bhat)) for i in range(m)]
print(f"[BM] OLS slope (duration) = {xhat:.4f}, intercept = {bhat:.8f}, max resid {max(resid):.3e}")
# also pure model with dur=7.7, no intercept: count close matches
for dur in (7.6,7.69,7.7,7.75,8.0):
    bad=0; maxr=0
    for i in range(1,n):
        if BM[i] is None: continue
        exp = 1 + GS[i]/1200.0 - dur*(GS[i]-GS[i-1])/100.0
        e=abs(BM[i]-exp); maxr=max(maxr,e)
        if e>1e-6: bad+=1
    print(f"   dur={dur}: mismatches {bad}/{n-1}, max abs {maxr:.2e}")
# check first month
print(f"[BM] first month: BM[0]={BM[0]}, implied prev GS = {GS[0]-(BM[0]-1-GS[0]/1200)/(-xhat):.4f}")

# ---- BR: implied monthly growth g[i] = BR[i]/BR[i-1]; compare candidates
infl=[None]+[CPI[i]/CPI[i-1]-1 for i in range(1,n)]
tests={'geo: BM/(1+infl)': lambda i: BM[i]/(1+infl[i]),
       'arith: 1+(BM-1)-infl': lambda i: 1+(BM[i]-1)-infl[i],
       'geo2: (1+GS/12)/(1+infl)': lambda i: (1+GS[i]/1200)/(1+infl[i]),
       'arith2: 1+GS/12-infl': lambda i: 1+GS[i]/1200-infl[i]}
for nm,f in tests.items():
    bad=0; maxr=0
    for i in range(1,n):
        if BR[i] is None or BR[i-1] is None or BM[i] is None: continue
        g=BR[i]/BR[i-1]; e=abs(g-f(i))
        maxr=max(maxr,e)
        if e>1e-6: bad+=1
    print(f"[BR] {nm}: mismatches {bad}, max abs {maxr:.3e}")
# print BR values around known regimes
for i in (0,1,100,240,480,720,1200,1440,1868):
    print(f"   {ym(i)}: BR={BR[i]:.4f} BM={BM[i]:.6f} GS={GS[i]}")
# min/max locations
i_min=BR.index(min(BR)); i_max=BR.index(max(BR))
print(f"   BR min {BR[i_min]:.4f} at {ym(i_min)}; BR max {BR[i_max]:.4f} at {ym(i_max)}")
i_minb=BM.index(min(BM)); i_maxb=BM.index(max(BM))
print(f"   BM min {BM[i_minb]:.4f} at {ym(i_minb)}; BM max {BM[i_maxb]:.4f} at {ym(i_maxb)}")

# ---- ExcessYield: X = 1/CAPE - EY, compare to GS variants
print("\n[EY] implied bond-like component X = 1/CAPE - EY:")
for i in (120, 1356, 1868, 1404, 200, 1600):
    if CAPE[i] is None or EY[i] is None: continue
    X = 1/CAPE[i] - EY[i]
    print(f"   {ym(i)}: X={X:.6f} GS={GS[i]} GS/100={GS[i]/100:.6f}")
# test X == GS/100 - 12mo avg inflation? and X == (GS/100 - infl10y)
import statistics
bad={nm:0 for nm in ('GS/100','GS/100 - infl12mo','GS/100 - infl10y','(1+GS/100)/(1+infl10y)-1')}
for i in range(n):
    if CAPE[i] is None or EY[i] is None: continue
    X = 1/CAPE[i]-EY[i]
    if i<120: continue
    infl12 = CPI[i]/CPI[i-12]-1
    infl10 = (CPI[i]/CPI[i-120])**(1/10)-1
    c={'GS/100': GS[i]/100,
       'GS/100 - infl12mo': GS[i]/100-infl12,
       'GS/100 - infl10y': GS[i]/100-infl10,
       '(1+GS/100)/(1+infl10y)-1': (1+GS[i]/100)/(1+infl10)-1}
    for nm,v in c.items():
        if abs(X-v)>1e-6: bad[nm]+=1
print("   candidate mismatches:", bad)
# OLS: EY = a + b*(1/CAPE) + c*(GS/100)
xs=[[1/CAPE[i], GS[i]/100, EY[i]] for i in range(n) if CAPE[i] and EY[i]]
# normal equations 3x3
import numpy as np
A=np.array([[x[0],x[1],1.0] for x in xs]); y=np.array([x[2] for x in xs])
coef,_,_,_=np.linalg.lstsq(A,y,rcond=None)
pred=A@coef
res=y-pred
print(f"[EY] OLS EY = {coef[0]:.6f}/CAPE + {coef[1]:.6f}*GS/100 + {coef[2]:.6f}: max resid {np.abs(res).max():.3e}")
