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

rows = [[num(v) for v in d.row_values(r)] for r in range(8, nrows-1)]  # data only
n = len(rows)
print("n =", n)

P  = [r[1] for r in rows]; D = [r[2] for r in rows]; E = [r[3] for r in rows]
CPI = [r[4] for r in rows]; F = [r[5] for r in rows]; GS = [r[6] for r in rows]
RP = [r[7] for r in rows]; RD = [r[8] for r in rows]; RT = [r[9] for r in rows]
RE = [r[10] for r in rows]; RTE = [r[11] for r in rows]
CAPE = [r[12] for r in rows]; TRCAPE = [r[14] for r in rows]
EY = [r[16] for r in rows]; BM = [r[17] for r in rows]; BR = [r[18] for r in rows]
A10s = [r[19] for r in rows]; A10b = [r[20] for r in rows]; A10ex = [r[21] for r in rows]
dates = [r[0] for r in rows]
def ym(dt):
    yr = int(math.floor(dt+1e-9)); mo = int(round((dt-yr)*100))
    return f"{yr}.{mo:02d}"

def check(name, got, exp, tol=1e-6):
    ok = got is not None and exp is not None and abs(got-exp) <= tol*max(1,abs(exp))
    return ok, got, exp

# --- 1. Deflator constant K for real columns
Ks = [RP[i]*CPI[i]/P[i] for i in range(n) if P[i]]
print("\n[1] K = RealP*CPI/P : min %.6f max %.6f  (spread %.2e)" % (min(Ks), max(Ks), max(Ks)-min(Ks)))
Ks_d = [RD[i]*CPI[i]/D[i] for i in range(n) if D[i]]
Ks_e = [RE[i]*CPI[i]/E[i] for i in range(n) if E[i]]
print("    K(D): min %.6f max %.6f | K(E): min %.6f max %.6f" % (min(Ks_d),max(Ks_d),min(Ks_e),max(Ks_e)))
print("    last CPI:", CPI[-1], " last P:", P[-1])

# --- 2. RealTR recursion: RT[i] = RT[i-1]*(RP[i] + RD[i]/12)/RP[i-1]
bad = 0; maxerr = 0
for i in range(1, n):
    if None in (RT[i], RT[i-1], RP[i], RP[i-1]): continue
    if RD[i] is None: RDv = 0.0
    else: RDv = RD[i]
    exp = RT[i-1]*(RP[i] + RDv/12)/RP[i-1]
    err = abs(RT[i]-exp)/exp
    maxerr = max(maxerr, err)
    if err > 1e-8: bad += 1
print("\n[2] RealTR recursion violations (>1e-8 rel):", bad, " max rel err: %.2e" % maxerr)
# also test with RD/12 omitted entirely
bad2 = 0; maxerr2 = 0
for i in range(1, n):
    if None in (RT[i], RT[i-1], RP[i], RP[i-1]): continue
    exp = RT[i-1]*RP[i]/RP[i-1]
    err = abs(RT[i]-exp)/exp
    maxerr2 = max(maxerr2, err)
    if err > 1e-8: bad2 += 1
print("    (price-only variant) violations:", bad2, " max rel err: %.2e" % maxerr2)

# --- 3. RealTRE = RealE * (RealTR/RealP)
bad = 0; maxerr=0
for i in range(n):
    if None in (RTE[i], RE[i], RT[i], RP[i]): continue
    exp = RE[i]*RT[i]/RP[i]
    err = abs(RTE[i]-exp)/exp
    maxerr = max(maxerr, err)
    if err > 1e-8: bad += 1
print("\n[3] RealTRE = RealE*(RealTR/RealP) violations:", bad, " max rel err: %.2e" % maxerr)

# --- 4. CAPE = P / mean(last 120 RealE)
bad=0; maxerr=0; tested=0
for i in range(n):
    if CAPE[i] is None: continue
    window = [RE[j] for j in range(i-119, i+1)]
    if None in window: continue
    tested+=1
    exp = P[i]/(sum(window)/120)
    err = abs(CAPE[i]-exp)/exp
    maxerr=max(maxerr,err)
    if err>1e-8: bad+=1
print(f"\n[4] CAPE = P/mean120(RealE): tested {tested}, violations {bad}, max rel err %.2e" % maxerr)
# window ending at i-1?
bad1=0; maxerr1=0; tested1=0
for i in range(n):
    if CAPE[i] is None: continue
    window = [RE[j] for j in range(i-120, i)]
    if None in window: continue
    tested1+=1
    exp = P[i]/(sum(window)/120)
    err = abs(CAPE[i]-exp)/exp
    maxerr1=max(maxerr1,err)
    if err>1e-8: bad1+=1
