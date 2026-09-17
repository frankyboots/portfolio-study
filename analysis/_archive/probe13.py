import xlrd, math
import numpy as np
wb = xlrd.open_workbook('ie_data.xls', formatting_info=False)
print("file props: author=%r last_saved_by=%r created=%r saved=%r printed=%r" % (
    wb.author, wb.last_saved_by, wb.create_time, wb.last_saved_time, wb.last_printed))
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
BR=np.array([r[18] for r in rows])
dates=[r[0] for r in rows]
def idx(y,m): return (y-1871)*12+(m-1)
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"
def dt_of(i): return ym(i)

# BR vs BM consistency (log growth corr)
lg=np.log(BR[1:]/BR[:-1]); lb=np.log(BM[1:])
print(f"\n[BR/BM] corr(log growth) = {np.corrcoef(lg,lb)[0,1]:.6f}")

# D / E: change frequency
def change_pattern(arr, name, upto=None):
    nn = ~np.isnan(arr)
    last = upto if upto else n
    chg = 0; runs=[]; rlen=1
    for i in range(1,last):
        if nn[i] and nn[i-1]:
            if arr[i]!=arr[i-1]:
                chg+=1; runs.append(rlen); rlen=1
            else: rlen+=1
    runs.append(rlen)
    import statistics
    print(f"[{name}] changes={chg}/{last-1}, run lengths: med={int(statistics.median(runs))} max={max(runs)}")
change_pattern(D,'D')
change_pattern(E,'E')
# where do D/E update in recent years? list change months 2024-2026
for nm,arr in [('D',D),('E',E)]:
    chgs=[dt_of(i) for i in range(idx(2024,1), n) if not np.isnan(arr[i]) and not np.isnan(arr[i-1]) and arr[i]!=arr[i-1]]
    print(f"  {nm} update months 2024+ : {chgs}")

# P: big month-to-month jumps (reconstitutions / crash)
pr = P[1:]/P[:-1]
jumps = [(dt_of(i+1), pr[i]) for i in range(len(pr)) if abs(pr[i]-1)>0.15]
print(f"\n[P] months with |move|>15%: {jumps}")
# 1957 context
for i in range(idx(1957,6), idx(1957,11)):
    print(f"  {dt_of(i)}: P={P[i]}  ratio={P[i]/P[i-1]:.4f}")
# 1926 context (S&P history start)
for i in range(idx(1926,2), idx(1926,5)):
    print(f"  {dt_of(i)}: P={P[i]} ratio={P[i]/P[i-1]:.4f}")
# 1929.09 crash
for i in range(idx(1929,9), idx(1929,11)):
    print(f"  {dt_of(i)}: P={P[i]} ratio={P[i]/P[i-1]:.4f} D={D[i]} E={E[i]}")

# CPI: pre-1913 wobble vs post-1913; flat recent months
for i in (idx(1912,12), idx(1913,1), idx(1913,2)):
    print(f"  CPI {dt_of(i)}: {CPI[i]}")
flat=[(dt_of(i), CPI[i]) for i in range(idx(2025,9), n) ]
print("  CPI 2025.09-2026.09:", [(a, round(b,4)) for a,b in flat])

# GS10 extremes
i_min=GS.argmin(); i_max=GS.argmax()
print(f"\n[GS10] min {GS[i_min]:.2f}% at {dt_of(i_min)}; max {GS[i_max]:.2f}% at {dt_of(i_max)}")
# CAPE extremes + NA range
ca=[i for i in range(n) if not np.isnan(CAPE[i])]
print(f"[CAPE] first {dt_of(ca[0])}, last {dt_of(ca[-1])}, n_NA={sum(1 for i in range(n) if np.isnan(CAPE[i]))}")
cmin=CAPE[ca].argmin(); cmax=CAPE[ca].argmax()
print(f"  min {CAPE[ca[cmin]]:.2f} at {dt_of(ca[cmin])}; max {CAPE[ca[cmax]]:.2f} at {dt_of(ca[cmax])}")

# CAPE at tail with missing earnings: mean of available vs /120
i = n-1
win=[RE[j] for j in range(i-119,i+1)]
avail=[x for x in win if not np.isnan(x)]
print(f"\n[CAPE tail] {dt_of(i)}: stored={CAPE[i]:.4f}; P/mean(avail {len(avail)})={P[i]/(sum(avail)/len(avail)):.4f}; P/mean120(nan=0)={P[i]/(sum(avail)/120):.4f}")

# Fraction column check
F=np.array([r[5] for r in rows])
bad_f = [dt_of(i) for i in range(n) if abs(F[i] - (dates[i]-int(dates[i])-0.5/12) ) > 1e-4 and abs(F[i] - (dates[i]-int(dates[i]) - 0.5/12))>1e-4]
ok = sum(1 for i in range(n) if abs(F[i] - (int(round((dates[i]-int(dates[i]))*100))-0.5)/12 - 0) < 1e-9 or abs(F[i] - ((int(round((dates[i]-int(dates[i]))*100)))-0.5)/12) < 1e-9)
print(f"\n[Fraction] mid-month formula matches: {ok}/{n}")

# BM/BR min/max locations
print(f"\n[BM] min {BM.min():.4f} @ {dt_of(BM.argmin())}; max {BM.max():.4f} @ {dt_of(BM.argmax())}; n missing={np.isnan(BM).sum()}")
print(f"[BR] min {BR.min():.4f} @ {dt_of(BR.argmin())}; max {BR.max():.4f} @ {dt_of(BR.argmax())}")
# D, E min locations
dmin=D.nanmin(); emin=E.nanmin()
print(f"[D] min {dmin} @ {dt_of(np.nanargmin(D))}; [E] min {emin} @ {dt_of(np.nanargmin(E))}")
