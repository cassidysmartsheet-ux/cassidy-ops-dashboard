"""Transform Operations Schedule + Silva Billing Queue raw data into ops dashboard data.json.

Usage:  python3 transform.py os_raw.json silva_raw.json > data.json
"""
import json, re, sys
from datetime import datetime, date, timezone, timedelta
from collections import defaultdict, Counter

OS = {
    "JOB_NUM": 7358000912879492, "COMPANY_NAME": 171009385385860,
    "CLIENT": 1728501378666372, "ADDRESS": 6232101006036868,
    "JOB_CITY": 3980301192351620, "ACCOUNT_REP": 321126495113092,
    "PM": 5252548828368772, "PROJECT_PRICE_EST": 2572926308798340,
    "PRICE": 6320343843819396, "CONTRACT_PRICE": 8367024680685444,
    "PHASE": 4824726122483588, "ASSIGNED_CREW": 8202425843011460,
    "ASPHALT_TONS": 2009976355377028, "SQUARE_YARDS": 4674609012756356,
    "START": 8765375796432772, "END": 180389006757764,
    "STATUS": 4683988634128260, "VARIANCE": 3698826215640964,
}
SV = {
    "JOB_NUM": 3914687386521476, "COMPANY_NAME": 8418287013891972,
    "CLIENT": 1099937619414916, "END_DATE": 6782213711761284,
    "CONTRACT_PRICE": 8981236967313284, "BILLING_STATUS": 7908113618603908,
    "DATE_INVOICED": 5093363851497348, "BALANCE_DUE": 6219263758339972,
}

CREWS = ["Milling", "Paving", "Crackfill", "Hand", "Reclaim/Grading", "Pulverizing"]
SUB_CREW = "Subcontractor"
HOLDS = {"Weather Hold", "Material Hold"}
ACTIVE_STATUSES = {"Scheduled", "In Progress"}
COMPLETE = "Complete"
CAPACITY_PER_CREW_WEEK = 5

def cv(r, cid):
    for c in (r.get("cells") or []):
        if int(c.get("columnId", 0)) == int(cid):
            v = c.get("value")
            return v if v is not None else c.get("displayValue")
    return None

def cd(r, cid):
    for c in (r.get("cells") or []):
        if int(c.get("columnId", 0)) == int(cid):
            return c.get("displayValue") or c.get("value")
    return None

def name_of(c):
    if isinstance(c, dict): return c.get("name") or c.get("email") or ""
    return c or ""

def parse_date(s):
    if not s: return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(s))
    if not m: return None
    try: return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError: return None

def to_number(v):
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError):
        try: return float(str(v).replace("$", "").replace(",", "").strip())
        except ValueError: return None

def money_round(x): return int(round(x)) if x else 0
def week_start(d): return d - timedelta(days=d.weekday())

def working_days_between(start, end):
    if start is None or end is None or end < start: return 0
    d = start; n = 0
    while d <= end:
        if d.weekday() < 5: n += 1
        d += timedelta(days=1)
    return n

def days_overlap_in_window(start, end, win_start, win_end):
    if not start or not end: return 0
    s = max(start, win_start); e = min(end, win_end)
    if e < s: return 0
    return working_days_between(s, e)

# ---------- Load ----------
os_raw = json.load(open(sys.argv[1]))
sv_raw = json.load(open(sys.argv[2])) if len(sys.argv) > 2 else None

today = date.today()
mtd_start = today.replace(day=1)
prior_mtd_start = (mtd_start.replace(year=mtd_start.year - 1, month=12)
                   if mtd_start.month == 1
                   else mtd_start.replace(month=mtd_start.month - 1))
prior_mtd_end = mtd_start - timedelta(days=1)
this_week_start = week_start(today)
this_week_end = this_week_start + timedelta(days=6)

# ---------- Flatten Ops Schedule ----------
ops_rows = []
for r in os_raw.get("rows", []):
    status = cv(r, OS["STATUS"]) or ""
    start = parse_date(cv(r, OS["START"]))
    end = parse_date(cv(r, OS["END"]))
    crew_label = cv(r, OS["ASSIGNED_CREW"]) or cv(r, OS["PHASE"]) or ""
    if isinstance(crew_label, dict): crew_label = crew_label.get("value") or ""
    crew_label = str(crew_label).strip()
    tons = to_number(cv(r, OS["ASPHALT_TONS"])) or 0
    sy = to_number(cv(r, OS["SQUARE_YARDS"])) or 0
    price = (to_number(cv(r, OS["CONTRACT_PRICE"])) or to_number(cv(r, OS["PRICE"]))
             or to_number(cv(r, OS["PROJECT_PRICE_EST"])) or 0)
    variance = to_number(cv(r, OS["VARIANCE"]))
    ops_rows.append({
        "job_num": str(cd(r, OS["JOB_NUM"]) or ""),
        "company": cv(r, OS["COMPANY_NAME"]) or cv(r, OS["CLIENT"]) or "",
        "address": cv(r, OS["ADDRESS"]) or "",
        "city": cv(r, OS["JOB_CITY"]) or "",
        "pm": cv(r, OS["PM"]) or "",
        "account_rep": name_of(cv(r, OS["ACCOUNT_REP"])),
        "crew": crew_label,
        "phase": cv(r, OS["PHASE"]) or "",
        "start": start, "end": end, "status": status,
        "tons": tons, "sy": sy, "price": price, "variance": variance,
    })

