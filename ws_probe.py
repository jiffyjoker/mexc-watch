import asyncio,json,time,collections,websockets,sys
DUR=int(sys.argv[1]) if len(sys.argv)>1 else 180
async def main():
    c=collections.Counter();syms=set();t0=time.time();sample=None
    async with websockets.connect('wss://contract.mexc.com/edge',ping_interval=None,max_size=2**24) as ws:
        await ws.send(json.dumps({'method':'sub.tickers','param':{}}))
        for s in ('BTC_USDT','XRP_USDT'):
            for iv in ('Min1','Min5'): await ws.send(json.dumps({'method':'sub.kline','param':{'symbol':s,'interval':iv}}))
        lp=0
        while time.time()-t0<DUR:
            if time.time()-lp>15: await ws.send(json.dumps({'method':'ping'})); lp=time.time()
            try: m=json.loads(await asyncio.wait_for(ws.recv(),5))
            except asyncio.TimeoutError: continue
            ch=m.get('channel');c[ch]+=1
            if ch=='push.tickers':
                d=m['data']; syms.update(x['symbol'] for x in d)
                if sample is None: sample={k:d[0].get(k) for k in d[0]}
            if ch=='push.kline' and c[ch]==1: print('kline sample',json.dumps(m)[:300])
    el=time.time()-t0
    print('secs',round(el),'msgs',dict(c),'per_min',{k:round(v/el*60,1) for k,v in c.items()},'ticker_syms',len(syms))
    print('ticker fields',sample)
asyncio.run(main())
