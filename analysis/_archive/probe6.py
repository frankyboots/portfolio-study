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
GS=[r[6] for r in rows]; CPI=[r[4] for r in rows]
CAPE=[r[12] for r in rows]; EY=[r[16] for r in rows]
BM=[r[17] for r in rows]; BR=[r[18] for r in rows]
dates=[r[0] for r in rows]
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

# Clean re-print of tail columns for first 3 months, labeled
for i in range(3):
    print(ym(i), "| col16(EY)=", rows[i][16], "| col17(BM)=", rows[i][17], "| col18(BR)=", rows[i][18],
          "| col19=", rows[i][19], "| col20=", rows[i][20], "| col21=", rows[i][21])

# BM: implied price component
print("\n[BM] implied price component k_i = (BM-1-GS/1200)/(-dGS/100) vs GS level:")
ks=[]
for i in range(1,n):
    if BM[i] is None: continue
    dgs=(GS[i]-GS[i-1])/100.0
    if abs(dgs)<1e-6: continue
    rp=(BM[i]-1)-GS[i]/1200.0
    k=-rp/dgs
    ks.append((GS[i], k, ym(i)))
ks_sorted = sorted(ks)
# show k by GS decile
import statistics
buckets={}
for g,k,y in ks:
    b=round(g/5)*5
    buckets.setdefault(b,[]).append(k)
for b in sorted(buckets):
    vals=buckets[b]
    print(f"  GS~{b}: n={len(vals)} median k={statistics.median(vals):.3f} min={min(vals):.3f} max={max(vals):.3f}")
# print some raw k values
print("  sample k:", [(y,round(g,2),round(k,3)) for g,k,y in ks[::400]])

# BR: implied real monthly return vs BM
print("\n[BR] g=BR[i]/BR[i-1] vs BM/(1+infl):")
bad=0; tot=0; diffs=[]
for i in range(1,n):
    if None in (BR[i],BR[i-1],BM[i]): continue
    tot+=1
    g=BR[i]/BR[i-1]
    e=(1+GS[i]/1200)/(CPI[i]/CPI[i-1]) - 1
    bm_g=BM[i]/(CPI[i]/CPI[i-1])-1
    diffs.append((g-bm_g, ym(i)))
    if abs(g-bm_g)>1e-9: bad+=1
print(f"  g vs BM/(1+infl)-1: mismatches {bad}/{tot}")
# maybe BR is just BR[i]=BR[i-1]*(1+GS/1200-infl)
bad=0
for i in range(1,n):
    if None in (BR[i],BR[i-1]): continue
    infl=CPI[i]/CPI[i-1]-1
    exp=BR[i-1]*(1+GS[i]/1200-infl)
    if abs(BR[i]-exp)>1e-9*BR[i]: bad+=1
print(f"  BR[i]=BR[i-1]*(1+GS/1200-infl): mismatches {bad}")
# maybe real return = (1+GS/1200)/(1+infl) -1
bad=0
for i in range(1,n):
    if None in (BR[i],BR[i-1]): continue
    infl=CPI[i]/CPI[i-1]-1
    exp=BR[i-1]*(1+GS[i]/1200)/(1+infl)
    if abs(BR[i]-exp)>1e-9*BR[i]: bad+=1
print(f"  BR[i]=BR[i-1]*(1+GS/1200)/(1+infl): mismatches {bad}")

# EY implied X
print("\n[EY] X=1/CAPE-EY vs candidates at sample dates:")
for i in (240, 480, 1200, 1440, 1600, 1800, 1868):
    if CAPE[i] is None or EY[i] is None: continue
    X=1/CAPE[i]-EY[i]
    infl12=CPI[i]/CPI[i-12]-1
    infl10=(CPI[i]/CPI[i-120])**(1/10)-1
    print(f"  {ym(i)}: X={X:.5f} | GS/100={GS[i]/100:.5f} | GS/100-infl12={GS[i]/100-infl12:.5f} | GS/100-infl10={GS[i]/100-infl10:.5f}")
