import fcntl, json, os, time, urllib.request
B='https://contract.mexc.com/api/v1/contract/'
H={'User-Agent':'GrokBot/1.0'}
DRY=os.environ.get('DRY_RUN')=='1'
CAP=30
DEDUPE={'breakout':12*3600,'retest':12*3600,'sweep':6*3600,'btc_move':3600,'oi_surge':6*3600}
MUTED={'oi_surge'}  # detected for the log, never posted
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
            sig=h['signal']
            if sig in MUTED: print('muted',sig,h['symbol'],flush=True); continue
            key=f"{'level' if sig in ('breakout','retest') else sig}:{h['symbol']}"
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
def taker_buy_share(sym,n=100):
    """Buy share of the last n public trades by volume (MEXC deals: T=1 buy, 2 sell). None if unavailable."""
    try:
        d=get(B+f'deals/{sym}?limit={n}',tries=2); t=sum(float(x['v']) for x in d)
        return sum(float(x['v']) for x in d if x.get('T')==1)/t if t else None
    except Exception: return None
def taker_against(side,share):
    """RULES triad: taker flow must agree with the side. Missing data never blocks."""
    return share is not None and ((side=='long' and share<0.5) or (side=='short' and share>0.5))
def breakout_check(sym,side,level,k,i,oi6=None,funding=None,chg24=None,taker=None):
    """Mechanical breakout gates shared with the downstream bot. Returns (reasons, info).
    A missing input never blocks. Public deals are fetched only after the cheap gates pass."""
    R=[]; L=side in ('L','long')
    cl,v=k['close'],k['vol']
    if i>=100 and i<len(v):
        av=sum(v[i-96:i])/96 or 1
        if v[i]<2*av: R.append('vol_lt_2x')
    if level and i<len(cl) and abs(cl[i]/level-1)>0.015: R.append('chase_gt_1.5pct')
    if chg24 is not None and ((L and chg24<0) or (not L and chg24>0)): R.append('against_day')
    if oi6 is not None and oi6<-1: R.append('oi_6h_fall')
    if funding is not None and ((L and funding>=0.0005) or (not L and funding<=-0.0005)): R.append('funding_extreme')
    if not R and taker is None: taker=taker_buy_share(sym)
    if taker is not None and ((L and taker<0.5) or (not L and taker>0.5)): R.append('taker_against')
    return R, dict(taker_buy_pct=None if taker is None else round(float(taker),3))
