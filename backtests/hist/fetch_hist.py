#!/usr/bin/env python3
"""Resumable free-history cache (public, no keys). Rate-limit safe (paced, small thread pool on CDN only)."""
import json,os,time,urllib.request,datetime as dt,concurrent.futures as cf
H=os.path.dirname(os.path.abspath(__file__)); UA={'User-Agent':'Mozilla/5.0'}
def get(u,raw=False,tries=4):
    for i in range(tries):
        try:
            b=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=30).read()
            return b if raw else json.loads(b)
        except urllib.error.HTTPError as e:
            if e.code==404: return None
            time.sleep(2+5*i)
        except Exception: time.sleep(2+5*i)
def mk(*p): d=os.path.join(H,*p); os.makedirs(d,exist_ok=True); return d
syms=[f[:-10] for f in os.listdir(os.path.join(H,'..','cache')) if f.endswith('_USDT.json') and not f.startswith('fund_')]
def fng():
    j=get('https://api.alternative.me/fng/?limit=0&format=json'); json.dump(j['data'],open(os.path.join(mk(),'fear_greed.json'),'w'))
def dvol():
    for c in ('BTC','ETH'):
        out=[]; end=int(time.time()*1000)
        while True:
            j=get(f'https://www.deribit.com/api/v2/public/get_volatility_index_data?currency={c}&start_timestamp=1600000000000&end_timestamp={end}&resolution=3600')
            d=j['result']['data']
            if not d: break
            out=d+out; c2=j['result'].get('continuation')
            if not c2 or c2>=end: break
            end=c2; time.sleep(0.3)
        out=sorted({r[0]:r for r in out}.values()); json.dump(out,open(os.path.join(mk(),f'dvol_{c}_1h.json'),'w'))
def coinbase():
    p=os.path.join(mk(),'coinbase_btcusd_1h.json'); rows={}
    t=dt.datetime(2020,1,1,tzinfo=dt.timezone.utc); now=dt.datetime.now(dt.timezone.utc)
    while t<now:
        e=t+dt.timedelta(hours=300)
        j=get(f'https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600&start={t:%Y-%m-%dT%H:%M:%SZ}&end={e:%Y-%m-%dT%H:%M:%SZ}') or []
        for r in j: rows[r[0]]=r
        t=e; time.sleep(0.4)
    json.dump(sorted(rows.values()),open(p,'w'))
    # Binance BTCUSDT spot 1h for premium
    rows={}; s=int(dt.datetime(2020,1,1,tzinfo=dt.timezone.utc).timestamp()*1000)
    while True:
        j=get(f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&startTime={s}&limit=1000')
        if not j: break
        for r in j: rows[r[0]]=r[:6]
        if len(j)<1000: break
        s=j[-1][0]+1; time.sleep(0.3)
    json.dump(sorted(rows.values()),open(os.path.join(mk(),'binance_btcusdt_spot_1h.json'),'w'))
def funding():
    d=mk('funding')
    for s in syms:
        for ex in ('binance','bybit'):
            p=os.path.join(d,f'{ex}_{s}.json')
            if os.path.exists(p): continue
            rows={}
            if ex=='binance':
                st=1567000000000
                while True:
                    j=get(f'https://fapi.binance.com/fapi/v1/fundingRate?symbol={s}USDT&startTime={st}&limit=1000')
                    if not j: break
                    for r in j: rows[r['fundingTime']]=float(r['fundingRate'])
                    if len(j)<1000: break
                    st=j[-1]['fundingTime']+1; time.sleep(0.3)
            else:
                en=int(time.time()*1000)
                while True:
                    j=get(f'https://api.bybit.com/v5/market/funding/history?category=linear&symbol={s}USDT&limit=200&endTime={en}')
                    l=(j or {}).get('result',{}).get('list') or []
                    if not l: break
                    for r in l: rows[int(r['fundingRateTimestamp'])]=float(r['fundingRate'])
                    en=min(int(r['fundingRateTimestamp']) for r in l)-1
                    if len(l)<200: break
                    time.sleep(0.2)
            json.dump(sorted(rows.items()),open(p,'w'))
def misc():
    d=mk()
    j=get('https://stablecoins.llama.fi/stablecoincharts/all'); json.dump(j,open(os.path.join(d,'stablecoins_total.json'),'w'))
    for sid in ('DTWEXBGS','DGS10','DGS2','CPIAUCSL','FEDFUNDS'):
        b=get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}',raw=True)
        if b: open(os.path.join(mk('fred'),sid+'.csv'),'wb').write(b)
    j=get('https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?range=max&interval=1d')
    if j: json.dump(j,open(os.path.join(d,'yahoo_dxy_1d.json'),'w'))
def vision():
    d=mk('vision_metrics'); jobs=[]
    today=dt.date.today()
    for s in syms:
        start=dt.date(2021,12,1) if s in ('BTC','ETH','SOL','XRP','DOGE','BNB') else today-dt.timedelta(days=400)
        x=start
        while x<today-dt.timedelta(days=1):
            p=os.path.join(d,s,f'{x}.zip')
            if not os.path.exists(p) and not os.path.exists(p+'.404'): jobs.append((s,x,p))
            x+=dt.timedelta(days=1)
    def one(a):
        s,x,p=a; os.makedirs(os.path.dirname(p),exist_ok=True)
        b=get(f'https://data.binance.vision/data/futures/um/daily/metrics/{s}USDT/{s}USDT-metrics-{x}.zip',raw=True,tries=3)
        if b: open(p,'wb').write(b)
        else: open(p+'.404','w').close()
    print('vision jobs',len(jobs),flush=True)
    with cf.ThreadPoolExecutor(16) as ex: list(ex.map(one,jobs))
def klines():
    d=mk('vision_klines15m'); jobs=[]; today=dt.date.today()
    for s in syms:
        y,m=2021,12
        while (y,m)<(today.year,today.month):
            p=os.path.join(d,s,f'{y}-{m:02d}.zip')
            if not os.path.exists(p) and not os.path.exists(p+'.404'): jobs.append((s,y,m,p))
            y,m=(y+1,1) if m==12 else (y,m+1)
    def one(a):
        s,y,m,p=a; os.makedirs(os.path.dirname(p),exist_ok=True)
        b=get(f'https://data.binance.vision/data/futures/um/monthly/klines/{s}USDT/15m/{s}USDT-15m-{y}-{m:02d}.zip',raw=True,tries=3)
        if b: open(p,'wb').write(b)
        else: open(p+'.404','w').close()
    print('kline jobs',len(jobs),flush=True)
    with cf.ThreadPoolExecutor(8) as ex: list(ex.map(one,jobs))
import sys
for f in (sys.argv[1:] or ['fng','dvol','misc','coinbase','funding','vision']):
    t=time.time(); globals()[f](); print(f,'done',round(time.time()-t),'s',flush=True)