# ---------- Crew util this week ----------
util_this = defaultdict(lambda: {"scheduled": 0, "weather": 0, "material": 0})
for r in ops_rows:
    crew = r["crew"] if r["crew"] in CREWS else (SUB_CREW if "Subcontractor" in (r["crew"] or "") or r["crew"] == SUB_CREW else None)
    if not crew: continue
    days = days_overlap_in_window(r["start"], r["end"], this_week_start, this_week_end)
    if days <= 0: continue
    if r["status"] == "Weather Hold": util_this[crew]["weather"] += days
    elif r["status"] == "Material Hold": util_this[crew]["material"] += days
    elif r["status"] in ACTIVE_STATUSES | {COMPLETE}: util_this[crew]["scheduled"] += days

total_scheduled_this_week = sum(u["scheduled"] for u in util_this.values())
total_capacity_this_week = CAPACITY_PER_CREW_WEEK * len(CREWS)
util_pct = round((total_scheduled_this_week / total_capacity_this_week) * 100, 1) if total_capacity_this_week else None

# ---------- Tons / SY MTD vs prior ----------
def tons_in(s, e): return sum(r["tons"] for r in ops_rows if r["status"] == COMPLETE and r["end"] and s <= r["end"] <= e)
def sy_in(s, e): return sum(r["sy"] for r in ops_rows if r["status"] == COMPLETE and r["end"] and s <= r["end"] <= e)
tons_mtd = tons_in(mtd_start, today); tons_prior = tons_in(prior_mtd_start, prior_mtd_end)
sy_mtd = sy_in(mtd_start, today); sy_prior = sy_in(prior_mtd_start, prior_mtd_end)

# ---------- 7-day slip + holds MTD ----------
seven_back = today - timedelta(days=7)
sched_7d = sum(1 for r in ops_rows if r["status"] in ACTIVE_STATUSES and r["start"] and seven_back <= r["start"] <= today)
done_7d = sum(1 for r in ops_rows if r["status"] == COMPLETE and r["end"] and seven_back <= r["end"] <= today)
weather_mtd = sum(1 for r in ops_rows if r["status"] == "Weather Hold" and r["start"] and r["start"] >= mtd_start)
material_mtd = sum(1 for r in ops_rows if r["status"] == "Material Hold" and r["start"] and r["start"] >= mtd_start)
holds_mtd = weather_mtd + material_mtd

# ---------- Revenue in progress ----------
billed_jobs = set()
if sv_raw:
    for r in sv_raw.get("rows", []):
        jn = cd(r, SV["JOB_NUM"])
        if jn: billed_jobs.add(str(jn).strip())
rev_in_progress = sum(r["price"] for r in ops_rows
                      if r["status"] in ACTIVE_STATUSES and r["job_num"] not in billed_jobs and r["price"])

# ---------- Crew util grid (this week + next 2) ----------
weeks = [{"start": this_week_start + timedelta(weeks=i), "end": this_week_start + timedelta(weeks=i, days=6)} for i in range(3)]
util_grid = []
for crew in CREWS + [SUB_CREW]:
    weeks_data = []
    for w in weeks:
        sched = wx = mx = 0
        for r in ops_rows:
            rcrew = r["crew"] if r["crew"] in CREWS else (SUB_CREW if "Subcontractor" in (r["crew"] or "") or r["crew"] == SUB_CREW else None)
            if rcrew != crew: continue
            d = days_overlap_in_window(r["start"], r["end"], w["start"], w["end"])
            if d <= 0: continue
            if r["status"] == "Weather Hold": wx += d
            elif r["status"] == "Material Hold": mx += d
            elif r["status"] in ACTIVE_STATUSES | {COMPLETE}: sched += d
        weeks_data.append({
            "weekStart": w["start"].isoformat(),
            "scheduled": sched, "weatherLost": wx, "materialLost": mx,
            "capacity": CAPACITY_PER_CREW_WEEK,
        })
    util_grid.append({"crew": crew, "weeks": weeks_data})

# ---------- Jobs behind (deduped by job) ----------
def calc_days_behind(r):
    if r["variance"] is not None and r["variance"] > 0:
        return int(r["variance"])
    if r["end"] and r["end"] < today and r["status"] in ACTIVE_STATUSES:
        return (today - r["end"]).days
    return 0

jobs_behind_by_job = {}
for r in ops_rows:
    db = calc_days_behind(r)
    if db <= 0 or r["status"] not in ACTIVE_STATUSES | HOLDS: continue
    existing = jobs_behind_by_job.get(r["job_num"])
    if not existing or db > existing["varianceDays"]:
        jobs_behind_by_job[r["job_num"]] = {
            "jobNum": r["job_num"], "company": r["company"],
            "phase": r["phase"] or r["crew"], "pm": r["pm"], "city": r["city"],
            "endDate": r["end"].isoformat() if r["end"] else None,
            "varianceDays": db, "status": r["status"],
        }
