"""Funding-extreme contrarian backtest, 365d 1h public MEXC data (../cache1h, embedded funding 'fu').
Returns % of notional per trade, net taker 0.02%/side + funding paid/received. H1 select / H2 validate.
Universe = today's top-50 (survivorship caveat)."""
import json,os,glob,bisect,statistics as S,math,itertools
C=os.path.dirname(os.path.abspath(__file__))+'/../cache1h';H=3600;DAY=86400;FEE=0.0002
X={}
for f in glob.glob(C+'/*_USDT.json'):
    z=json.load(open(f));k=z['k']
    if len(k['time'])<24*60: continue
    s=os.path.basename(f)[:-5];t=[int(x) for x in k['time']]
    X[s]=dict(t=t,ix={x:i for i,x in enumerate(t)},o=[float(x) for x in k['open']],fu=[tuple(x) for x in z['fu']],ft=[x[0] for x in z['fu']])
T0=min(v['t'][0] for v in X.values());T1=max(v['t'][-1] for v in X.values());MID=(T0+T1)//2
def px(s,t):
    v=X[s];i=v['ix'].get(t);return v['o'][i] if i is not None else None
def fund(s,a,b,side):
    v=X[s];i=bisect.bisect_right(v['ft'],a);j=bisect.bisect_right(v['ft'],b);return -side*sum(v['fu'][q][1] for q in range(i,j))*100
def trade(s,a,b,side):
    p0=px(s,a);p1=px(s,b)
    if not p0 or not p1: return None
    return side*(p1/p0-1)*100-2*FEE*100+fund(s,a,b,side)
def lastf(s,t,n=1):
    v=X[s];i=bisect.bisect_right(v['ft'],t)
    return sum(x[1] for x in v['fu'][max(0,i-n):i])/n if i>=n else None
def pctl(s,t,lb=90*DAY):
    v=X[s];i=bisect.bisect_right(v['ft'],t);j=bisect.bisect_left(v['ft'],t-lb)
    xs=[x[1] for x in v['fu'][j:i]]
    if len(xs)<60: return None
    cur=xs[-1];return sum(1 for x in xs if x<=cur)/len(xs)
def grid(step): 
    t=T0//step*step+step+90*DAY
    while t<T1-3*DAY: yield t;t+=step
def stats(r):
    if len(r)<3: return dict(n=len(r))
    m=S.mean(r);sd=S.pstdev(r) or 1e-9;return dict(n=len(r),avg=round(m,3),t=round(m/sd*math.sqrt(len(r)),2),win=round(sum(x>0 for x in r)/len(r),3))
def split(out):
    a=[x for t,x in out if t<MID];b=[x for t,x in out if t>=MID];return stats(a),stats(b)
R={}
# A) BTC own-funding percentile extremes, contrarian, checked at each 8h settlement
for q,hold in itertools.product([0.05,0.10],[1,3]):
    out=[];nxt=0
    for t in grid(8*H):
        if t<nxt: continue
        p=pctl('BTC_USDT',t)
        if p is None: continue
        side=-1 if p>=1-q else (1 if p<=q else 0)
        if side: x=trade('BTC_USDT',t,t+hold*DAY,side);out+=[(t,x)] if x is not None else [];nxt=t+hold*DAY
    R[f'btc_pctl{int(q*100)}_hold{hold}d']=split(out)
# B) market-wide avg funding extreme (avg latest funding over universe, percentile vs own 90d) -> BTC contrarian
mk={}
for t in grid(8*H):
    v=[lastf(s,t) for s in X];v=[x for x in v if x is not None]
    if len(v)>20: mk[t]=S.mean(v)
mt=sorted(mk)
for q,hold in itertools.product([0.05,0.10],[1,3]):
    out=[];nxt=0
    for i,t in enumerate(mt):
        if t<nxt or i<270: continue
        hist=[mk[x] for x in mt[i-270:i+1]];cur=hist[-1];p=sum(1 for x in hist if x<=cur)/len(hist)
        side=-1 if p>=1-q else (1 if p<=q else 0)
        if side: x=trade('BTC_USDT',t,t+hold*DAY,side);out+=[(t,x)] if x is not None else [];nxt=t+hold*DAY
    R[f'mkt_pctl{int(q*100)}_btc_hold{hold}d']=split(out)
# C) cross-sectional absolute extremes: each 8h settlement, coins with last funding >= +thr -> short, <= -thr -> long; hold h
for thr,hold in itertools.product([0.0005,0.001],[1,3]):
    out=[];busy={}
    for t in grid(8*H):
        for s in X:
            if busy.get(s,0)>t: continue
            f=lastf(s,t)
            if f is None: continue
            side=-1 if f>=thr else (1 if f<=-thr else 0)
            if side:
                x=trade(s,t,t+hold*DAY,side)
                if x is not None: out.append((t,x));busy[s]=t+hold*DAY
    R[f'xs_abs{thr*100:.2f}pct_hold{hold}d']=split(out)
# D) cross-sectional own-percentile extremes (5%) per coin
for hold in [1,3]:
    out=[];busy={}
    for t in grid(8*H):
        for s in X:
            if busy.get(s,0)>t: continue
            p=pctl(s,t)
            if p is None: continue
            side=-1 if p>=0.95 else (1 if p<=0.05 else 0)
            if side:
                x=trade(s,t,t+hold*DAY,side)
                if x is not None: out.append((t,x));busy[s]=t+hold*DAY
    R[f'xs_pctl5_hold{hold}d']=split(out)
for k,(a,b) in R.items(): print(f'{k:28s} H1 {a}  H2 {b}')
json.dump({k:dict(H1=a,H2=b) for k,(a,b) in R.items()},open('bt_funding.json','w'),indent=1)
