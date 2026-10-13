"""Parse analyst X posts (raw/posts.jsonl) into directional calls and score vs MEXC 1h closes (../cache1h).
Direction = keyword vote (heuristic, not hand-labelled). Returns in % of price, no fees (signal quality test)."""
import json,re,bisect,math,statistics as S,collections,random,datetime as dt
A={'KillaXBT','CastilloTrading','EmperorBTC','scottmelker','fundstrat','astronomer_zero','Wealthmanager','rektcapital','CryptoCapo_','DaanCrypto','CryptoJelleNL','MerlijnTrader','Pentosh1','AltcoinSherpa','CryptoKaleo','TedPillows','crypto_lens_','CrypNuevo'}
P=[json.loads(l) for l in open('raw/posts.jsonl')]
K={c:json.load(open(f'../cache1h/{c}_USDT.json'))['k'] for c in ['BTC','ETH','SOL']}
TT={c:[int(x) for x in K[c]['time']] for c in K};CL={c:[float(x) for x in K[c]['close']] for c in K}
HI={c:[float(x) for x in K[c]['high']] for c in K};LO={c:[float(x) for x in K[c]['low']] for c in K}
BULL=r'\b(long|longed|longing|longs? opened|bullish|breakout|pump|higher|bounce|rally|reclaim|accumulat\w*|buy|bought|send it|moon|upside|bottom is in|squeeze)\b'
BEAR=r'\b(short|shorted|shorting|bearish|breakdown|dump|lower|rejection|reject|sell|sold|crash|downside|top is in|bull trap|capitulat\w*)\b'
def coin(t):
    s=t.lower()
    if re.search(r'\$eth\b|\beth\b|ethereum',s) and not re.search(r'\$btc|\bbtc\b|bitcoin',s): return 'ETH'
    if re.search(r'\$sol\b|\bsolana\b',s) and not re.search(r'\$btc|\bbtc\b|bitcoin',s): return 'SOL'
    if re.search(r'\$btc|\bbtc\b|bitcoin',s): return 'BTC'
    return None
def levels(t):
    out=[]
    for m in re.finditer(r'\$?(\d{1,3}(?:[.,]\d{1,3})?)\s*([kK])\b|\$(\d{1,3}(?:,\d{3})+|\d{3,6})(?:\.\d+)?',t):
        if m.group(1): v=float(m.group(1).replace(',','.'))*1000
        else: v=float(m.group(3).replace(',',''))
        out.append(v)
    return out
def idx(c,ts): return bisect.bisect_right(TT[c],ts)-1
calls=[]
for p in P:
    if p.get('user') not in A: continue
    c=coin(p['text'])
    if not c: continue
    s=p['text'].lower();b=len(re.findall(BULL,s));e=len(re.findall(BEAR,s))
    if b==e: continue
    d=1 if b>e else -1
    ts=int(dt.datetime.fromisoformat(p['t'].replace('Z','+00:00')).timestamp())
    i=idx(c,ts)
    if i<0 or i+24*7>=len(TT[c]): continue
    p0=CL[c][i];r={h:d*(CL[c][i+24*h]/p0-1)*100 for h in (1,3,7)}
    lv=[x for x in levels(p['text']) if 0.7*p0<x<1.3*p0] if c=='BTC' else [x for x in levels(p['text']) if 0.5*p0<x<1.5*p0]
    tgt=inv=None
    if lv:
        above=[x for x in lv if x>p0*1.003];below=[x for x in lv if x<p0*0.997]
        if d==1: tgt=max(above) if above else None;inv=min(below) if below else None
        else: tgt=min(below) if below else None;inv=max(above) if above else None
    hit=None
    if tgt and inv:
        hit=0
        for j in range(i+1,i+24*7+1):
            th=(HI[c][j]>=tgt) if d==1 else (LO[c][j]<=tgt);ti=(LO[c][j]<=inv) if d==1 else (HI[c][j]>=inv)
            if ti: hit=0;break
            if th: hit=1;break
        else: hit=None  # neither within 7d
    calls.append(dict(user=p['user'],t=p['t'],url=f"https://x.com/{p['user']}/status/{p['id']}",coin=c,dir=d,price=p0,target=tgt,invalid=inv,r1=r[1],r3=r[3],r7=r[7],hit=hit))
json.dump(calls,open('calls.json','w'),indent=0)
# baseline: drift per coin per horizon over the same period (random-direction expectation = 0; always-long = drift)
def tstat(x): 
    if len(x)<3: return 0
    sd=S.pstdev(x) or 1e-9;return S.mean(x)/sd*math.sqrt(len(x))
# de-duplicate clustering: keep at most one call per user/coin/day
seen=set();D=[]
for c in sorted(calls,key=lambda x:x['t']):
    k=(c['user'],c['coin'],c['t'][:10])
    if k in seen: continue
    seen.add(k);D.append(c)
by=collections.defaultdict(list)
for c in D: by[c['user']].append(c)
rows=[]
for u,L in by.items():
    hits=[c['hit'] for c in L if c['hit'] is not None]
    # excess vs always-long drift: subtract d*drift is equivalent to removing long-bias; use permutation: shuffle directions
    r3=[c['r3'] for c in L];
    rnd=[];rng=random.Random(1)
    for _ in range(2000):
        rnd.append(S.mean([abs(c['r3'])*rng.choice((1,-1)) for c in L]))
    pval=sum(1 for x in rnd if x>=S.mean(r3))/len(rnd)
    rows.append(dict(user=u,n=len(L),bull=sum(c['dir']>0 for c in L),win1=round(sum(c['r1']>0 for c in L)/len(L),2),
        avg1=round(S.mean([c['r1'] for c in L]),2),avg3=round(S.mean(r3),2),avg7=round(S.mean([c['r7'] for c in L]),2),
        t3=round(tstat(r3),2),p_rand3=round(pval,3),tgt_n=len(hits),tgt_rate=round(sum(hits)/len(hits),2) if hits else None))
rows.sort(key=lambda r:(-r['avg3']))
allr={h:[c[f'r{h}'] for c in D] for h in (1,3,7)}
summary=dict(n_calls_raw=len(calls),n_dedup=len(D),overall={h:dict(avg=round(S.mean(v),3),t=round(tstat(v),2),win=round(sum(x>0 for x in v)/len(v),3)) for h,v in allr.items()},
   bull_share=round(sum(c['dir']>0 for c in D)/len(D),2),
   long_only_baseline={h:round(S.mean([c[f'r{h}']*c['dir'] for c in D]),3) for h in (1,3,7)},rows=rows)
json.dump(summary,open('score_calls.json','w'),indent=1)
print(json.dumps({k:v for k,v in summary.items() if k!='rows'}))
for r in rows: print(r)