print(f"    (window shifted back 1: mean of i-120..i-1) tested {tested1}, violations {bad1}, max rel err %.2e" % maxerr1)

# --- 5. TRCAPE = RealTR / mean120(RealTRE)
bad=0; maxerr=0; tested=0
for i in range(n):
    if TRCAPE[i] is None: continue
    window = [RTE[j] for j in range(i-119, i+1)]
    if None in window: continue
    tested+=1
    exp = RT[i]/(sum(window)/120)
    err = abs(TRCAPE[i]-exp)/exp
    maxerr=max(maxerr,err)
    if err>1e-8: bad+=1
print(f"\n[5] TRCAPE = RealTR/mean120(RealTRE): tested {tested}, violations {bad}, max rel err %.2e" % maxerr)
bad1=0; maxerr1=0; tested1=0
for i in range(n):
    if TRCAPE[i] is None: continue
    window = [RTE[j] for j in range(i-120, i)]
    if None in window: continue
    tested1+=1
    exp = RT[i]/(sum(window)/120)
    err = abs(TRCAPE[i]-exp)/exp
    maxerr1=max(maxerr1,err)
    if err>1e-8: bad1+=1
print(f"    (window i-120..i-1) tested {tested1}, violations {bad1}, max rel err %.2e" % maxerr1)

# --- 6. ExcessYield candidates
cands = {}
for i in range(n):
    if CAPE[i] is None or GS[i] is None or EY[i] is None: continue
    cands[i] = (EY[i], 1/CAPE[i]-GS[i]/100, 1/CAPE[i]-GS[i-12]/100 if i>=12 else None,
                1/CAPE[i]-(GS[i]/100 - (CPI[i]/CPI[i-12]-1)), 1/TRCAPE[i]-GS[i]/100)
tested = len(cands)
for k,name in [(1,'1/CAPE - GS10'),(2,'1/CAPE - GS10(12mo ago)'),(3,'1/CAPE - realGS10(cpi yoy)'),(4,'1/TRCAPE - GS10')]:
    errs=[abs(v[0]-v[k]) for v in cands.values() if v[k] is not None]
    if errs:
        ok = sum(1 for e in errs if e<1e-6)
        print(f"\n[6] {name}: tested {len(errs)}, exact {ok}, max abs err {max(errs):.2e}")
        if errs and max(errs)>1e-6:
            i0 = max(cands, key=lambda i: abs(cands[i][0]-cands[i][k]))
            print("   worst at", ym(dates[i0]), [round(x,6) if x is not None else None for x in cands[i0]])

# --- 7. Bond columns
# find the 59.45 outlier
outl = [(i, BR[i], ym(dates[i])) for i in range(n) if BR[i] is not None and BR[i] > 1.5]
print("\n[7] BndR outliers (>1.5):", outl[:10])
# test BndR = BndM / (1+inflation)
bad=0; maxerr=0; tested=0
for i in range(1,n):
    if None in (BR[i], BM[i], CPI[i], CPI[i-1]): continue
    if BR[i] > 1.5: continue
    infl = CPI[i]/CPI[i-1]-1
    exp = BM[i]/(1+infl)
    err = abs(BR[i]-exp)/exp
    maxerr=max(maxerr,err)
    if err>1e-8: bad+=1
    tested+=1
print(f"    BndR = BndM/(1+CPIinfl): tested {tested}, violations {bad}, max rel err {maxerr:.2e}")
# test BndM = 1+GS/12
bad=0; maxerr=0; tested=0
for i in range(n):
    if BM[i] is None or GS[i] is None: continue
    exp = 1+GS[i]/12/100
    err = abs(BM[i]-exp)/exp
    maxerr=max(maxerr,err)
    if err>1e-8: bad+=1
    tested+=1
print(f"    BndM = 1+GS10/12: tested {tested}, violations {bad}, max rel err {maxerr:.2e}")
# maybe BndM uses prior-month GS10 or has a duration term: (1+GS/12)*(1+ (GS[i-1]-GS[i])*dur/12/100)
best=None
for dur in (7.5, 7.6, 8.0, 8.2, 8.6, 9.0, 9.3, 9.5):
    bad=0; maxerr=0
    for i in range(1,n):
        if None in (BM[i],GS[i],GS[i-1]): continue
        exp = (1+GS[i]/12/100)*(1+(GS[i-1]-GS[i])*dur/12/100)
        err = abs(BM[i]-exp)/exp
        if err>1e-8: bad+=1
        maxerr=max(maxerr,err)
    print(f"    BndM = (1+GS/12)*(1+dur*dGS/12), dur={dur}: violations {bad}, maxrel {maxerr:.2e}")
    if best is None or bad < best[1]: best=(dur,bad)
print("    best duration model:", best)
