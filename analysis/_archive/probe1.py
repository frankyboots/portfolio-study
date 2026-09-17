import xlrd, json, math

wb = xlrd.open_workbook('ie_data.xls')
d = wb.sheet_by_name('Data')
nrows, ncols = d.nrows, d.ncols
print("sheet dims:", nrows, "x", ncols)

# Row lengths (how many cells each row actually has)
lens = {}
for r in range(8, nrows):
    vals = d.row_values(r)
    lens[len(vals)] = lens.get(len(vals), 0) + 1
print("row length histogram (data rows):", dict(sorted(lens.items())))

# Which rows are shorter than 22, and where the truncation starts
short = []
for r in range(8, nrows):
    vals = d.row_values(r)
    if len(vals) < 22:
        short.append((r, vals[0], len(vals)))
print("short rows count:", len(short))
print("short rows (first 15):", short[:15])
if short:
    print("short rows (last 15):", short[-15:])

# Find last non-empty cell column per short row to see the pattern
for r, dt, ln in short[:5] + short[-5:]:
    row = d.row_values(r)
    # find last non-empty
    last = max((i for i,v in enumerate(row) if str(v).strip()!=''), default=None)
    print(f"row {r} date={dt} len={ln} last_nonempty_col={last} tail={row[-3:]}")
