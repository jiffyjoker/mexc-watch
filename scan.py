import fcntl, json, os, re, time, urllib.request
from common import get, load, commit_hits, B, H
B='https://contract.mexc.com/api/v1/contract/'
H={'User-Agent':'GrokBot/1.0'}
DRY=os.environ.get('DRY_RUN')=='1'
EXCL=r'(STOCK|XAU|XAG|GOLD|SILVER|OIL|NAS|SPX|TSLA|NVDA|AAPL|COIN|MSTR|NICKEL|COPPER|PLAT|PALL|NATGAS|SOX|QQQ|TQQQ|SQQQ|SPY|DJI|HOOD|CRCL)'
DEDUPE={'breakout':12*3600,'retest':12*3600,'sweep':6*3600,'btc_move':3600,'oi_surge':6*3600}
CAP=12
VB=float(os.environ.get('VB','3'))  # breakout-bar volume vs 24h avg
RNG=float(os.environ.get('RNG','0.07'))
TOP=int(os.environ.get('TOP','30'))  # max 24h range

def signals(k,i,chg24):
    """Evaluate closed bar i of kline dict k. Returns list of (signal,side,level)."""
    if i<100: return []
    hi,lo,cl,op,v=k['high'],k['low'],k['close'],k['open'],k['vol']
    out=[]
    av=sum(v[i-96:i])/96 or 1
    ph,pl=max(hi[i-96:i]),min(lo[i-96:i])          # 24h before bar i
    if pl<=0 or (ph-pl)/pl>=RNG: return out
    loc=(cl[i-8]-pl)/(ph-pl) if ph>pl else .5  # location at arm time (2h before); the bar before a break is always ~0/1
    # 1 breakout (original)
    if cl[i]>ph and cl[i-1]<=ph and cl[i]<=ph*1.01 and 0.50<=loc<=0.85 and chg24>0 and v[i]>=VB*av: out.append(('breakout','long',ph))
    if cl[i]<pl and cl[i-1]>=pl and cl[i]>=pl*0.99 and 0.15<=loc<=0.50 and chg24<0 and v[i]>=VB*av: out.append(('breakout','short',pl))
    # 2 retest-and-hold: break 2-8 bars ago, every close since held, this bar tagged level (0.3%) and closed back away, <1% past
    for b in range(i-6,i-1):
        bh,bl=max(hi[b-96:b]),min(lo[b-96:b])
        if cl[b]>bh and cl[b-1]<=bh and chg24>0 and v[b]>=VB*av and all(c>bh for c in cl[b:i+1]) \
           and lo[i]<=bh*1.003 and cl[i]>op[i] and cl[i]<=bh*1.01:
            out.append(('retest','long',bh)); break
        if cl[b]<bl and cl[b-1]>=bl and chg24<0 and v[b]>=VB*av and all(c<bl for c in cl[b:i+1]) \
           and hi[i]>=bl*0.997 and cl[i]<op[i] and cl[i]>=bl*0.99:
            out.append(('retest','short',bl)); break
    # 3 failed-breakout sweep: wick >=0.3% through 24h extreme, close back inside, volume >=2x 24h avg, only with the day
    if hi[i]>=ph*1.003 and cl[i]<ph and cl[i]<op[i] and v[i]>=2*av and chg24<0: out.append(('sweep','short',ph))
    if lo[i]<=pl*0.997 and cl[i]>pl and cl[i]>op[i] and v[i]>=2*av and chg24>0: out.append(('sweep','long',pl))
    return out

def closed(k,now):
    n=len(k['time'])
    return n-2 if k['time'][-1]+900>now else n-1

