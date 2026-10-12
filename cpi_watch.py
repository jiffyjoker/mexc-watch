"""CPI watcher: wakes the trader on a sharp BTC move around the US CPI print."""
import argparse, json, os, time, urllib.request
from datetime import datetime, timezone
B='https://contract.mexc.com/api/v1/contract/'
H={'User-Agent':'GrokBot/1.0'}
def ts(x): return datetime.fromisoformat(x.replace('Z','+00:00')).timestamp()
def iso(t): return datetime.fromtimestamp(t,timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=10))['data']
def kl(now):
    k=get(B+f'kline/BTC_USDT?interval=Min1&start={int(now)-600}&end={int(now)}')
    return [dict(t=t,o=o,h=h,l=l,c=c) for t,o,h,l,c in zip(k['time'],k['open'],k['high'],k['low'],k['close'])]
def price():
    try: return float(get(B+'ticker?symbol=BTC_USDT')['lastPrice']),'ticker'
    except Exception:
        return float(kl(time.time())[-1]['c']),'kline'
def post(body,dry):
    if dry: print('DRY POST',json.dumps(body),flush=True); return 200
    auth=os.environ['WEBHOOK_AUTH'].split('Authorization:',1)[-1].strip()
    r=urllib.request.Request(os.environ['WEBHOOK_URL'],data=json.dumps(body).encode(),
        headers={'Content-Type':'application/json','Authorization':auth,**H})
    st=urllib.request.urlopen(r,timeout=20).status; print('POST status',st,flush=True); return st
a=argparse.ArgumentParser()
a.add_argument('--start-at',default='2026-10-14T12:20:00Z')
a.add_argument('--ref-at',default='2026-10-14T12:29:00Z')
a.add_argument('--minutes',type=float,default=70)
a.add_argument('--threshold-pct',type=float,default=0.7)
a.add_argument('--test',action='store_true')
a.add_argument('--dry-run',action='store_true')
o=a.parse_args()
if o.test: o.start_at=iso(time.time()); o.minutes=3; o.threshold_pct=0.01
start=ts(o.start_at); end=start+o.minutes*60; refat=ts(o.ref_at)
if time.time()<start: print('sleeping until',o.start_at,flush=True); time.sleep(max(0,start-time.time()))
hist=[]; ref=None; fired=0; last_move=None; cap=1 if o.test else 4
while time.time()<end and fired<cap:
    now=time.time()
    try: p,src=price()
    except Exception as e: print(iso(now),'price error',type(e).__name__,flush=True); time.sleep(60); continue
    hist.append((now,p))
    rng=0.0
    try:
        ks=kl(now); done=[k for k in ks if k['t']+60<=now]
        if done: b=done[-1]; rng=(b['h']-b['l'])/b['l']*100
        if ref is None and not o.test and now>=refat+60:
            r=[k for k in ks if k['t']==int(refat)]
            if r: ref=float(r[0]['c']); print('ref fixed at 12:29 close',ref,flush=True)
    except Exception as e: print('kline error',type(e).__name__,flush=True)
    if ref is not None: rp=ref
    else:
        old=[x for x in hist if now-x[0]>=110]; rp=old[-1][1] if old else hist[0][1]
    move=(p/rp-1)*100
    print(iso(now),src,'price',p,'ref',rp,'move%',round(move,3),'range%',round(rng,3),flush=True)
    trig=abs(move)>=o.threshold_pct or rng>=0.5
    if o.test: trig=True  # test: fire exactly once
    if trig and (last_move is None or abs(move)-abs(last_move)>=0.7 or (move>0)!=(last_move>0)):
        body=dict(event='cpi_move',signal='cpi_move',symbol='BTC_USDT',move_pct=round(move,3),ref_price=rp,
                  price=p,minute_range_pct=round(rng,3),time=iso(now))
        if o.test: body.update(test=True,note='TEST - ignore, do not trade')
        try: post(body,o.dry_run); fired+=1; last_move=move
        except Exception as e: print('post failed',type(e).__name__,flush=True)
    if fired>=cap: break
    time.sleep(max(1,60-(time.time()-now)))
print('done, wakes',fired,flush=True)
