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
CPI=np.array([r[4] for r in rows]); GS=np.array([r[6] for r in rows])
BM=np.array([r[17] if r[17] is not None else np.nan for r in rows])
BR=np.array([r[18] for r in rows])
dates=[r[0] for r in rows]
def idx(y,m): return (y-1871)*12+(m-1)
def ym(i):
    dt=dates[i]; return f"{int(dt//1)}.{int(round((dt-int(dt))*100)):02d}"

# Show 1952.09-1953.06
print("1952.09 - 1953.06:")
for i in range(idx(1952,9), idx(1953,6)):
    dgs = GS[i]-GS[i-1]
    k = -(BM[i]-1-GS[i]/1200)/((dgs)/100) if abs(dgs)>1e-4 else float('nan')
    print(f"  {ym(i)}: GS {GS[i-1]:.4f} -> {GS[i]:.4f} (d={dgs:+.4f}) BM={BM[i]:.6f} (r={(BM[i]-1)*100:+.4f}%) implied_k={k:.2f}")

# hypothesis: BM uses PRIOR-month GS for coupon?  k' with coupon=GS[i-1]/1200
print("\n1953-1955 with coupon=prev GS:")
for i in range(idx(1953,1), idx(1955,1)):
    dgs = GS[i]-GS[i-1]
    k = -(BM[i]-1-GS[i-1]/1200)/((dgs)/100) if abs(dgs)>1e-4 else float('nan')
    print(f"  {ym(i)}: GS {GS[i-1]:.4f} -> {GS[i]:.4f} (d={dgs:+.4f}) BM={BM[i]:.6f} k_prevcoupon={k:.2f}")
