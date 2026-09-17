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
CPI=[r[4] for r in rows]; GS=[r[6] for r in rows]
BM=[r[17] for r in rows]; BR=[r[18] for r in rows]
dates=[r[0] for r in rows]
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

# --- implied duration k_i for BM by era
ks=[]
for i in range(1,n):
    if BM[i] is None or GS[i] is None or GS[i-1] is None: continue
    dgs=(GS[i]-GS[i-1])/100.0
    if abs(dgs)<0.5/100: continue   # skip near-zero moves
    rp=(BM[i]-1)-GS[i]/1200
    ks.append((ym(i), GS[i], dgs, -rp/dgs))
# era summary
import statistics
def era(yr0,yr1):
    sel=[k for y,g,dk,k in ks if yr0<=int(y[:4])<=yr1]
    if not sel: return None
    return f"n={len(sel)} med={statistics.median(sel):.2f} p10={sorted(sel)[len(sel)//10]:.2f} p90={sorted(sel)[9*len(sel)//10]:.2f}"
for yr0,yr1 in [(1871,1899),(1900,1929),(1930,1969),(1970,1979),(1980,1989),(1990,1999),(2000,2009),(2010,2026)]:
    print(f"BM implied duration {yr0}-{yr1}: {era(yr0,yr1)}")

# --- recover implied bond price level from BM with coupon = GS/1200
Pb=[1.0]
for i in range(1,n):
    if BM[i] is None or GS[i] is None: Pb.append(Pb[-1]); continue
    Pb.append(Pb[-1]*BM[i]-GS[i]/1200)
# compare shape with zero-coupon price Z=(1+GS/100)^-10
Z=[(1+GS[i]/100)**-10 for i in range(n)]
# scale Pb to match Z on mean
s = sum(z/p for z,p in zip(Z,Pb) if p>0)/n
corr_num = sum((z-s*p)*(z-sum(s*Pb)/n - (sum(z)/n)) for z,p in zip(Z,Pb))
varz = sum((z-sum(z)/n)**2 for z in Z); varp = sum((p-sum(Pb)/n)**2 for p in Pb)
print(f"\n[BM] recovered price level vs (1+GS/100)^-10: corr = {corr_num/math.sqrt(varz*varp):.4f}")
# also try Z30
Z3=[(1+GS[i]/100)**-30 for i in range(n)]
s3 = sum(z/p for z,p in zip(Z3,Pb) if p>0)/n
c3 = sum((z-s3*p)*(z-sum(Z3)/n-(sum(s3*Pb)/n)) for z,p in zip(Z3,Pb))
vz3=sum((z-sum(Z3)/n)**2 for z in Z3)
print(f"[BM] vs (1+GS/100)^-30: corr = {c3/math.sqrt(vz3*varp):.4f}")

# --- BR implied real monthly returns vs "proper 10y par bond" real return
# proper: r_nom = GS[i]/1200 - D*dgs ; r_real = (1+r_nom)/(1+infl)-1 ; compare to g=BR[i]/BR[i-1]
for D in (7.5, 8.0, 8.26):
    bad=0; tested=0; maxr=0; errs=[]
    for i in range(1,n):
        if None in (BR[i],BR[i-1],GS[i],GS[i-1]): continue
        dgs=(GS[i]-GS[i-1])/100.0
        rnom=GS[i]/1200 - D*dgs
        infl=CPI[i]/CPI[i-1]-1
        pred=(1+rnom)/(1+infl)
        g=BR[i]/BR[i-1]
        e=abs(g-pred)/pred
        errs.append((e, ym(i), g, pred))
        tested+=1; maxr=max(maxr,e)
        if e>1e-8: bad+=1
    errs.sort(reverse=True)
    print(f"[BR] proper-10y-par D={D}: mismatches {bad}/{tested}, maxrel {maxr:.3e}")
    print("   worst:", [(y, round(g,4), round(p,4)) for e,y,g,p in errs[:5]])
