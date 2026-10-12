"""Daily review: what price did 1h/4h/12h after each wake, and would-be R with RULES stop/target."""
import json, os, sys, time
from common import get, post, load, B
FEE=0.0016; now=time.time(); TEST=os.environ.get('TEST')=='true'
wakes=[w for w in load('wakes.json',[]) if now-w['t']<=36*3600 and w.get('price')]
def kl(s,a,b):
    T,Hh,L,C=[],[],[],[]
    while a<b:
        k=get(B+f'kline/{s}?interval=Min5&start={a}&end={min(b,a+1900*300)}')
        if not k or not k['time']: break
        for t,h,l,c in zip(k['time'],k['high'],k['low'],k['close']):
            if not T or t>T[-1]: T.append(t);Hh.append(h);L.append(l);C.append(c)
        a=T[-1]+300
    return T,Hh,L,C
rows=[]
for w in wakes:
    s,t0,p0=w['symbol'],int(w['t']),float(w['price']); sg=1 if w.get('side')=='long' else -1
    try: T,Hh,L,C=kl(s,t0-3*3600,int(min(now,t0+12*3600)))
    except Exception: continue
    i=next((j for j,t in enumerate(T) if t>=t0-300),None)
    if i is None: continue
    def at(h):
        j=next((j for j,t in enumerate(T) if t>=t0+h*3600),None); return None if j is None else round(sg*(C[j]/p0-1)*100,2)
    lo,hi=min(L[max(0,i-12):i+1]),max(Hh[max(0,i-12):i+1])
    atr=sum(Hh[j]-L[j] for j in range(max(0,i-36),i))/max(1,min(36,i))*1.7
    d=(p0-(lo-0.4*atr))/p0 if sg>0 else ((hi+0.4*atr)-p0)/p0
    d=min(max(d,0.012),0.03); R=None
    for j in range(i+1,len(C)):
        if (sg>0 and L[j]<=p0*(1-d)) or (sg<0 and Hh[j]>=p0*(1+d)): R=-1; break
        if (sg>0 and Hh[j]>=p0*(1+2*d)) or (sg<0 and L[j]<=p0*(1-2*d)): R=2; break
    if R is None: R=round(sg*(C[-1]/p0-1)/d,2); state='open'
    else: state='closed'
    rows.append(dict(time=time.strftime('%m-%d %H:%M',time.gmtime(t0+36000)),signal=w['signal'],symbol=s,side=w.get('side'),price=p0,
        h1=at(1),h4=at(4),h12=at(12),stop_pct=round(d*100,2),R=round(R-FEE/d,2),state=state))
day=time.strftime('%Y-%m-%d',time.gmtime(now+36000))
md=[f'# Scanner review {day} (local time)','',f'Wakes in last 36h: {len(rows)}','',
    '| time local | signal | coin | side | price | 1h % | 4h % | 12h % | stop % | would-be R | |','|'+'---|'*11]
for r in rows: md.append('| '+' | '.join(str(r[k]) for k in ('time','signal','symbol','side','price','h1','h4','h12','stop_pct','R','state'))+' |')
by={}
for r in rows: by.setdefault(r['signal'],[]).append(r['R'])
summ='; '.join(f"{k}: {len(v)} wakes, net {sum(v):+.2f}R" for k,v in by.items()) or 'no wakes'
md+=['',f'Summary: {summ}','','R uses RULES stops (structure + 0.4x ATR, 1.2-3%) and a 2x target, fees 0.16% round trip, 12h max hold.']
os.makedirs('reviews',exist_ok=True); open(f'reviews/{day}.md','w').write('\n'.join(md)+'\n')
print('\n'.join(md),flush=True)
if not TEST: post({'event':'daily_review','source':'github','date':day,'wakes':len(rows),'summary':summ,'file':f'reviews/{day}.md'})
else: print('test mode: webhook skipped')
