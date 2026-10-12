# Backtest 7: stop-distance sizing vs current rule, with realistic margin sequencing. Public klines only (data.json cache).
# Current: risk 5% (2.5% after 2 straight losses); skip if margin would leave < half the book free.
# Proposed: if that size doesn't fit, take the largest size that fits if it is >= 2.5% risk, else skip.
# Both: 20x isolated (10x if liq within 1.5x stop), max 3 open, one per coin, 3-loss daily brake, trail exit,
# BTC corr cap approx (same-direction risk of open trades with 4h-return corr>=0.7 vs BTC over prior 3 days <= 7.5%;
# a trade's risk drops to 0 once the trail has moved its stop to breakeven at +1R). Equity changes on close only.
import json,time,math,sys
sys.argv=[sys.argv[0]]
src=open('bt_all.py').read();exec(src[:src.index('trades=[]')])   # reuse data, signals, atr (no side effects)
def sim_trail(k,i,side,e,sl):
    L=side=='long';R=abs(e-sl);tp=e+1.5*R if L else e-1.5*R;stop=sl;trail=False;fee=2*FEE*e/R;be_t=None
    for j in range(i+1,min(i+97,len(k['time']))):
        h,l,c=k['high'][j],k['low'][j],k['close'][j]
        if (l<=stop) if L else (h>=stop): return ((stop-e) if L else (e-stop))/R-fee,k['time'][j],be_t
        g=(c-e) if L else (e-c)
        if trail or g>=R:
            if not trail: be_t=k['time'][j]
            trail=True;a=atr(k,j);be=e*(1.0015 if L else 0.9985);ns=max(be,c-a) if L else min(be,c+a)
            stop=max(stop,ns) if L else min(stop,ns)
            if abs(tp-c)<0.3*R: tp=tp+R if L else tp-R
        if ((h>=tp) if L else (l<=tp)) and not trail: return 1.5-fee,k['time'][j],be_t
    return ((c-e) if L else (e-c))/R-fee,k['time'][j],be_t
def corr(sym,t):
    if sym=='BTC_USDT': return 1.0
    a=D[sym]['k'];ia={x:i for i,x in enumerate(a['time'])};ts=[x for x in range(t-3*86400,t+1,3600) if x in ia and x in bt]
    if len(ts)<20: return 0.0
    ra=[a['close'][ia[ts[i]]]/a['close'][ia[ts[i-4]]]-1 for i in range(4,len(ts))];rb=[btc['close'][bt[ts[i]]]/btc['close'][bt[ts[i-4]]]-1 for i in range(4,len(ts))]
    n=len(ra);ma,mb=sum(ra)/n,sum(rb)/n;cv=sum((x-ma)*(y-mb) for x,y in zip(ra,rb));va=sum((x-ma)**2 for x in ra);vb=sum((y-mb)**2 for y in rb)
    return cv/math.sqrt(va*vb) if va and vb else 0.0
sig=[]
for s,d in D.items():
    k=d['k'];n=len(k['time']);last={};frt=[x[0] for x in d['fr']]
    for i in range(110,n-1):
        chg=k['close'][i]/k['close'][i-96]-1
        for sg,side,lvl,locok in sig_all(k,i,chg):
            key='level' if sg!='sweep' else 'sweep';ded=12*3600 if key=='level' else 6*3600;t=k['time'][i]
            if t-last.get(key,-1e18)<ded: continue
            last[key]=t;e=k['close'][i];a=atr(k,i);L=side=='long'
            st=((k['high'][i]+0.4*a) if not L else (k['low'][i]-0.4*a)) if sg=='sweep' else ((lvl-0.4*a) if L else (lvl+0.4*a))
            dist=min(max(abs(e-st)/e,0.012),0.03);st=e*(1-dist) if L else e*(1+dist)
            p=bisect.bisect_right(frt,t)-1;fr=d['fr'][p][1] if p>=0 else 0
            crowd=(L and fr>=0.0005) or ((not L) and fr<=-0.0005)
            if not (sg=='sweep' or (locok and not crowd)): continue
            R,tx,be=sim_trail(k,i,side,e,st)
            sig.append(dict(t=t,sym=s,side=side,dist=dist,R=R,tx=tx,be=be,c=corr(s,t)))
sig.sort(key=lambda x:x['t'])
def lev(dist,mmr=0.0023):
    for L_ in (20,10,5):
        if (1/L_-mmr)/(1+mmr)>=1.5*dist: return L_
def run(rule):
    eq=60.0;pk=eq;dd=0;opn=[];res=[];streak=0;day=None;dl=0;skips={}
    def close_until(t):
        nonlocal eq,pk,dd,streak,dl
        for o in sorted([o for o in opn if o['tx']<=t],key=lambda o:o['tx']):
            opn.remove(o);pnl=o['risk$']*o['R'];eq+=pnl;res.append(dict(R=o['R'],pnl=pnl,risk=o['rp']))
            streak=streak+1 if o['R']<=0 else 0
            if o['R']<=0 and time.strftime('%Y-%m-%d',time.gmtime(o['tx']+36000))==day: dl+=1
            pk=max(pk,eq);dd=max(dd,(pk-eq)/pk)
    for x in sig:
        close_until(x['t']);d=time.strftime('%Y-%m-%d',time.gmtime(x['t']+36000))
        if d!=day: day,dl=d,0
        sk=lambda r: skips.__setitem__(r,skips.get(r,0)+1)
        if dl>=3: sk('brake');continue
        if len(opn)>=3: sk('max3');continue
        if any(o['sym']==x['sym'] for o in opn): sk('same_coin');continue
        base=2.5 if streak>=2 else 5.0
        if x['c']>=0.7:
            cr=sum(o['rp'] for o in opn if o['side']==x['side'] and o['c']>=0.7 and not (o['be'] and o['be']<=x['t']))
            if cr+base>7.5+1e-9: sk('corr_cap');continue
        lv=lev(x['dist']);used=sum(o['m'] for o in opn);avail=eq-used;free=avail-eq/2
        need=eq*base/100/x['dist']/lv
        if need<=free: rp=base
        elif rule=='fit':
            fit=free*lv*x['dist']/eq*100
            if fit>=2.5: rp=fit
            else: sk('half_book');continue
        else: sk('half_book');continue
        m=eq*rp/100/x['dist']/lv
        opn.append(dict(x,rp=rp,m=m,**{'risk$':eq*rp/100}))
    close_until(1e18)
    w=sum(r['R']>0 for r in res)
    return dict(trades=len(res),win_pct=round(100*w/len(res),1),avg_R=round(sum(r['R'] for r in res)/len(res),3),total_R=round(sum(r['R'] for r in res),2),
                reduced_size_trades=sum(r['risk']<4.999 for r in res),total_usd=round(eq-60,2),end_equity=round(eq,2),max_dd_pct=round(100*dd,1),skips=skips)
O=dict(span_days=DAYS,signals=len(sig),from_=time.strftime('%Y-%m-%d',time.gmtime(sig[0]['t'])),to=time.strftime('%Y-%m-%d',time.gmtime(sig[-1]['t'])),
       stop_dist_pct=dict(min=round(100*min(x['dist'] for x in sig),2),median=round(100*sorted(x['dist'] for x in sig)[len(sig)//2],2)),
       current=run('current'),stop_distance_fit=run('fit'))
json.dump(O,open('results_sizing.json','w'),indent=1);print(json.dumps(O,indent=1))
