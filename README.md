# Cassidy Ops Dashboard

Live operations KPI dashboard, pulled from Smartsheet every 15 minutes.

**Live URL:** https://cassidysmartsheet-ux.github.io/cassidy-ops-dashboard/

## What it shows
- **Crew Util · This Week** — sum of scheduled crew-days across all crews / 30 day capacity (6 crews × 5 days)
- **Tons MTD** — `Asphalt Tons` summed across rows with Status = Complete + End Date in MTD
- **Square Yards MTD** — same calc on `Square Yards`
- **7-Day Slip** — Completed/Scheduled count over last 7 days
- **Holds MTD** — count of rows with Status = Weather Hold or Material Hold
- **Revenue in Progress** — Contract Price of Scheduled/In Progress rows not on Silva Billing Queue
- **Crew Utilization Grid** — per-crew, this week + next 2, with weather/material days lost shown
- **Jobs Behind Schedule** — top 10 by days behind (using Variance formula)
- **Tons placed weekly** — last 13 weeks with YoY ghost line
- **Completed Not Billed** aging buckets + billing totals from Silva Billing Queue

## How it refreshes
GitHub Action runs every 15 min:
1. Curls Smartsheet API (read-only `CalendarGit` token)
2. Runs `.github/scripts/transform.py` → writes `data.json`
3. Commits + pushes (with 3-attempt rebase retry)

## Known data quality issues
- `Job Record` sheet has only 1 row — actual tons placed isn't being captured. Dashboard uses estimated tons from Operations Schedule instead.
- `Weather Forecast Sheet` is empty — no forecast strip yet.

## Read-only — do not edit
