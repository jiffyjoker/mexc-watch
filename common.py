import fcntl, json, os, time, urllib.request
B='https://contract.mexc.com/api/v1/contract/'
H={'User-Agent':'GrokBot/1.0'}
DRY=os.environ.get('DRY_RUN')=='1'
CAP=30
DEDUPE={'breakout':12*3600,'retest':12*3600,'sweep':6*3600,'btc_move':3600,'oi_surge':6*3600}
def get(u,tries=3):
    for i in range(tries):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=15))
            if d.get('success',True): return d['data']
        except Exception: pass
        time.sleep(1+i)
    raise RuntimeError('api '+u)
def post(body):
    if DRY: print('DRY POST',json.dumps(body),flush=True); return 200
    auth=os.environ['WEBHOOK_AUTH'].split('Authorization:',1)[-1].strip()
    r=urllib.request.Request(os.environ['WEBHOOK_URL'],data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','Authorization':auth,**H})
    st=urllib.request.urlopen(r,timeout=20).status
    print('POST',body.get('event'),body.get('symbol',''),'status',st,flush=True); return st
def load(p,d):
    try: return json.load(open(p))
    except Exception: return d
def commit_hits(hits):
    """Dedupe, cap, post and log wakes under a file lock (scan.py and live.py run side by side)."""
    if not hits: return 0
    with open('.lock','w') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX)
        now=time.time(); seen=load('seen.json',{}); wakes=load('wakes.json',[])
        day=time.strftime('%Y-%m-%d',time.gmtime(now+36000)); cnt=seen.get('_n_'+day,0); sent=0
        for h in hits:
            sig=h['signal']; key=f"{'level' if sig in ('breakout','retest') else sig}:{h['symbol']}"
            if now-seen.get(key,0)<DEDUPE.get(sig,6*3600): continue
            if cnt>=CAP: print('cap reached',flush=True); break
            try: post({'event':sig,'source':'github',**h})
            except Exception as e: print('post failed',h['symbol'],type(e).__name__,flush=True); continue
            seen[key]=now; cnt+=1; sent+=1
            wakes.append(dict(t=int(now),signal=sig,symbol=h['symbol'],side=h.get('side'),price=h.get('close') or h.get('price'),level=h.get('level')))
        seen={k:v for k,v in seen.items() if (k=='_n_'+day) or (not k.startswith('_n_') and now-v<12*3600)}
        seen['_n_'+day]=cnt
        if not DRY:
            json.dump(seen,open('seen.json','w')); json.dump([w for w in wakes if now-w['t']<3*86400],open('wakes.json','w'))
    return sent
