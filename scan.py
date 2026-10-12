import json, os, re, time, urllib.request
B='https://contract.mexc.com/api/v1/contract/'
H={'User-Agent':'GrokBot/1.0'}
DRY=os.environ.get('DRY_RUN')=='1'
EXCL=r'(STOCK|XAU|XAG|GOLD|SILVER|OIL|NAS|SPX|TSLA|NVDA|AAPL|COIN|MSTR|NICKEL|COPPER|PLAT|PALL|NATGAS|SOX|QQQ|TQQQ|SQQQ|SPY|DJI|HOOD|CRCL)'
DEDUPE={'breakout':12*3600,'retest':12*3600,'sweep':6*3600,'btc_move':3600}
CAP=12
VB=float(os.environ.get('VB','3'))  # breakout-bar volume vs 24h avg
RNG=float(os.environ.get('RNG','0.07'))
TOP=int(os.environ.get('TOP','30'))  # max 24h range
def get(u,tries=3):
    for i in range(tries):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=15))
            if d.get('success',True): return d['data']
        except Exception: pass
        time.sleep(1+i)
    raise RuntimeError('api '+u)

def signals(k,i,chg24):
    """Evaluate closed bar i of kline dict k. Returns list of (signal,side,level)."""
    if i<100: return []
    hi,lo,cl,op,v=k['high'],k['low'],k['close'],k['open'],k['vol']
    out=[]
    av=sum(v[i-96:i])/96 or 1
    ph,pl=max(hi[i-96:i]),min(lo[i-96:i])          # 24h before bar i
    if pl<=0 or (ph-pl)/pl>=RNG: return out
    loc=(cl[i-1]-pl)/(ph-pl) if ph>pl else .5
    # 1 breakout (original)
    if cl[i]>ph and cl[i-1]<=ph and 0.50<=loc<=0.85 and chg24>0 and v[i]>=VB*av: out.append(('breakout','long',ph))
    if cl[i]<pl and cl[i-1]>=pl and 0.15<=loc<=0.50 and chg24<0 and v[i]>=VB*av: out.append(('breakout','short',pl))
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
    now=time.time()
    seen=json.load(open('seen.json')) if os.path.exists('seen.json') else {}
    seen={k:v for k,v in seen.items() if k.startswith('_n_') or now-v<12*3600}
    tick=[t for t in get(B+'ticker') if t['symbol'].endswith('_USDT') and float(t.get('amount24',0))>=1e7
          and not re.search(EXCL,t['symbol'])]
    tick=sorted(tick,key=lambda t:-float(t['amount24']))[:TOP]
    hits=[]
    def add(sig,s,side,lvl,extra):
        key=f"{'level' if sig in ('breakout','retest') else sig}:{s}"  # breakout+retest share one per-coin slot
        if now-seen.get(key,0)<DEDUPE[sig]: return
        seen[key]=now; hits.append(dict(signal=sig,symbol=s,side=side,level=lvl,**extra))
    # BTC market-wide move
    try:
        k=get(B+f'kline/BTC_USDT?interval=Min15&start={int(now)-3*3600}&end={int(now)}')
        i=closed(k,now); m=k['close'][i]/k['close'][i-1]-1
        if abs(m)>=0.015: add('btc_move','BTC_USDT','long' if m>0 else 'short',k['close'][i-1],dict(close=k['close'][i],move_pct=round(m*100,2),bar=k['time'][i]))
    except Exception as e: print('btc err',e)
    for t in tick:
        s=t['symbol']
        try: k=get(B+f'kline/{s}?interval=Min15&start={int(now)-28*3600}&end={int(now)}')
        except Exception: continue
        i=closed(k,now)
        try: sg=signals(k,i,float(t.get('riseFallRate',0)))
        except Exception: continue
        for sig,side,lvl in sg:
            add(sig,s,side,lvl,dict(close=k['close'][i],bar=k['time'][i],funding=t.get('fundingRate')))
        time.sleep(0.05)
    day=time.strftime('%Y-%m-%d',time.gmtime(now+36000))
    cnt=seen.get('_n_'+day,0)
    seen={k:v for k,v in seen.items() if not k.startswith('_n_') or k=='_n_'+day}
    for h in hits:
        if cnt>=CAP: print('cap reached'); break
        body=json.dumps({'event':h['signal'],'source':'github',**h}).encode()
        if DRY: print('DRY',body.decode()); cnt+=1; continue
        try:
            auth=os.environ['WEBHOOK_AUTH'].split('Authorization:',1)[-1].strip()
            r=urllib.request.Request(os.environ['WEBHOOK_URL'],data=body,headers={'Content-Type':'application/json','Authorization':auth,**H})
            print(h['signal'],h['symbol'],h['side'],urllib.request.urlopen(r,timeout=20).status); cnt+=1
        except Exception as e: print('post failed',h['symbol'],type(e).__name__)
    if not DRY:
        seen['_n_'+day]=cnt; json.dump(seen,open('seen.json','w'))
    print('scanned',len(tick),'hits',len(hits),'secs',round(time.time()-now,1))

if __name__=='__main__': main()