def main():
    now=time.time(); live=os.environ.get('LIVE')=='1'
    tick=[t for t in get(B+'ticker') if t['symbol'].endswith('_USDT') and float(t.get('amount24',0))>=1e7
          and not re.search(EXCL,t['symbol'])]
    tick=sorted(tick,key=lambda t:-float(t['amount24']))[:TOP]
    hits=[]; levels={}
    with open('.lock','w') as lk:
        fcntl.flock(lk,fcntl.LOCK_EX)
        oi=load('oi.json',{})
        for t in tick:
            try: oi.setdefault(t['symbol'],[]).append([int(now),float(t['holdVol'])])
            except Exception: pass
        oi={k:[p for p in v if now-p[0]<=24*3600] for k,v in oi.items() if v and now-v[-1][0]<=24*3600}
        json.dump(oi,open('oi.json','w'))
    def oichg(s,h):
        pts=oi.get(s,[])
        if not pts or pts[-1][0]-pts[0][0]<h*3600*0.9: return None
        old=min(pts,key=lambda p:abs(p[0]-(pts[-1][0]-h*3600)))
        return round((pts[-1][1]/old[1]-1)*100,2) if old[1] else None
    def add(sig,s,side,lvl,extra): hits.append(dict(signal=sig,symbol=s,side=side,level=lvl,**extra))
    try:
        k=get(B+f'kline/BTC_USDT?interval=Min15&start={int(now)-3*3600}&end={int(now)}')
        i=closed(k,now); m=k['close'][i]/k['close'][i-1]-1
        if abs(m)>=0.015: add('btc_move','BTC_USDT','long' if m>0 else 'short',k['close'][i-1],dict(close=k['close'][i],move_pct=round(m*100,2),bar=k['time'][i]))
    except Exception as e: print('btc err',e)
    for t in tick:
        s=t['symbol']
        try: k=get(B+f'kline/{s}?interval=Min15&start={int(now)-28*3600}&end={int(now)}')
        except Exception: continue
        i=closed(k,now); chg=float(t.get('riseFallRate',0))
        o1,o6=oichg(s,1),oichg(s,6)
        try: fr=float(t.get('fundingRate') or 0)
        except Exception: fr=0.0
        ex=dict(close=k['close'][i],bar=k['time'][i],funding=fr,funding_pct=round(fr*100,4),funding_extreme=abs(fr)>=0.0005,oi_1h_pct=o1,oi_6h_pct=o6)
        # levels for the bar now forming (used by live.py to judge the next 15m close within seconds)
        try:
            j=len(k['time'])-1 if k['time'][-1]+900>now else len(k['time'])
            hi,lo,cl,v=k['high'],k['low'],k['close'],k['vol']
            ph,pl=max(hi[j-96:j]),min(lo[j-96:j]); al=(cl[j-8]-pl)/(ph-pl) if ph>pl else .5
            levels[s]=dict(ph=ph,pl=pl,arm_loc=round(al,3),range_ok=(ph-pl)/pl<RNG,avgv=sum(v[j-96:j])/96,chg24=chg,**{x:ex[x] for x in ('funding','funding_pct','funding_extreme','oi_1h_pct','oi_6h_pct')})
        except Exception: pass
        try: sg=signals(k,i,chg)
        except Exception: continue
        for sig,side,lvl in sg:
            if sig=='breakout' and live: continue  # live.py owns breakouts (fires seconds after the close)
            if sig in ('breakout','retest') and o6 is not None and o6<-1: continue  # OI falling over 6h
            if sig in ('breakout','retest') and ((side=='long' and fr>=0.0005) or (side=='short' and fr<=-0.0005)): continue  # crowded funding
            add(sig,s,side,lvl,ex)
        c=k['close']; p1=c[i]/c[i-4]-1
        if o1 is not None and o1>=15 and ((chg>0 and p1>0.003) or (chg<0 and p1<-0.003)):
            add('oi_surge',s,'long' if chg>0 else 'short',c[i-4],ex)
        time.sleep(0.05)
    json.dump(dict(t=int(now),levels=levels),open('levels.tmp','w')); os.replace('levels.tmp','levels.json')
    sent=commit_hits(hits)
    print(time.strftime('%H:%M:%SZ',time.gmtime()),'scanned',len(tick),'hits',len(hits),'sent',sent,'secs',round(time.time()-now,1),flush=True)

if __name__=='__main__': main()
