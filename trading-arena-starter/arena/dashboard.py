"""Local, read-only Arena dashboard with isolated historical backtests."""
import json
import re
import sqlite3
import threading
import uuid
from datetime import date, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

from arena.market.data import DataStore
from arena.supervisor.runner import Arena

ROOT = Path.cwd()
RUNS = ROOT / "dashboard_runs"
RUNS.mkdir(exist_ok=True)
RUNS_LOCK = threading.Lock()
RUNS_STATE = {}
HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arena — Paper Trading Lab</title>
<style>
:root{color-scheme:dark;--bg:#0b1015;--panel:#111920;--panel2:#151f27;--line:#26343d;--muted:#8c9ba4;--text:#e8f0ed;--green:#9de3bd;--mint:#5fcca0;--red:#ff897e;--amber:#e6bd73;--blue:#87b8d9}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 78% -20%,#20352c 0,transparent 38%),var(--bg);color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.shell{max-width:1440px;margin:auto;padding:30px 34px 48px}.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:30px}.brand{display:flex;align-items:center;gap:12px}.mark{width:38px;height:38px;border-radius:12px;background:linear-gradient(145deg,#c4f1d4,#46b884);color:#12251c;display:grid;place-items:center;font-weight:900;font-size:19px;box-shadow:0 8px 26px #61d39b30}.brand strong{font-size:16px;letter-spacing:.2px}.brand small{display:block;color:var(--muted);font-size:11px;letter-spacing:1.5px;text-transform:uppercase}.topright{display:flex;align-items:center;gap:10px;color:var(--muted);font-size:12px}.pill{border:1px solid #2a4c3b;background:#12251d;color:var(--green);border-radius:99px;padding:6px 11px;display:flex;gap:7px;align-items:center}.dot{height:7px;width:7px;border-radius:50%;background:#71d5a0;box-shadow:0 0 10px #71d5a0}
.hero{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;margin:0 0 22px}.eyebrow{font-size:11px;text-transform:uppercase;letter-spacing:1.8px;color:var(--green);font-weight:700}.hero h1{font-size:clamp(28px,3.5vw,42px);letter-spacing:-1.7px;line-height:1.12;margin:6px 0 8px}.hero p{margin:0;color:var(--muted);max-width:650px}.select{min-width:205px;background:#121b22;border:1px solid var(--line);color:var(--text);border-radius:10px;padding:11px 13px;font:inherit}
.grid{display:grid;gap:14px}.metrics{grid-template-columns:repeat(4,1fr);margin-bottom:14px}.card{background:linear-gradient(160deg,#141e25,#10171d);border:1px solid var(--line);border-radius:15px;padding:18px;min-width:0;box-shadow:0 10px 28px #00000014}.metric-label{color:var(--muted);font-size:12px}.metric-value{font-size:26px;letter-spacing:-.7px;font-weight:650;margin:6px 0 3px}.metric-note{font-size:11px;color:var(--muted)}.good{color:var(--green)}.negative{color:var(--red)}.muted{color:var(--muted)}
.main-grid{grid-template-columns:minmax(0,1.6fr) minmax(310px,.9fr);margin-bottom:14px}.card-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:15px}.card h2{margin:0;font-size:15px;font-weight:650;letter-spacing:.1px}.sub{color:var(--muted);font-size:11px;margin-top:3px}.tag{color:#b8c8c5;background:#1b292e;border-radius:7px;padding:4px 8px;font-size:10px;text-transform:uppercase;letter-spacing:.6px;white-space:nowrap}.chart{width:100%;height:242px;display:block;overflow:visible}.chart text{fill:#778891;font-size:10px}.legend{display:flex;gap:13px;flex-wrap:wrap;color:#b5c2c5;font-size:11px;margin-top:8px}.legend i{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}.bot-list{display:grid;gap:9px}.bot{display:grid;grid-template-columns:1fr auto;align-items:center;gap:7px;padding:12px;background:#151f26;border:1px solid #233139;border-radius:11px}.bot-name{font-weight:650}.bot-sub{font-size:11px;color:var(--muted)}.bot-equity{text-align:right;font-size:15px;font-weight:650}.bot-return{text-align:right;font-size:11px}.avatar{display:inline-grid;place-items:center;width:26px;height:26px;border-radius:8px;margin-right:8px;background:#263b33;color:var(--green);font-size:10px;font-weight:700}.bot-left{display:flex;align-items:center}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;white-space:nowrap}th{text-align:left;color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.7px;font-weight:600;padding:10px 8px;border-bottom:1px solid var(--line)}td{padding:12px 8px;border-bottom:1px solid #202b32;font-size:12px}tr:last-child td{border-bottom:0}.rank{width:23px;height:23px;border-radius:7px;background:#202d32;display:inline-grid;place-items:center;color:#b7c5c1;font-size:11px}.rank.first{background:#294b3a;color:var(--green)}.bottom-grid{grid-template-columns:1.2fr .8fr}.timeline{display:grid;gap:0}.event{position:relative;padding:0 0 17px 20px;border-left:1px solid #314139;margin-left:6px}.event:last-child{border-color:transparent;padding-bottom:0}.event:before{content:"";position:absolute;left:-4px;top:4px;width:7px;height:7px;background:var(--mint);border-radius:50%;box-shadow:0 0 9px #5fcca055}.event strong{font-size:12px}.event small{display:block;color:var(--muted);font-size:11px}.event p{margin:4px 0 0;color:#bdcbc7;font-size:11px}.experiment{display:grid;grid-template-columns:1fr 1fr;gap:10px}.field label{display:block;color:var(--muted);font-size:11px;margin:0 0 5px}.field input{width:100%;background:#0c1419;border:1px solid #2a3940;border-radius:9px;padding:9px 10px;color:var(--text);font:inherit}.run-btn{border:0;background:var(--green);color:#0d2118;font:650 12px inherit;border-radius:9px;padding:11px 14px;cursor:pointer;grid-column:1/-1}.run-btn:hover{background:#baf2d0}.run-btn:disabled{opacity:.55;cursor:wait}.note{background:#18252a;border-left:2px solid var(--amber);padding:10px 12px;border-radius:0 8px 8px 0;color:#c1cbc6;font-size:11px;margin-top:13px}.status{font-size:11px;color:var(--muted);margin-top:10px;min-height:17px}.empty{color:var(--muted);font-size:12px;padding:18px 10px;text-align:center}.footer{text-align:center;color:#71818a;font-size:10px;margin-top:20px;letter-spacing:.2px}
@media(max-width:900px){.metrics{grid-template-columns:repeat(2,1fr)}.main-grid{grid-template-columns:1fr}.bottom-grid{grid-template-columns:1fr}.hero{align-items:flex-start;flex-direction:column}.select{width:100%}}@media(max-width:520px){.shell{padding:20px 14px}.metrics{gap:8px}.metric-value{font-size:21px}.card{padding:14px}.topright .clock{display:none}.experiment{grid-template-columns:1fr 1fr}}
</style>
</head><body><main class="shell">
<header class="top"><div class="brand"><div class="mark">A</div><div><strong>ARENA</strong><small>Paper trading lab</small></div></div><div class="topright"><span class="clock" id="updated">Local ledger</span><span class="pill"><i class="dot"></i> PAPER ONLY</span></div></header>
<section class="hero"><div><div class="eyebrow">Evolution, made visible</div><h1>Three bots. One arena.</h1><p>Track simulated capital, compare strategy families, and watch the weekly selection loop. No broker connection. No real money.</p></div><select class="select" id="source"><option value="backtest">Latest historical backtest</option><option value="paper">Live paper ledger</option></select></section>
<section class="grid metrics">
 <article class="card"><div class="metric-label">Active bots</div><div class="metric-value" id="active">—</div><div class="metric-note" id="activeNote">Three competitors, one survivor's loop</div></article>
 <article class="card"><div class="metric-label">Active paper equity</div><div class="metric-value" id="equity">—</div><div class="metric-note" id="equityNote">Combined value of active bots</div></article>
 <article class="card"><div class="metric-label">Evolutions</div><div class="metric-value" id="evolutions">—</div><div class="metric-note" id="evolutionNote">Elimination and mutated births</div></article>
 <article class="card"><div class="metric-label">Last processed day</div><div class="metric-value" style="font-size:19px" id="lastDay">—</div><div class="metric-note" id="freshness">Waiting for ledger</div></article>
</section>
<section class="grid main-grid">
 <article class="card"><div class="card-head"><div><h2>Equity journey</h2><div class="sub">Daily closes · each bot's own lineage</div></div><span class="tag" id="chartTag">CAD · history</span></div><svg class="chart" id="chart" viewBox="0 0 760 250" role="img" aria-label="Bot equity over time"></svg><div class="legend" id="legend"></div></article>
 <article class="card"><div class="card-head"><div><h2>On the board</h2><div class="sub">Current generation and holdings</div></div><span class="tag">Capital · CAD</span></div><div class="bot-list" id="bots"></div></article>
</section>
<section class="grid bottom-grid">
 <article class="card"><div class="card-head"><div><h2>Weekly leaderboard</h2><div class="sub">Ranked by return %, exactly as Arena selects</div></div><span class="tag">Recent weeks</span></div><div class="table-wrap" id="leaderboard"></div></article>
 <article class="card"><div class="card-head"><div><h2>Evolution trail</h2><div class="sub">Who survived, who was copied</div></div><span class="tag">Lineage</span></div><div class="timeline" id="events"></div></article>
</section>
<section class="grid main-grid" style="margin-top:14px">
 <article class="card"><div class="card-head"><div><h2>Replay a past market</h2><div class="sub">Start fresh three-bot capital, run against cached historical bars</div></div><span class="tag">No lookahead</span></div><form id="replay" class="experiment"><div class="field"><label for="start">Decision window starts</label><input id="start" type="date" required></div><div class="field"><label for="end">Decision window ends</label><input id="end" type="date" required></div><button class="run-btn" id="runBtn">Run isolated historical replay ↗</button></form><div class="note">Bars before the start date are used only for strategy warm-up. Decisions see prices through that day; orders fill at the next trading day's open. This is a backtest, not a forecast.</div><div class="status" id="runStatus"></div></article>
 <article class="card"><div class="card-head"><div><h2>Latest fills</h2><div class="sub">Paper executions at next-day open, after slippage</div></div><span class="tag">Simulated</span></div><div class="table-wrap" id="fills"></div></article>
</section>
<div class="footer">PERSONAL PAPER SIMULATION · YAHOO FINANCE DATA · RESULTS DO NOT PREDICT LIVE PERFORMANCE</div>
</main>
<script>
const $=id=>document.getElementById(id), colors=['#9de3bd','#82b6dc','#e8bd79','#dca4d3','#95d3d1','#e68d7f'];
const money=x=>x==null?'—':Number(x).toLocaleString('en-CA',{style:'currency',currency:'CAD'});
const pct=x=>x==null?'—':`${Number(x)>0?'+':''}${Number(x).toFixed(2)}%`;
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function renderChart(points,bots){const svg=$('chart'),w=760,h=250,p={l:48,r:12,t:12,b:28};if(!points.length){svg.innerHTML='<text x="380" y="120" text-anchor="middle">No equity history in this ledger yet</text>';return}
 const dates=[...new Set(points.map(x=>x.date))].sort(),  series=bots.filter(b=>b.status==='active').map(b=>({bot:b,vals:dates.map(d=>{let x=points.find(p=>p.bot_id===b.bot_id&&p.date===d);return x?Number(x.equity):null})})).filter(s=>s.vals.some(v=>v!=null));
 let vals=series.flatMap(s=>s.vals.filter(v=>v!=null));if(!vals.length)return;let min=Math.min(...vals),max=Math.max(...vals);if(min===max){min-=1;max+=1}let xx=i=>p.l+i*(w-p.l-p.r)/Math.max(1,dates.length-1), yy=v=>p.t+(max-v)*(h-p.t-p.b)/(max-min);
 let out='';for(let i=0;i<4;i++){let y=p.t+i*(h-p.t-p.b)/3,v=max-i*(max-min)/3;out+=`<line x1="${p.l}" y1="${y}" x2="${w-p.r}" y2="${y}" stroke="#27343b" stroke-dasharray="3 5"/><text x="${p.l-8}" y="${y+3}" text-anchor="end">${v.toFixed(0)}</text>`}
 if(dates.length){out+=`<text x="${p.l}" y="${h-5}">${dates[0]}</text><text x="${w-p.r}" y="${h-5}" text-anchor="end">${dates.at(-1)}</text>`}
 series.forEach((s,n)=>{let segment=[];const flush=()=>{if(segment.length>1)out+=`<polyline fill="none" stroke="${colors[n%colors.length]}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" points="${segment.join(' ')}"/>`;segment=[]};s.vals.forEach((v,i)=>{if(v==null){flush();return}segment.push(`${xx(i)},${yy(v)}`)});flush()});svg.innerHTML=out;
 $('legend').innerHTML=series.map((s,n)=>`<span><i style="background:${colors[n%colors.length]}"></i>${esc(s.bot.bot_id)} · ${esc(s.bot.strategy.replace('_',' '))}</span>`).join('')}
function render(d){$('active').textContent=d.metrics.active;$('equity').textContent=money(d.metrics.active_equity);$('evolutions').textContent=d.metrics.evolutions;$('lastDay').textContent=d.metrics.last_day||'Not started';$('freshness').textContent=d.metrics.last_day?'Last ledger close':'Paper process has not run yet';$('updated').textContent=d.source==='paper'?'Paper ledger':'Historical replay · '+(d.metrics.last_day||'no daily bars');$('chartTag').textContent=d.source==='paper'?'CAD · live paper':'CAD · backtest';
 $('bots').innerHTML=d.bots.length?d.bots.filter(b=>b.status==='active').map((b,i)=>`<div class="bot"><div class="bot-left"><span class="avatar">${esc(b.bot_id.slice(-3))}</span><div><div class="bot-name">${esc(b.strategy.replace('_',' '))}</div><div class="bot-sub">${esc(b.bot_id)} · gen ${b.generation} · ${b.positions} holding${b.positions===1?'':'s'}</div></div></div><div><div class="bot-equity">${money(b.equity)}</div><div class="bot-return ${Number(b.weekly_return)>=0?'good':'negative'}">${pct(b.weekly_return)} weekly</div></div></div>`).join(''):'<div class="empty">No bot data yet.</div>';
 let weeks=d.weekly||[];$('leaderboard').innerHTML=weeks.length?`<table><thead><tr><th>Week</th><th>Rank</th><th>Bot</th><th>Family</th><th>Return</th><th>Trades</th></tr></thead><tbody>${weeks.map(w=>`<tr><td>${esc(w.week)}</td><td><span class="rank ${w.rank===1?'first':''}">${w.rank}</span></td><td>${esc(w.bot_id)}</td><td>${esc(w.strategy.replace('_',' '))}</td><td class="${Number(w.return_pct)>=0?'good':'negative'}">${pct(w.return_pct)}</td><td>${w.trades}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">Weekly rankings appear after a week boundary is processed.</div>';
 $('events').innerHTML=d.events.length?d.events.slice(0,6).map(e=>`<div class="event"><strong>${esc(e.parent)} → ${esc(e.child)}</strong><small>${esc(e.date)} · ${money(e.freed)} liquidation proceeds${Number(e.topup)>0?' · '+money(e.topup)+' top-up':''}</small><p>${esc(e.eliminated)} eliminated; child inherits ${esc(e.strategy)} genome, mutated.</p></div>`).join(''):'<div class="empty">The first evolution appears after the grace period and a completed evaluation.</div>';
 $('fills').innerHTML=d.fills.length?`<table><thead><tr><th>Day</th><th>Bot</th><th>Side</th><th>Symbol</th><th>Price</th></tr></thead><tbody>${d.fills.map(f=>`<tr><td>${esc(f.date)}</td><td>${esc(f.bot_id)}</td><td class="${f.side==='buy'?'good':'negative'}">${esc(f.side)}</td><td>${esc(f.symbol)}</td><td>${money(f.price)}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">No fills recorded in this view.</div>';
 renderChart(d.equity,d.bots)}
async function load(){try{let r=await fetch('/api/data?source='+encodeURIComponent($('source').value));if(!r.ok)throw Error(await r.text());render(await r.json())}catch(e){$('runStatus').textContent='Dashboard data error: '+e.message}}
$('source').onchange=load;
const today=new Date(),end=new Date(today);end.setDate(end.getDate()-56);const start=new Date(end);start.setDate(start.getDate()-56);const iso=d=>d.toISOString().slice(0,10);$('start').value=iso(start);$('end').value=iso(end);
$('replay').onsubmit=async e=>{e.preventDefault();$('runBtn').disabled=true;$('runStatus').textContent='Starting isolated replay…';try{let r=await fetch('/api/backtest',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({start:$('start').value,end:$('end').value})});let x=await r.json();if(!r.ok)throw Error(x.error);$('runStatus').textContent='Replay is running…';let status;do{await new Promise(res=>setTimeout(res,900));status=await(await fetch('/api/run?id='+encodeURIComponent(x.id))).json()}while(status.status==='running');if(status.status!=='done')throw Error(status.error||'Replay failed');let opt=document.createElement('option');opt.value='run:'+x.id;opt.textContent='Replay '+$('start').value+' → '+$('end').value;$('source').prepend(opt);$('source').value=opt.value;$('runStatus').textContent='Replay complete · '+status.evolutions+' evolutions · isolated from paper ledger';await load()}catch(err){$('runStatus').textContent='Replay failed: '+err.message}finally{$('runBtn').disabled=false}};
load();
</script></body></html>"""


def read_cfg():
    return yaml.safe_load((ROOT / "config.yaml").read_text())


def read_dashboard(db_path: Path, source: str) -> dict:
    if not db_path.is_file():
        return {"source": source, "metrics": {"active": 0, "active_equity": "0.00", "evolutions": 0,
                                                "last_day": None}, "bots": [], "equity": [], "weekly": [],
                "events": [], "fills": []}
    conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        state = dict(conn.execute("SELECT key,value FROM state").fetchall())
        bot_states = json.loads(state.get("bots", "{}"))
        meta = json.loads(state.get("meta", "{}"))
        last_day = meta.get("last_day")
        rows = conn.execute(
            "SELECT d.bot_id,d.date,d.equity FROM daily_equity d "
            "ORDER BY d.date,d.bot_id"
        ).fetchall()
        latest = {}
        for row in rows:
            latest[row["bot_id"]] = row
        weekly_latest = {}
        for row in conn.execute(
            "SELECT w.bot_id,w.week,w.return_pct,w.trades,w.rank,b.strategy "
            "FROM weekly_results w JOIN bots b USING(bot_id) ORDER BY w.week DESC,w.rank"
        ):
            weekly_latest.setdefault(row["bot_id"], row)
        bots = []
        for row in conn.execute(
            "SELECT bot_id,strategy,parent_id,generation,status FROM bots ORDER BY bot_id"
        ):
            saved = bot_states.get(row["bot_id"], {})
            day_row = latest.get(row["bot_id"])
            bots.append({
                "bot_id": row["bot_id"], "strategy": row["strategy"], "parent_id": row["parent_id"],
                "generation": row["generation"], "status": saved.get("status", row["status"]),
                "equity": day_row["equity"] if day_row else saved.get("cash", "0.00"),
                "positions": len(saved.get("positions", {})),
                "weekly_return": (weekly_latest[row["bot_id"]]["return_pct"]
                                  if row["bot_id"] in weekly_latest else None),
            })
        equity = [{"bot_id": r["bot_id"], "date": r["date"], "equity": r["equity"]} for r in rows]
        if len(equity) > 1200:
            # ponytail: chart renders only the latest 1,200 closes; raise the cap if multi-year runs matter.
            equity = equity[-1200:]
        weekly = []
        for r in conn.execute(
            "SELECT w.bot_id,w.week,w.return_pct,w.trades,w.rank,b.strategy "
            "FROM weekly_results w JOIN bots b USING(bot_id) ORDER BY w.week DESC,w.rank LIMIT 36"
        ):
            weekly.append(dict(r))
        events = []
        for row in conn.execute(
            "SELECT timestamp,detail_json FROM events WHERE type='evolution' ORDER BY event_id DESC LIMIT 20"
        ):
            detail = json.loads(row["detail_json"])
            parent = next((b for b in bots if b["bot_id"] == detail.get("parent")), {})
            child_state = bot_states.get(detail.get("child"), {})
            events.append({"date": child_state.get("created_date", row["timestamp"][:10]),
                           "parent": detail.get("parent"), "child": detail.get("child"),
                           "eliminated": detail.get("eliminated"),
                           "freed": detail.get("freed", "0"), "topup": detail.get("topup", "0"),
                           "strategy": parent.get("strategy", "strategy")})
        fills = [dict(r) for r in conn.execute(
            "SELECT fill_date AS date,bot_id,side,symbol,price FROM fills ORDER BY fill_id DESC LIMIT 12"
        )]
        active = [b for b in bots if b["status"] == "active"]
        active_equity = sum((Decimal(b["equity"]) for b in active), Decimal("0"))
        return {"source": source, "metrics": {"active": len(active), "active_equity": f"{active_equity:.2f}",
                                               "evolutions": len(events) if len(events) < 20 else
                                               conn.execute("SELECT count(*) FROM events WHERE type='evolution'").fetchone()[0],
                                               "last_day": last_day or (max((r["date"] for r in rows), default=None))},
                "bots": bots, "equity": equity, "weekly": weekly, "events": events, "fills": fills}
    finally:
        conn.close()


def run_backtest(run_id: str, start: date, end: date) -> None:
    folder = RUNS / run_id
    folder.mkdir(parents=True, exist_ok=True)
    with RUNS_LOCK:
        RUNS_STATE[run_id] = {"status": "running"}
    try:
        cfg = read_cfg()
        arena = Arena(cfg, DataStore(cfg["data_cache_dir"]), folder / "arena.db",
                      folder / "reports", folder / "genomes")
        arena.init_bots(start)
        arena.backtest(start, end)
        events = arena.ledger.db.execute("SELECT count(*) FROM events WHERE type='evolution'").fetchone()[0]
        arena.ledger.db.close()
        with RUNS_LOCK:
            RUNS_STATE[run_id] = {"status": "done", "evolutions": events}
    except Exception as exc:
        with RUNS_LOCK:
            RUNS_STATE[run_id] = {"status": "failed", "error": str(exc)}


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        elif parsed.path == "/":
            body = HTML.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif parsed.path == "/api/data":
            source = params.get("source", ["backtest"])[0]
            if source == "paper":
                path = ROOT / "arena.db"
            elif source == "backtest":
                path = ROOT / "backtest.db"
            elif source.startswith("run:") and re.fullmatch(r"run:[a-f0-9]{12}", source):
                path = RUNS / source[4:] / "arena.db"
            else:
                self.send_json(400, {"error": "Unknown dashboard data source"})
                return
            self.send_json(200, read_dashboard(path, source))
        elif parsed.path == "/api/run":
            run_id = params.get("id", [""])[0]
            with RUNS_LOCK:
                status = RUNS_STATE.get(run_id)
            if status is None and re.fullmatch(r"[a-f0-9]{12}", run_id) and (RUNS / run_id / "arena.db").is_file():
                status = {"status": "done", "evolutions": 0}
            self.send_json(200 if status else 404, status or {"error": "Replay not found"})
        else:
            self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/backtest":
            self.send_error(404)
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            start, end = date.fromisoformat(body["start"]), date.fromisoformat(body["end"])
            if start >= end:
                raise ValueError("Start date must be earlier than end date.")
            cfg = read_cfg()
            store = DataStore(cfg["data_cache_dir"])
            bars = store.trading_days(cfg["universe"], start, end)
            if not bars:
                raise ValueError("No cached market bars in that date range.")
            short_history = [symbol for symbol in cfg["universe"]
                             if not len(store.load(symbol)) or
                             store.load(symbol).index.min().date() > start - timedelta(days=400)]
            if short_history:
                raise ValueError(f"Need at least 400 calendar days of warm-up data before {start}; "
                                 f"insufficient cached history for: {', '.join(short_history)}.")
            run_id = uuid.uuid4().hex[:12]
            threading.Thread(target=run_backtest, args=(run_id, start, end), daemon=True).start()
            self.send_json(202, {"id": run_id})
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            self.send_json(400, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the local Arena dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        parser.error("Dashboard binds to localhost only.")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Arena dashboard: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
