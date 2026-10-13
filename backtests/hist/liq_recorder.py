#!/usr/bin/env python3
"""Public liquidation recorder (no keys, no trading). Binance !forceOrder@arr (1 snapshot/sym/sec, largest only),
Bybit allLiquidation (all fills) for top coins, OKX liquidation-orders WS on :443 (all USDT swaps; :8443 blocked from box; plain /ws/ Binance path silent, /market/ws/ works).
Writes paper/hist/liq/YYYY-MM-DD.jsonl: {ts,ex,sym,side(long/short liquidated),px,qty,usd}"""
import asyncio, json, time, os, urllib.request, websockets
D=os.path.join(os.path.dirname(os.path.abspath(__file__)),'liq')
os.makedirs(D,exist_ok=True)
for k in list(os.environ):
    if k.startswith('MEXC_'): del os.environ[k]
BY=["BTC","ETH","SOL","XRP","DOGE","BNB","ADA","AVAX","LINK","SUI","HYPE","LTC","DOT","AAVE","NEAR","APT","ARB","OP","TON","TRX","ENA","WIF","PEPE","UNI","FIL","ATOM","TIA","SEI","INJ","ETC"]
def w(rec):
    rec['usd']=round(rec['px']*rec['qty'],2)
    with open(os.path.join(D,time.strftime('%Y-%m-%d',time.gmtime(rec['ts']/1e3))+'.jsonl'),'a') as f: f.write(json.dumps(rec)+'\n')
async def binance():
    while True:
        try:
            async with websockets.connect('wss://fstream.binance.com/market/ws/!forceOrder@arr',ping_interval=60) as ws:
                async for m in ws:
                    o=json.loads(m)['o']
                    w(dict(ts=o['T'],ex='binance',sym=o['s'],side='long' if o['S']=='SELL' else 'short',px=float(o['ap'] or o['p']),qty=float(o['z'] or o['q'])))
        except Exception as e: print('binance',repr(e)[:120],flush=True); await asyncio.sleep(10)
async def bybit():
    while True:
        try:
            async with websockets.connect('wss://stream.bybit.com/v5/public/linear',ping_interval=None) as ws:
                await ws.send(json.dumps({"op":"subscribe","args":[f"allLiquidation.{c}USDT" for c in BY]}))
                async def ping():
                    while True: await asyncio.sleep(20); await ws.send('{"op":"ping"}')
                pt=asyncio.create_task(ping())
                try:
                    async for m in ws:
                        j=json.loads(m)
                        for o in j.get('data') or []:
                            # Bybit S = side of liquidated position: Buy = long liquidated
                            w(dict(ts=o['T'],ex='bybit',sym=o['s'],side='long' if o['S']=='Buy' else 'short',px=float(o['p']),qty=float(o['v'])))
                finally: pt.cancel()
        except Exception as e: print('bybit',repr(e)[:120],flush=True); await asyncio.sleep(10)
def okx_ctval():
    rq=urllib.request.Request('https://www.okx.com/api/v5/public/instruments?instType=SWAP',headers={'User-Agent':'Mozilla/5.0'})
    r=json.load(urllib.request.urlopen(rq,timeout=20))
    return {i['instId']:float(i['ctVal']) for i in r['data']}
async def okx():
    ctv={}
    while True:
        try:
            if not ctv: ctv=await asyncio.to_thread(okx_ctval)
            async with websockets.connect('wss://ws.okx.com:443/ws/v5/public',ping_interval=None) as ws:
                await ws.send(json.dumps({"op":"subscribe","args":[{"channel":"liquidation-orders","instType":"SWAP"}]}))
                async def ping():
                    while True: await asyncio.sleep(20); await ws.send('ping')
                pt=asyncio.create_task(ping())
                try:
                    async for m in ws:
                        if m=='pong': continue
                        for blk in json.loads(m).get('data') or []:
                            iid=blk.get('instId','')
                            if not iid.endswith('-USDT-SWAP'): continue
                            for o in blk['details']:
                                w(dict(ts=int(o['ts']),ex='okx',sym=iid.replace('-USDT-SWAP','USDT'),side=o['posSide'],px=float(o['bkPx']),qty=float(o['sz'])*ctv.get(iid,1)))
                finally: pt.cancel()
        except Exception as e: print('okx',repr(e)[:120],flush=True); await asyncio.sleep(10)
async def main(): await asyncio.gather(binance(),bybit(),okx())
asyncio.run(main())
