import os, time, secrets, datetime as dt
import requests
from flask import Flask, request, Response, render_template_string, redirect

app = Flask(__name__)
API = "https://api.housecallpro.com"
KEY = os.environ.get("HCP_API_KEY", "")
PASSWORD = os.environ.get("APP_PASSWORD", "")
CENTS = os.environ.get("AMOUNTS_IN_CENTS", "true").lower() == "true"
_cache = {"t": 0, "data": None}


@app.before_request
def auth():
    a = request.authorization
    if not PASSWORD or not a or not secrets.compare_digest(a.password or "", PASSWORD):
        return Response("Login required", 401, {"WWW-Authenticate": 'Basic realm="Report"'})


def fetch_all(path, key):
    out, page = [], 1
    while page <= 100:
        r = requests.get(f"{API}{path}", params={"page": page, "page_size": 100},
                         headers={"Authorization": f"Token {KEY}", "Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        j = r.json()
        out += j.get(key, [])
        if page >= (j.get("total_pages") or 1):
            break
        page += 1
    return out


def pick(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and d.get(k) is not None:
            return d[k]
    return default


def money(v):
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        return 0.0
    return v / 100 if CENTS else v


def parse_date(s):
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except Exception:
        return None


def build():
    jobs, invs = fetch_all("/jobs", "jobs"), fetch_all("/invoices", "invoices")
    by_job, by_num = {}, {}
    for i in invs:
        by_job.setdefault(str(pick(i, "job_id", default="")), []).append(i)
        by_num[str(pick(i, "invoice_number", "number", default=""))] = i
    today, rows = dt.date.today(), []
    for j in jobs:
        c = j.get("customer") or {}
        name = (f"{c.get('first_name','')} {c.get('last_name','')}".strip()) or c.get("company", "") or "—"
        inv_list = by_job.get(str(j.get("id"))) or ([by_num[str(j.get("invoice_number"))]] if str(j.get("invoice_number")) in by_num else [])
        work = (j.get("work_status") or "").replace("_", " ")
        total = money(pick(j, "total_amount"))
        if inv_list:
            billed = sum(money(pick(i, "amount", "total", "total_amount")) for i in inv_list)
            due = sum(money(pick(i, "due_amount", "amount_due", "balance", "outstanding_balance", default=0)) for i in inv_list)
            d0 = parse_date(pick(inv_list[0], "invoice_date", "sent_at", "created_at"))
            status = "Paid" if due <= 0.005 else ("Partial" if due < billed - 0.005 else "Unpaid")
            age = (today - d0).days if d0 and due > 0.005 else None
            num = pick(inv_list[0], "invoice_number", "number", default="")
        else:
            billed, due, age, num = 0.0, 0.0, None, j.get("invoice_number") or ""
            status = "Needs invoicing" if "complete" in work else "In progress"
        rows.append(dict(job=j.get("invoice_number") or j.get("id"), customer=name, work=work,
                         date=str(pick(j.get("schedule") or {}, "scheduled_start", default=""))[:10],
                         total=total, billed=billed, due=due, status=status, inv=num, age=age))
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows, jobs[:1], invs[:1]


def data(refresh=False):
    if refresh or not _cache["data"] or time.time() - _cache["t"] > 300:
        _cache["data"], _cache["t"] = build(), time.time()
    return _cache["data"]


PAGE = """<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><title>Jobs & invoices</title>
<style>
:root{--ink:#1c2430;--mut:#667085;--line:#e3e7ee;--bg:#f6f7f9;--blue:#1f5fbf}
*{box-sizing:border-box}body{margin:0;font:15px/1.45 system-ui,Segoe UI,sans-serif;color:var(--ink);background:var(--bg)}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);margin-bottom:20px}.sub a{color:var(--blue)}
.sum{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:20px}
.sum div{background:#fff;border:1px solid var(--line);padding:12px 14px;border-radius:6px}
.sum b{display:block;font-size:22px}.sum span{color:var(--mut);font-size:13px}
.out b{color:#b42318}.tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
.tabs a{padding:6px 12px;border:1px solid var(--line);background:#fff;border-radius:99px;text-decoration:none;color:var(--ink);font-size:14px}
.tabs a.on{background:var(--ink);color:#fff;border-color:var(--ink)}
.wrap{overflow-x:auto;background:#fff;border:1px solid var(--line);border-radius:6px}
table{border-collapse:collapse;width:100%;min-width:760px}th,td{padding:9px 12px;text-align:left;border-bottom:1px solid var(--line);white-space:nowrap}
th{font-size:13px;color:var(--mut);font-weight:600}td.n,th.n{text-align:right}
.s{padding:2px 8px;border-radius:4px;font-size:13px;font-weight:600}
.Paid{background:#dcfae6;color:#067647}.Unpaid{background:#fee4e2;color:#b42318}.Partial{background:#fef0c7;color:#93370d}
.Needs\\ invoicing{background:#e0eaff;color:#1f3f99}.In\\ progress{background:#eef0f4;color:#475467}
</style><main>
<h1>Jobs & invoice status</h1>
<div class=sub>Updated {{ stamp }} · <a href="/?refresh=1">Refresh now</a> · <a href="/check">Data check</a></div>
<div class=sum>
<div class=out><b>${{ '{:,.0f}'.format(uninv) }}</b><span>Value not yet invoiced</span></div>
<div><b>${{ '{:,.0f}'.format(billed) }}</b><span>Invoiced</span></div>
<div><b>${{ '{:,.0f}'.format(billed-due) }}</b><span>Collected</span></div>
<div class=out><b>${{ '{:,.0f}'.format(due) }}</b><span>Still owed</span></div>
<div><b>{{ counts.get('Needs invoicing',0) }}</b><span>Jobs to invoice</span></div>
</div>
<div class=sum>{% for k,v in aging %}<div><b>${{ '{:,.0f}'.format(v) }}</b><span>Unpaid {{ k }}</span></div>{% endfor %}</div>
<div class=tabs>{% for t in tabs %}<a class="{{ 'on' if t==sel else '' }}" href="/?status={{ t }}">{{ t }}{% if t!='All' %} ({{ counts.get(t,0) }}){% endif %}</a>{% endfor %}</div>
<div class=wrap><table><tr><th>Job<th>Customer<th>Date<th>Job status<th>Invoice status<th class=n>Job total<th class=n>Invoiced<th class=n>Owed<th class=n>Days open</tr>
{% for r in rows %}<tr><td>{{ r.job }}<td>{{ r.customer }}<td>{{ r.date }}<td>{{ r.work }}<td><span class="s {{ r.status }}">{{ r.status }}</span>
<td class=n>{{ '${:,.2f}'.format(r.total) }}<td class=n>{{ '${:,.2f}'.format(r.billed) if r.billed else '—' }}<td class=n>{{ '${:,.2f}'.format(r.due) if r.due else '—' }}<td class=n>{{ r.age if r.age is not none else '—' }}</tr>
{% else %}<tr><td colspan=9>No jobs match this filter.</tr>{% endfor %}</table></div></main>"""


@app.route("/")
def index():
    try:
        rows, _, _ = data(bool(request.args.get("refresh")))
    except Exception as e:
        return f"Could not load Housecall Pro data: {e}. Check HCP_API_KEY and your plan's API access.", 502
    if request.args.get("refresh"):
        return redirect("/")
    sel = request.args.get("status", "Needs invoicing")
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    aging = []
    for lab, lo, hi in [("0-30 days", 0, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("90+", 91, 10**6)]:
        aging.append((lab, sum(r["due"] for r in rows if r["age"] is not None and lo <= r["age"] <= hi)))
    shown = [r for r in rows if sel == "All" or r["status"] == sel]
    if sel == "Needs invoicing":
        shown.sort(key=lambda r: r["date"])
    uninv = sum(r["total"] for r in rows if r["status"] == "Needs invoicing")
    return render_template_string(PAGE, rows=shown, sel=sel, counts=counts, aging=aging,
                                  uninv=uninv, billed=sum(r["billed"] for r in rows), due=sum(r["due"] for r in rows),
                                  tabs=["All", "Unpaid", "Partial", "Paid", "Needs invoicing", "In progress"],
                                  stamp=time.strftime("%b %d, %I:%M %p", time.localtime(_cache["t"])))


@app.route("/check")
def check():
    _, j, i = data()
    import json
    return Response(json.dumps({"first_job": j, "first_invoice": i}, indent=2), mimetype="text/plain")
