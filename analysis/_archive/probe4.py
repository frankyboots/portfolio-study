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

rows = [[num(v) for v in d.row_values(r)] for r in range(8, nrows-1)]
n = len(rows)
P=[r[1] for r in rows]; D=[r[2] for r in rows]; E=[r[3] for r in rows]
CPI=[r[4] for r in rows]; GS=[r[6] for r in rows]; RP=[r[7] for r in rows]
RD=[r[8] for r in rows]; RT=[r[9] for r in rows]; RE=[r[10] for r in rows]
RTE=[r[11] for r in rows]; CAPE=[r[12] for r in rows]; TRC=[r[14] for r in rows]
EY=[r[16] for r in rows]; BM=[r[17] for r in rows]; BR=[r[18] for r in rows]
A10s=[r[19] for r in rows]; A10b=[r[20] for r in rows]; A10ex=[r[21] for r in rows]
dates=[r[0] for r in rows]
def ym(i): 
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

def relerr(a,b): return abs(a-b)/abs(b) if b else None

# --- CAPE variants with window i-120..i-1 (matching TRCAPE window)
w = lambda arr, i: [arr[j] for j in range(i-120, i)]
for nm, price, earn in [("P/mean(RealE)", P, RE), ("RealP/mean(RealE)", RP, RE), ("RealP/mean120(RTE)", RP, RTE)]:
    bad=0; maxe=0
    for i in range(n):
        if CAPE[i] is None: continue
        win = w(earn, i)
        if None in win: continue
        exp = price[i]/(sum(win)/120)
        e = relerr(CAPE[i], exp); maxe=max(maxe,e)
        if e>1e-8: bad+=1
    print(f"[CAPE] {nm}: violations {bad}, maxrel {maxe:.2e}")

# --- A10 forward test
for nm, arr in [("A10s (RealTR fwd 120)", RT)]:
    ok=0; bad=0
    for i in range(0, 1749):
        if A10s[i] is None: continue
        exp = (RT[i+120]/RT[i])**(1/10)-1
        e = relerr(A10s[i], exp)
        if e < 1e-6: ok+=1
        else: bad+=1
    print(f"[A10] {nm}: ok {ok}, bad {bad}")
# A10b forward from BR cumulative index
ok=0; bad=0
for i in range(1749):
    if A10b[i] is None: continue
    exp = (BR[i+120]/BR[i])**(1/10)-1
    e = relerr(A10b[i], exp)
    if e is not None and e < 1e-6: ok+=1
    else: bad+=1
print(f"[A10] A10b = (BR[i+120]/BR[i])^(1/10)-1: ok {ok}, bad {bad}")
# A10ex = A10s - A10b?
bad=0
for i in range(n):
    if None in (A10ex[i],A10s[i],A10b[i]): continue
    if abs(A10ex[i]-(A10s[i]-A10b[i]))>1e-12: bad+=1
print(f"[A10] A10ex = A10s-A10b: violations {bad}")
# where do A10s columns stop/start
a10idx = [i for i in range(n) if A10s[i] is not None]
print("[A10] filled rows:", a10idx[0], "to", a10idx[-1], "->", ym(a10idx[0]), "to", ym(a10idx[-1]))

# --- BR cumulative: BR[i] = BR[i-1]*BM[i]/(1+infl)
bad=0; maxe=0
for i in range(1,n):
    if None in (BR[i],BR[i-1],BM[i]): continue
    infl = CPI[i]/CPI[i-1]-1
    exp = BR[i-1]*BM[i]/(1+infl)
    e = relerr(BR[i],exp); maxe=max(maxe,e)
    if e>1e-8: bad+=1
print(f"[BR] cumulative test BR[i]=BR[i-1]*BM[i]/(1+infl): violations {bad}, maxrel {maxe:.2e}")
# also without inflation deflation
bad=0; maxe=0
for i in range(1,n):
    if None in (BR[i],BR[i-1],BM[i]): continue
    exp = BR[i-1]*BM[i]
    e = relerr(BR[i],exp); maxe=max(maxe,e)
    if e>1e-8: bad+=1
print(f"[BR] BR[i]=BR[i-1]*BM[i] (nominal): violations {bad}, maxrel {maxe:.2e}")

# --- BM models: test with exact 10yr zero-coupon + coupon
models = {}
# model A: coupon y/12 + price change of (1+y/100)^-10
ok=0
for i in range(1,n):
    if None in (BM[i],GS[i],GS[i-1]): continue
    y,yp = GS[i]/100, GS[i-1]/100
    pa = (1+y)**-10; pp=(1+yp)**-10
    exp = (1+y/12)*(pa/pp)
    if relerr(BM[i],exp) is not None and relerr(BM[i],exp)<1e-8: ok+=1
print(f"[BM] zero-coupon 10y model: matches {ok}/{n-1}")
# model B: monthly compounding of bond price level: BM = exp(y/12)?? 
ok=0
for i in range(n):
    if None in (BM[i],GS[i]): continue
    exp = math.exp(GS[i]/100/12)
    if relerr(BM[i],exp)<1e-8: ok+=1
print(f"[BM] exp(GS/12/100): matches {ok}/{n}")
# print first 30 BM vs GS to eyeball
print("  first 24 months BM & GS10 & dGS:")
for i in range(0,24):
    dgs = (GS[i]-GS[i-1]) if i>0 else None
    print(f"   {ym(i)}: BM={BM[i]:.6f} GS={GS[i]} dGS={dgs if dgs is None else round(dgs,4)}")
