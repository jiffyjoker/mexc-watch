"""Daily X crowd sentiment proxy: per UTC day, top-25 'relevant' posts matching (bitcoin OR $BTC) (bullish OR bearish);
score = (#bullish - #bearish)/25. Compare with next-day BTC return (MEXC 1h closes). Recent-counts endpoint only covers 7d."""
import json,glob,re,datetime as dt,statistics as S,math,bisect
k=json.load(open('../cache1h/BTC_USDT.json'))['k'];T=[int(x) for x in k['time']];C=[float(x) for x in k['close']]
day={}
for f in glob.glob('raw/crowd_*.txt'):
    s=open(f).read();z=json.loads(s[s.find('{'):s.rfind('}')+1])
    for p in z.get('data',[]):
        d=p['created_at'][:10];t=p['text'].lower();b='bullish' in t;e='bearish' in t
        day.setdefault(d,{})[p['id']]=(b,e)
def close_at(ts): i=bisect.bisect_right(T,ts)-1;return C[i]
rows=[]
for d,v in sorted(day.items()):
    n=len(v);sc=(sum(b and not e for b,e in v.values())-sum(e and not b for b,e in v.values()))/n
    t0=int(dt.datetime.fromisoformat(d+'T00:00:00+00:00').timestamp())+86400
    if t0+86400>T[-1]: continue
    same=(close_at(t0)/close_at(t0-86400)-1)*100;nxt=(close_at(t0+86400)/close_at(t0)-1)*100
    rows.append(dict(day=d,n=n,score=round(sc,2),ret_same=round(same,2),ret_next=round(nxt,2)))
def corr(a,b):
    ma,mb=S.mean(a),S.mean(b);return sum((x-ma)*(y-mb) for x,y in zip(a,b))/math.sqrt(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))
sc=[r['score'] for r in rows];nx=[r['ret_next'] for r in rows];sm=[r['ret_same'] for r in rows]
med=S.median(sc);hi=[r['ret_next'] for r in rows if r['score']>med];lo=[r['ret_next'] for r in rows if r['score']<=med]
rc=corr(sc,nx);out=dict(days=len(rows),corr_next=round(rc,3),t_approx=round(rc*math.sqrt((len(rows)-2)/(1-rc*rc)),2),corr_same=round(corr(sc,sm),3),
   next_ret_when_bullish_above_median=round(S.mean(hi),3),next_ret_when_below=round(S.mean(lo),3),rows=rows)
json.dump(out,open('crowd.json','w'),indent=1);print({k:v for k,v in out.items() if k!='rows'})
