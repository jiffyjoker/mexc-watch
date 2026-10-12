"""Stage 1/2 live breakout watcher.
Stage 1: MEXC websocket push.tickers (all coins, ~every 2-3s) -> mark coins 'hot' when within 0.3% of the
cached 24h level (levels.json, written by scan.py) or moving >1% in a minute. REST ticker polling every 60s if
the websocket is down. Stage 2: 5s after each 15m close, fetch 15m klines for hot coins only and run the exact
breakout rules (scan.signals), then the OI/funding gates, then wake."""
import argparse, asyncio, json, os, time
import scan
from common import get, load, commit_hits, B
a=argparse.ArgumentParser(); a.add_argument('--minutes',type=float,default=30); o=a.parse_args()
END=time.time()+o.minutes*60
px={}; hist={}; hot={}; st=dict(mode='init',msgs=0,reconnects=0,rest_calls=0)
def lv(): return load('levels.json',{}).get('levels',{})
def on_prices(rows,now,levels):
    for r in rows:
        s=r.get('symbol');p=r.get('lastPrice')
        if s not in levels or not p: continue
        p=float(p); px[s]=p; h=hist.setdefault(s,[]); h.append((now,p))
        while h and now-h[0][0]>90: h.pop(0)
        L=levels[s]; old=[q for t,q in h if now-t>=55]
        near=abs(p/L['ph']-1)<=0.003 or abs(p/L['pl']-1)<=0.003 or p>L['ph'] or p<L['pl']
        fast=bool(old) and abs(p/old[0]-1)>=0.01
        if near or fast:
            if s not in hot: print(time.strftime('%H:%M:%SZ',time.gmtime()),'hot',s,p,'near' if near else 'fast',flush=True)
            hot[s]=now
def stage2(levels):
    now=time.time(); cands=[s for s,t in hot.items() if now-t<=16*60]
    for s in list(hot):
        if now-hot[s]>16*60: del hot[s]
    hits=[]
    for s in cands:
        try: k=get(B+f'kline/{s}?interval=Min15&start={int(now)-28*3600}&end={int(now)}'); st['rest_calls']+=1
        except Exception: continue
        i=scan.closed(k,now); L=levels.get(s,{})
        for sig,side,lvl in scan.signals(k,i,L.get('chg24',0)):
            if sig!='breakout': continue
            o6=L.get('oi_6h_pct'); fr=L.get('funding',0) or 0
            if o6 is not None and o6<-1: print('skip OI falling',s,flush=True); continue
            if (side=='long' and fr>=0.0005) or (side=='short' and fr<=-0.0005): print('skip funding',s,flush=True); continue
            hits.append(dict(signal='breakout',symbol=s,side=side,level=lvl,close=k['close'][i],bar=k['time'][i],via='live',
                past_level_pct=round(abs(k['close'][i]/lvl-1)*100,3),arm_loc=L.get('arm_loc'),
                **{x:L.get(x) for x in ('funding','funding_pct','funding_extreme','oi_1h_pct','oi_6h_pct')}))
    print(time.strftime('%H:%M:%SZ',time.gmtime()),'stage2 checked',len(cands),'hits',len(hits),'sent',commit_hits(hits),flush=True)
async def ws_loop():
    import websockets
    back=1
    while time.time()<END:
        try:
            async with websockets.connect('wss://contract.mexc.com/edge',ping_interval=None,max_size=2**24,open_timeout=15) as ws:
                await ws.send(json.dumps({'method':'sub.tickers','param':{}})); st['mode']='ws'; back=1; lp=0; last_msg=time.time()
                while time.time()<END:
                    if time.time()-lp>15: await ws.send(json.dumps({'method':'ping'})); lp=time.time()
                    try: m=json.loads(await asyncio.wait_for(ws.recv(),5))
                    except asyncio.TimeoutError:
                        if time.time()-last_msg>60: raise RuntimeError('ws stalled')
                        continue
                    last_msg=time.time(); st['msgs']+=1
                    if m.get('channel')=='push.tickers': on_prices(m['data'],time.time(),LEV[0])
        except Exception as e:
            st['mode']='rest'; st['reconnects']+=1
            print('ws down',type(e).__name__,'retry in',back,'s',flush=True)
            await asyncio.sleep(back); back=min(back*2,120)
async def rest_loop():
    while time.time()<END:
        await asyncio.sleep(60)
        if st['mode']!='ws':
            try: on_prices(await asyncio.to_thread(get,B+'ticker'),time.time(),LEV[0]); st['rest_calls']+=1
            except Exception as e: print('rest ticker err',type(e).__name__,flush=True)
async def clock():
    last_close=int(time.time()//900*900)
    while time.time()<END:
        now=time.time(); LEV[0]=lv() or LEV[0]
        b=int(now//900*900)
        if b!=last_close and now-b>=5:
            last_close=b; await asyncio.to_thread(stage2,LEV[0])
        if int(now)%60<2:
            json.dump(dict(t=int(now),**st,hot=len(hot)),open('heartbeat.json','w'))
            print(time.strftime('%H:%M:%SZ',time.gmtime()),'hb',st,'hot',sorted(hot),flush=True); await asyncio.sleep(2)
        await asyncio.sleep(1)
LEV=[lv()]
async def main(): await asyncio.gather(ws_loop(),rest_loop(),clock())
asyncio.run(main())
