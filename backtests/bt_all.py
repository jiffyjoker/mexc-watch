# Backtests 1-6 on public MEXC 15m klines + funding history. No keys. Read-only; does not touch live code.
import json,os,re,sys,time,urllib.request,bisect
sys.path.insert(0,'..'); from scan import EXCL
B='https://contract.mexc.com/api/v1/contract/';H={'User-Agent':'GrokBot/1.0'}
DAYS=int(os.environ.get('DAYS','14'));FEE=0.0002;CACHE='data.json'
def get(u):
    for i in range(4):
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(u,headers=H),timeout=20))
            if d.get('success',True): return d['data']
        except Exception: pass
        time.sleep(1+i)
    raise RuntimeError(u)
def fetch():
    if os.path.exists(CACHE): return json.load(open(CACHE))
    now=int(time.time());tk=[t for t in get(B+'ticker') if t['symbol'].endswith('_USDT') and float(t.get('amount24',0))>=1e7 and not re.search(EXCL,t['symbol'])]
    syms=[t['symbol'] for t in sorted(tk,key=lambda t:-float(t['amount24']))[:30]]
    if 'BTC_USDT' not in syms: syms.append('BTC_USDT')
    D={}
    for s in syms:
        k={'time':[],'open':[],'high':[],'low':[],'close':[],'vol':[]};st=now-(DAYS+1)*86400
        while st<now:
            en=min(st+1500*900,now);d=get(B+f'kline/{s}?interval=Min15&start={st}&end={en}')
            for f in k: k[f]+=d[f]
            st=en;time.sleep(0.15)   # ~7 req/s, well under 20 req/2s
        seen=set();idx=[i for i,t in enumerate(k['time']) if not (t in seen or seen.add(t))]
        k={f:[k[f][i] for i in idx] for f in k}
        fr=get(B+f'funding_rate/history?symbol={s}&page_num=1&page_size=100')['resultList'];time.sleep(0.15)
        D[s]=dict(k=k,fr=sorted((x['settleTime']//1000,x['fundingRate']) for x in fr))
        print('got',s,len(k['time']),flush=True)
    json.dump(D,open(CACHE,'w'));return D
D=fetch()
btc=D['BTC_USDT']['k'];bt={t:i for i,t in enumerate(btc['time'])}
def atr(k,i): return sum(k['high'][j]-k['low'][j] for j in range(i-13,i+1))/14
def sig_all(k,i,chg24):  # mirrors scan.signals but returns location flag instead of filtering on it
    hi,lo,cl,op,v=k['high'],k['low'],k['close'],k['open'],k['vol'];out=[]
    av=sum(v[i-96:i])/96 or 1;ph,pl=max(hi[i-96:i]),min(lo[i-96:i])
    if pl<=0 or (ph-pl)/pl>=0.07: return out
    loc=(cl[i-8]-pl)/(ph-pl) if ph>pl else .5
    if cl[i]>ph and cl[i-1]<=ph and cl[i]<=ph*1.01 and chg24>0 and v[i]>=3*av: out.append(('breakout','long',ph,0.5<=loc<=0.85))
    if cl[i]<pl and cl[i-1]>=pl and cl[i]>=pl*0.99 and chg24<0 and v[i]>=3*av: out.append(('breakout','short',pl,0.15<=loc<=0.5))
    for b in range(i-6,i-1):
        bh,bl=max(hi[b-96:b]),min(lo[b-96:b])
        if cl[b]>bh and cl[b-1]<=bh and chg24>0 and v[b]>=3*av and all(c>bh for c in cl[b:i+1]) and lo[i]<=bh*1.003 and cl[i]>op[i] and cl[i]<=bh*1.01: out.append(('retest','long',bh,True));break
        if cl[b]<bl and cl[b-1]>=bl and chg24<0 and v[b]>=3*av and all(c<bl for c in cl[b:i+1]) and hi[i]>=bl*0.997 and cl[i]<op[i] and cl[i]>=bl*0.99: out.append(('retest','short',bl,True));break
    if hi[i]>=ph*1.003 and cl[i]<ph and cl[i]<op[i] and v[i]>=2*av and chg24<0: out.append(('sweep','short',ph,True))
    if lo[i]<=pl*0.997 and cl[i]>pl and cl[i]>op[i] and v[i]>=2*av and chg24>0: out.append(('sweep','long',pl,True))
    return out
def sim(k,i,side,e,sl,mode):
    """Walk bars after i. Returns R net of fees. Intrabar: stop checked before target (conservative)."""
    L=side=='long';R=abs(e-sl);tp=e+1.5*R if L else e-1.5*R;stop=sl;half=0;trail=False;fee=2*FEE*e/R
    for j in range(i+1,min(i+97,len(k['time']))):
        h,l,c=k['high'][j],k['low'][j],k['close'][j]
        hitS=(l<=stop) if L else (h>=stop)
        if hitS: r=((stop-e) if L else (e-stop))/R; return (0.5*r+half if half else r)-fee
        if mode in('fixed','time','trail') and ((h>=tp) if L else (l<=tp)):
            if mode!='trail': return 1.5-fee
        if mode=='half' and not half and ((h>=e+R) if L else (l<=e-R)): half=0.5; trail=True
        g=(c-e) if L else (e-c)
        if mode in('trail','half') and (trail or g>=R):
            trail=True;a=atr(k,j);be=e*(1.0015 if L else 0.9985);ns=max(be,c-a) if L else min(be,c+a)
            stop=max(stop,ns) if L else min(stop,ns)
            if mode=='trail' and abs(tp-c)<0.3*R: tp=tp+R if L else tp-R
        if mode=='trail' and ((h>=tp) if L else (l<=tp)) and not trail: return 1.5-fee
        if mode=='time' and j-i>=16: return g/R-fee
    g=((c-e) if L else (e-c))/R; return (0.5*g+half if half else g)-fee
trades=[]
for s,d in D.items():
    k=d['k'];n=len(k['time']);last={};frt=[x[0] for x in d['fr']]
    for i in range(110,n-1):
        chg=k['close'][i]/k['close'][i-96]-1
        for sig,side,lvl,locok in sig_all(k,i,chg):
            key='level' if sig!='sweep' else 'sweep';ded=12*3600 if key=='level' else 6*3600
            t=k['time'][i]
            if t-last.get(key,-1e18)<ded: continue
            last[key]=t;e=k['close'][i];a=atr(k,i);L=side=='long'
            if sig=='sweep': st=(k['high'][i]+0.4*a) if not L else (k['low'][i]-0.4*a)
            else: st=(lvl-0.4*a) if L else (lvl+0.4*a)
            dist=min(max(abs(e-st)/e,0.012),0.03);st=e*(1-dist) if L else e*(1+dist)
            p=bisect.bisect_right(frt,t)-1;fr=d['fr'][p][1] if p>=0 else 0
            crowd=(L and fr>=0.0005) or ((not L) and fr<=-0.0005)
            bi=bt.get(t);bt4=None
            if bi and bi>=16: bt4=btc['close'][bi]/btc['close'][bi-16]-1
            tr=dict(t=t,sym=s,sig=sig,side=side,locok=locok,crowd=crowd,fr=fr,hourUTC=time.gmtime(t).tm_hour,
                    btc_with=None if s=='BTC_USDT' or bt4 is None else ((bt4>0)==L))
            for m in('fixed','trail','half','time'): tr[m]=round(sim(k,i,side,e,st,m),3)
            trades.append(tr)
trades.sort(key=lambda x:x['t'])
def st(rs):
    if not rs: return dict(n=0)
    eq=pk=dd=0
    for r in rs: eq+=r;pk=max(pk,eq);dd=max(dd,pk-eq)
    return dict(n=len(rs),win=round(100*sum(r>0 for r in rs)/len(rs),1),avgR=round(sum(rs)/len(rs),3),totR=round(sum(rs),2),maxDD_R=round(dd,2))
live=[x for x in trades if (x['sig']=='sweep' or (x['locok'] and not x['crowd']))]
O={'span_days':DAYS,'universe':len(D),'from':time.strftime('%Y-%m-%d',time.gmtime(trades[0]['t'])) if trades else None}
O['1_exits']={m:st([x[m] for x in live]) for m in('fixed','trail','half','time')}
def gate(name,f):
    blk=[x for x in trades if f(x)];return dict(blocked=len(blk),winners_blocked=sum(x['fixed']>0 for x in blk),losers_blocked=sum(x['fixed']<=0 for x in blk),blocked_avgR=st([x['fixed'] for x in blk]).get('avgR'),
      with_gate=st([x['fixed'] for x in trades if x['sig']=='sweep' or not f(x)]) if 0 else None)
lv=[x for x in trades if x['sig']!='sweep']
O['2_gates']={'all_breakout_retest_no_gates':st([x['fixed'] for x in lv]),
 'location':dict(pass_=st([x['fixed'] for x in lv if x['locok']]),blocked=st([x['fixed'] for x in lv if not x['locok']]),winners_blocked=sum(x['fixed']>0 for x in lv if not x['locok']),losers_blocked=sum(x['fixed']<=0 for x in lv if not x['locok'])),
 'funding':dict(pass_=st([x['fixed'] for x in lv if not x['crowd']]),blocked=st([x['fixed'] for x in lv if x['crowd']]),winners_blocked=sum(x['fixed']>0 for x in lv if x['crowd']),losers_blocked=sum(x['fixed']<=0 for x in lv if x['crowd'])),
 'oi':'not testable: MEXC has no free OI history; self-built oi.json only began 12 Oct (~hours), 0 historical trades have a 6h OI value'}
O['3_signals']={sg:{m:st([x[m] for x in live if x['sig']==sg]) for m in('fixed','trail')} for sg in('breakout','retest','sweep')}
O['3_signals']['btc_move/oi_surge']='not entries / no OI history'
def sess(h): return 'Asia 00-08Z (10am-6pm Bris)' if h<8 else 'London 08-13Z (6-11pm Bris)' if h<13 else 'US 13-21Z (11pm-7am Bris)' if h<21 else 'Late 21-24Z (7-10am Bris)'
O['4_sessions']={s_:st([x['fixed'] for x in live if sess(x['hourUTC'])==s_]) for s_ in sorted({sess(x['hourUTC']) for x in live})}
O['5_btc4h']={'with':st([x['fixed'] for x in live if x['btc_with'] is True]),'against':st([x['fixed'] for x in live if x['btc_with'] is False])}
def replay(rule,key='fixed'):
    eq=60.0;pk=eq;dd=0;streak=0;day=None;dl=0
    for x in live:
        d=time.strftime('%Y-%m-%d',time.gmtime(x['t']+36000))
        if d!=day: day,dl=d,0
        if rule=='rules' and dl>=3: continue
        r=(0.025 if streak>=2 else 0.05) if rule=='rules' else rule
        R=x[key];eq+=eq*r*R
        if R<=0: streak+=1;dl+=1
        else: streak=0
        pk=max(pk,eq);dd=max(dd,(pk-eq)/pk)
    return dict(end_equity=round(eq,2),max_dd_pct=round(100*dd,1))
O['6_sizing']={k_:{e:replay(v,e) for e in('fixed','trail')} for k_,v in (('RULES 5%/2.5% after 2L/3L daily brake','rules'),('flat 2.5%',0.025),('flat 5%',0.05))}
O['6_sizing']['note']='A+ 7% tier not mechanically identifiable (needs triad/1h judgement) so treated as 5%; trades replayed sequentially, overlap/max-3-open ignored'
json.dump(trades,open('trades_bt.json','w'));json.dump(O,open('results.json','w'),indent=1);print(json.dumps(O,indent=1))