jobs_behind = sorted(jobs_behind_by_job.values(), key=lambda x: -x["varianceDays"])[:10]

# ---------- Tons placed weekly (13 weeks) ----------
ts_start_week = this_week_start - timedelta(weeks=12)
tons_weekly = defaultdict(lambda: {"tons": 0, "tonsLY": 0})
for r in ops_rows:
    if r["status"] != COMPLETE or not r["end"]: continue
    ws = week_start(r["end"])
    if ts_start_week <= ws <= this_week_start:
        tons_weekly[ws.isoformat()]["tons"] += r["tons"]
    try:
        shifted = week_start(date(ws.year + 1, ws.month, ws.day))
        if ts_start_week <= shifted <= this_week_start:
            tons_weekly[shifted.isoformat()]["tonsLY"] += r["tons"]
    except ValueError: pass

tons_weekly_series = []
cursor = ts_start_week
while cursor <= this_week_start:
    w = tons_weekly.get(cursor.isoformat(), {"tons": 0, "tonsLY": 0})
    tons_weekly_series.append({"weekStart": cursor.isoformat(),
                               "tons": round(w["tons"], 1), "tonsLY": round(w["tonsLY"], 1)})
    cursor += timedelta(weeks=1)

# ---------- Completed Not Billed aging ----------
cnb_buckets = {"0-7 days": [], "8-14 days": [], "15-30 days": [], "30+ days": []}
ready_total = invoiced_total = paid_total = overdue_total = 0

if sv_raw:
    for r in sv_raw.get("rows", []):
        end_d = parse_date(cv(r, SV["END_DATE"]))
        status = cv(r, SV["BILLING_STATUS"]) or ""
        contract = to_number(cv(r, SV["CONTRACT_PRICE"])) or 0
        balance = to_number(cv(r, SV["BALANCE_DUE"])) or 0
        date_invoiced = parse_date(cv(r, SV["DATE_INVOICED"]))
        is_unbilled = (status == "Ready to Invoice") or (not date_invoiced and end_d and end_d < today)
        if is_unbilled and end_d:
            age = max(0, (today - end_d).days)
            entry = {"jobNum": str(cd(r, SV["JOB_NUM"]) or ""),
                     "company": cv(r, SV["COMPANY_NAME"]) or cv(r, SV["CLIENT"]) or "",
                     "amount": money_round(contract), "ageDays": age}
            if age <= 7: cnb_buckets["0-7 days"].append(entry)
            elif age <= 14: cnb_buckets["8-14 days"].append(entry)
            elif age <= 30: cnb_buckets["15-30 days"].append(entry)
            else: cnb_buckets["30+ days"].append(entry)
        if status == "Ready to Invoice": ready_total += contract
        elif status == "Invoiced": invoiced_total += contract
        elif status == "Paid in Full": paid_total += contract
        elif status == "Overdue": overdue_total += balance

cnb_summary = [{"bucket": k, "count": len(v),
                "amount": sum(j["amount"] for j in v),
                "jobs": sorted(v, key=lambda x: -x["ageDays"])[:5]}
               for k, v in cnb_buckets.items()]

# ---------- Status counts ----------
status_counts = Counter(r["status"] for r in ops_rows)

# ---------- Assemble ----------
out = {
    "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "source": "Cassidy Smartsheet — Operations Schedule + Silva Billing Queue",
    "asOf": {"today": today.isoformat(), "mtdStart": mtd_start.isoformat(),
             "priorMtdStart": prior_mtd_start.isoformat(),
             "priorMtdEnd": prior_mtd_end.isoformat(),
             "thisWeekStart": this_week_start.isoformat()},
    "kpis": {
        "crewUtilThisWeek": {
            "scheduledDays": total_scheduled_this_week,
            "availableDays": total_capacity_this_week, "pct": util_pct},
        "tonsMTD": {"value": round(tons_mtd, 1), "priorMonth": round(tons_prior, 1)},
        "syMTD": {"value": round(sy_mtd, 1), "priorMonth": round(sy_prior, 1)},
        "slip7d": {"scheduled": sched_7d, "completed": done_7d},
        "holdsMTD": {"weather": weather_mtd, "material": material_mtd, "total": holds_mtd},
        "revenueInProgress": {"amount": money_round(rev_in_progress)},
    },
    "crewUtilGrid": util_grid,
    "jobsBehind": jobs_behind,
    "tonsWeekly": tons_weekly_series,
    "completedNotBilled": cnb_summary,
    "billingTotals": {
        "readyToInvoice": money_round(ready_total),
        "invoiced": money_round(invoiced_total),
        "paidInFull": money_round(paid_total),
        "overdueBalance": money_round(overdue_total),
    },
    "statusCounts": dict(status_counts),
}

json.dump(out, sys.stdout, indent=2, ensure_ascii=False, default=str)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             