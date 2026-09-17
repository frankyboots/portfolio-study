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
CAPE=[r[12] for r in rows]; EY=[r[16] for r in rows]
BM=[r[17] for r in rows]; BR=[r[18] for r in rows]
dates=[r[0] for r in rows]
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

# EY full verification
bad=0; tested=0; maxr=0
for i in range(n):
    if CAPE[i] is None or EY[i] is None or i<120: continue
    tested+=1
    infl10=(CPI[i]/CPI[i-120])**(1/10)-1
    exp=1/CAPE[i]-(GS[i]/100-infl10)
    r=abs(EY[i]-exp); maxr=max(maxr,r)
    if r>1e-9: bad+=1
print(f"[EY] full test: {tested} rows, mismatches {bad}, max abs {maxr:.3e}")
# what about first rows where EY is None?
print("    EY None where CAPE present, i<120:", sum(1 for i in range(n) if CAPE[i] is not None and EY[i] is None and i<120))

# BR: where are the big divergences?
divs=[]
for i in range(1,n):
    if None in (BR[i],BR[i-1],BM[i]): continue
    infl=CPI[i]/CPI[i-1]-1
    g=BR[i]/BR[i-1]
    pred=BM[i]/(1+infl)
    divs.append((abs(g-pred), ym(i), g, pred, infl, GS[i]))
divs.sort(reverse=True)
print("\n[BR] top 15 divergences g vs BM/(1+infl):")
for dd in divs[:15]:
    print(f"  {dd[1]}: g={dd[2]:.5f} pred={dd[3]:.5f} infl={dd[4]:.5f} GS={dd[5]}")

# try alternative inflation defs for deflation
for nm, f in {
  'infl 12mo-ann (per month)': lambda i: (CPI[i]/CPI[i-12])**(1/12)-1,
  'infl 12mo-ann full (1+infl12)': lambda i: CPI[i]/CPI[i-1]-1,
  'mean of 12 monthly infs': lambda i: sum(CPI[j]/CPI[j-1]-1 for j in range(i-11,i+1))/12,
}.items():
    bad=0; tested=0; maxr=0
    for i in range(120,n):
        if None in (BR[i],BR[i-1],BM[i]): continue
        tested+=1
        infl=f(i)
        pred=BR[i-1]*BM[i]/(1+infl)
        r=abs(BR[i]-pred)/BR[i]
        maxr=max(maxr,r)
        if r>1e-8: bad+=1
    print(f"  BR=BRprev*BM/(1+{nm}): mismatches {bad}/{tested}, maxrel {maxr:.3e}")

# What if BR uses nominal = (1+GS/1200)*(price from GS) i.e. BM, but deflates by annual avg CPI?
# try: BR[i] = BR[i-1] * BM[i] * CPI[i-1]/CPI[i]
bad=0
for i in range(1,n):
    if None in (BR[i],BR[i-1],BM[i]): continue
    pred=BR[i-1]*BM[i]*CPI[i-1]/CPI[i]
    if abs(BR[i]-pred)>1e-9*BR[i]: bad+=1
print(f"  BR=BRprev*BM*CPI[i-1]/CPI[i]: mismatches {bad}")
