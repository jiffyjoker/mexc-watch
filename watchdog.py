"""Checks the mexc-scan chain is alive; restarts it, else wakes the trader with scanner_down."""
import json, os, subprocess, sys, time
from datetime import datetime
from common import post
R=os.environ['GITHUB_REPOSITORY']; TEST=os.environ.get('TEST')=='true'
def gh(*a): return subprocess.run(['gh',*a],capture_output=True,text=True,timeout=60)
def ts(x): return datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()
def check():
    r=gh('run','list','-R',R,'-w','mexc-scan','-L','5','--json','databaseId,status,createdAt')
    runs=json.loads(r.stdout or '[]'); live=[x for x in runs if x['status'] in ('in_progress','queued','waiting','pending')]
    if not live: return False,'no mexc-scan run in progress'
    if any(x['status']!='in_progress' for x in live) and not any(x['status']=='in_progress' for x in live): 
        age=time.time()-ts(live[0]['createdAt']); return age<600,f'queued {int(age)}s'
    run=[x for x in live if x['status']=='in_progress'][0]
    j=json.loads(gh('run','view',str(run['databaseId']),'-R',R,'--json','jobs').stdout)['jobs'][0]
    steps=[s for s in j['steps'] if s.get('startedAt') and s['status'] in ('in_progress','completed')]
    last=max(ts(s['startedAt']) for s in steps) if steps else ts(run['createdAt'])
    age=time.time()-last  # heartbeat = newest step start; a scan chunk lasts ~30 min
    return age<45*60, f"run {run['databaseId']} newest step {int(age/60)} min ago"
ok,why=check(); print('healthy' if ok else 'DEAD',why,flush=True)
if TEST: print('test mode: no action'); sys.exit(0)
if not ok:
    r=gh('workflow','run','mexc-scan','-R',R); print('dispatch rc',r.returncode,flush=True)
    time.sleep(90); ok2,why2=check(); print('after restart:',ok2,why2,flush=True)
    if not ok2: post({'event':'scanner_down','source':'github','detail':why2,'time':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())})
# daily review trigger (cron backup): between 21:00 and 21:59 UTC, once per day
if time.gmtime().tm_hour==21:
    r=gh('run','list','-R',R,'-w','daily-review','-L','1','--json','createdAt')
    runs=json.loads(r.stdout or '[]')
    if not runs or time.time()-ts(runs[0]['createdAt'])>12*3600: print('dispatch review rc',gh('workflow','run','daily-review','-R',R).returncode)
