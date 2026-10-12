import json, os, time, urllib.request
B='https://contract.mexc.com/api/v1/contract/'
H={'User-Agent':'GrokBot/1.0'}
def get(u):
    return json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=20))['data']
SEEN='seen.json'
seen=json.load(open(SEEN)) if os.path.exists(SEEN) else {}
now=time.time(); seen={k:v for k,v in seen.items() if now-v<6*3600}
import re
tick=[t for t in get(B+'ticker') if t['symbol'].endswith('_USDT') and float(t.get('amount24',0))>=1e7
      and not re.search(r'(STOCK|XAU|XAG|GOLD|SILVER|OIL|NAS|SPX|TSLA|NVDA|AAPL|COIN|MSTR)',t['symbol'])]
tick=sorted(tick,key=lambda t:-float(t['amount24']))[:50]
hits=[]
for t in tick:
    s=t['symbol']
    try:
        k=get(B+f'kline/{s}?interval=Min15&start={int(now)-26*3600}&end={int(now)}')
    except Exception: continue
    T,hi,lo,cl=k['time'],k['high'],k['low'],k['close']
    if len(cl)<98: continue
    # drop the still-open bar
    if T[-1]+900>now: T,hi,lo,cl=T[:-1],hi[:-1],lo[:-1],cl[:-1]
    ph,pl=max(hi[-97:-1]),min(lo[-97:-1])
    if ph<=0 or (ph-pl)/pl>=0.10: continue
    loc=(cl[-2]-pl)/(ph-pl) if ph>pl else .5
    side=None
    if cl[-1]>ph and cl[-2]<=ph and 0.50<=loc<=0.85: side='long'; lvl=ph
    if cl[-1]<pl and cl[-2]>=pl and 0.15<=loc<=0.50: side='short'; lvl=pl
    if side and s not in seen:
        seen[s]=now; hits.append(dict(symbol=s,side=side,level=lvl,close=cl[-1],bar=T[-1]))
    time.sleep(0.1)
json.dump(seen,open(SEEN,'w'))
day=time.strftime('%Y-%m-%d',time.gmtime(now+36000))
cnt=seen.get('_n_'+day,0)
for h in hits:
    if cnt>=12: break
    body=json.dumps({'event':'breakout','source':'github',**h}).encode()
    auth=os.environ['WEBHOOK_AUTH'].split('Authorization:',1)[-1].strip()
    r=urllib.request.Request(os.environ['WEBHOOK_URL'],data=body,headers={'Content-Type':'application/json','Authorization':auth,**H})
    print(h['symbol'],h['side'],urllib.request.urlopen(r,timeout=20).status); cnt+=1
seen['_n_'+day]=cnt; json.dump(seen,open(SEEN,'w'))
print('scanned',len(tick),'hits',len(hits))
