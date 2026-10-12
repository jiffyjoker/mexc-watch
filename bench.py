"""Rate-limit probe: full scan request pattern back-to-back, logs HTTP codes."""
import json,time,urllib.request,urllib.error,collections,re
B='https://contract.mexc.com/api/v1/contract/';H={'User-Agent':'GrokBot/1.0'}
c=collections.Counter();n=0;t0=time.time()
def g(u):
    global n;n+=1
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=15);d=json.load(r)
        c[f"{r.status}/{d.get('code')}"]+=1;return d.get('data')
    except urllib.error.HTTPError as e: c[f'HTTP{e.code}']+=1
    except Exception as e: c[type(e).__name__]+=1
it=0
while time.time()-t0<240:
    s=time.time();it+=1
    tk=g(B+'ticker') or []
    syms=[t['symbol'] for t in sorted(tk,key=lambda t:-float(t.get('amount24',0)))][:30]
    g(B+f'kline/BTC_USDT?interval=Min15&start={int(s)-10800}&end={int(s)}')
    for x in syms: g(B+f'kline/{x}?interval=Min15&start={int(s)-100800}&end={int(s)}'); time.sleep(0.05)
    print(f'scan {it}: {round(time.time()-s,1)}s total_req {n} codes {dict(c)}',flush=True)
print('FINAL req',n,'in',round(time.time()-t0),'s =',round(n/(time.time()-t0),2),'req/s',dict(c))
