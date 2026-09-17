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
BR=np.array([r[18] for r in rows])
dates=[r[0] for r in rows]
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

# distinct GS10 values per year
from collections import defaultdict
per_year=defaultdict(list)
for i,dt in enumerate(dates):
    per_year[int(dt//1)].append(GS[i])
# find when monthly fidelity starts
print("years with >12 distinct GS10 values (truly monthly):")
monthly_years=[]
for y in range(1871,2027):
    v=per_year.get(y,[])
    if len(set(round(x,6) for x in v))>6:
        monthly_years.append(y)
print("  ", monthly_years[0] if monthly_years else None, "->", monthly_years[-1] if monthly_years else None, f"({len(monthly_years)} years)")
# distinct values per year for a few sample years
for y in (1872, 1900, 1925, 1950, 1952, 1953, 1960, 1962, 1980, 2000, 2025):
    v=per_year.get(y,[])
    print(f"  {y}: {len(set(round(x,6) for x in v))} distinct GS10 values (n={len(v)})")

# BR implied duration
dgs=np.diff(GS)/100.0
infl=np.diff(CPI)/CPI[:-1]
g=BR[1:]/BR[:-1]
r_nom=(g-1)*(1+infl)+infl  # exact: (1+r_nom)=g*(1+infl)
r_nom=np.log(g*(1+infl))   # use log returns for cleanliness
coupon=GS[1:]/1200
c=r_nom-coupon
with np.errstate(divide='ignore', invalid='ignore'):
    k_br=-c/dgs
k_br=np.where(np.abs(dgs)>2e-4, k_br, np.nan)
yrs=np.array([int(dt//1) for dt in dates[1:]])
print("\nBR implied duration by era (median of |dgs|>2e-4):")
for yr0,yr1 in [(1871,1912),(1913,1945),(1946,1970),(1971,1989),(1990,2010),(2011,2026)]:
    sel=k_br[(yrs>=yr0)&(yrs<=yr1)&np.isfinite(k_br)]
    if len(sel): print(f"  {yr0}-{yr1}: med={np.median(sel):.2f} p10={np.percentile(sel,10):.2f} p90={np.percentile(sel,90):.2f} n={len(sel)}")

# sanity: what's BR's annualized real return per era
print("\nBR growth per era:")
def idx_of(y,m):
    return (y-1871)*12+(m-1)
for (y0,m0),(y1,m1) in [((1871,1),(1913,1)),((1913,1),(1946,1)),((1946,1),(1971,1)),((1971,1),(1991,1)),((1991,1),(2011,1)),((2011,1),(2026,9))]:
    a,b=idx_of(y0,m0),idx_of(y1,m1)
    yrs=(b-a)/12
    print(f"  {y0}-{y1}: {BR[b]/BR[a]:.3f}x  ({(BR[b]/BR[a])**(1/yrs)-1:.2%}/yr real)")
