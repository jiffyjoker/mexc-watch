#!/usr/bin/env python3
"""Multi-year backtest of pre-registered signals on free Binance history (paper research only, read-only).
Pre-registered parameters (written before any result was seen, 14 Oct 2026):
 breakout = live rules (24h range<7%, 15m close break, chase<=1%, vol>=3x, day side, arm loc, funding gate, point-in-time top-30, 12h dedupe)
   gates: OI6h<-1% drop; taker share of the signal bar against side drop; DVOL split (BTC DVOL vs trailing 365d median)
 oi_surge = live rule: OI 1h >= +15%, 1h price move >0.3% in day direction, taker agrees -> day side
 R trades exit with papersim (= guard.py trail, 4R TP), taker 0.02%/side, funding charged in R.
 fixed-hold (% of notional, 0.04% round trip + funding): lsr_global / lsr_top contrarian |z30d|>2 hold 24h;
   taker 1h flow z30d>2.5 continuation hold 4h; F&G <=20 long / >=80 short BTC hold 7d;
   Coinbase premium 24h-avg z30d>2 long BTC / <-2 short hold 24h;
   heatmap magnet: est. liq imbalance within 5% >0.5 -> trade toward the bigger cluster hold 24h;
   heatmap sweep-reverse: 1h bar wipes est. liq > p95(30d) of one side -> fade hold 12h.
 Pass = mean>0 in H1 and H2, H2 t>=2, >=75% of years (n>=20) positive."""
import os,sys,glob,io,zipfile,json,time,bisect,collections,numpy as np,pandas as pd
H=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,os.path.dirname(H));import papersim as S
FEE=0.0004
def load(s):
    p=f'{H}/npz/{s}.npz'
    if os.environ.get('SAVE') and os.path.exists(p): return dict(np.load(p))
    fs=sorted(glob.glob(f'{H}/vision_klines15m/{s}/*.zip'))
    if not fs: return None
    ks=[]
    for f in fs:
        z=zipfile.ZipFile(f);d=pd.read_csv(z.open(z.namelist()[0]),header=None)
        if str(d.iloc[0,0]).startswith('open'): d=d.iloc[1:]
        ks.append(d.iloc[:,[0,1,2,3,4,7,10]].astype(float))
    k=pd.concat(ks).drop_duplicates(0).sort_values(0).values
    out=dict(t=(k[:,0]//1000).astype(np.int64),o=k[:,1],h=k[:,2],l=k[:,3],c=k[:,4],qv=k[:,5],tb=k[:,6])
    ms=[]
    for f in sorted(glob.glob(f'{H}/vision_metrics/{s}/*.zip')):
        try:
            z=zipfile.ZipFile(f);ms.append(pd.read_csv(z.open(z.namelist()[0])))
        except Exception: pass
    ct=out['t']+900
    if ms:
        m=pd.concat(ms);m['ts']=(pd.to_datetime(m['create_time'])-pd.Timestamp('1970-01-01'))//pd.Timedelta(seconds=1);m=m.sort_values('ts').drop_duplicates('ts')
        idx=np.searchsorted(m['ts'].values,ct,side='right')-1;ok=(idx>=0)&(ct-m['ts'].values[np.clip(idx,0,None)]<=1800)
        for a,b in (('oi','sum_open_interest'),('gls','count_long_short_ratio'),('tls','sum_toptrader_long_short_ratio')):
            v=pd.to_numeric(m[b],errors='coerce').values[np.clip(idx,0,None)].astype(float);v[~ok]=np.nan;out[a]=v
    else:
        for a in ('oi','gls','tls'): out[a]=np.full(len(ct),np.nan)
    fp=f'{H}/funding/binance_{s}.json';fu=json.load(open(fp)) if os.path.exists(fp) else []
    out['ft']=np.array([x[0]//1000 for x in fu],dtype=np.int64);out['fr']=np.array([x[1] for x in fu])
    if os.environ.get('SAVE'): np.savez(p,**out)
    return out
syms=sorted(os.listdir(f'{H}/vision_klines15m'))
C={}
for s in syms:
    d=load(s)
    if d is not None and len(d['t'])>2000: C[s]=d
print('coins',len(C),flush=True)
def fund_between(d,t0,t1):
    a,b=np.searchsorted(d['ft'],[t0,t1],side='right');return float(d['fr'][a:b].sum())
# ---- point-in-time top-30 by 24h quote volume, hourly
for s,d in C.items(): d['qv24']=pd.Series(d['qv']).rolling(96).sum().values;d['ix']={int(t):i for i,t in enumerate(d['t'])}
hours=sorted({int(t) for d in C.values() for t in d['t'][::4]});rank={}
for th in hours:
    v=[]
    for s,d in C.items():
        i=d['ix'].get(th)
        if i is not None and i>=96: v.append((d['qv24'][i],s))
    v.sort(reverse=True);rank[th]={s for _,s in v[:30]}
# ---- DVOL
dv=json.load(open(f'{H}/dvol_BTC_1h.json'));dvt=np.array([x[0]//1000 for x in dv]);dvc=np.array([x[4] for x in dv])
dvmed=pd.Series(dvc).rolling(24*365,min_periods=24*90).median().values
def dvol_hi(t):
    j=np.searchsorted(dvt,t,side='right')-1
    if j<0 or np.isnan(dvmed[j]): return None
    return bool(dvc[j]>dvmed[j])
# ---- R simulation
def simR(s,i,side):
    d=C[s];L=side=='long';e=d['c'][i];atr=pd.Series(d['h'][max(0,i-13):i+1]-d['l'][max(0,i-13):i+1]).mean()
    _,sp=S.rules_stop(L,e,d['h'][i],d['l'][i],atr);p=S.open_pos('x',side,e,sp,1000,5,1e-6,0.004)
    if p['status']!='open': return None
    hl=d['h']-d['l']
    for j in range(i+1,min(len(d['c'])-1,i+96*14)):
        a=hl[max(0,j-14):j].mean()
        if S.step(p,d['h'][j],d['l'][j],d['c'][j],a): break
    else: S.close_pos(p,d['c'][j],'timeout')
    t0=d['t'][i]+900;t1=d['t'][j]+900
    fR=fund_between(d,t0,t1)*(1 if L else -1)/(sp/100 if sp>1 else sp)  # longs pay positive funding
    return p['R_net']-fR,t1
def breakouts(s,d):
    c,h,l,qv,tb=d['c'],d['h'],d['l'],d['qv'],d['tb'];n=len(c);out=[];last=0
    ph=pd.Series(h).rolling(96).max().shift(1).values;pl=pd.Series(l).rolling(96).min().shift(1).values
    av=pd.Series(qv).rolling(96).mean().shift(1).values
    for i in np.nonzero(((c>ph)&(np.roll(c,1)<=ph))|((c<pl)&(np.roll(c,1)>=pl)))[0]:
        if i<200 or i>=n-2: continue
        t=int(d['t'][i])+900
        if s not in rank.get((t-900)//3600*3600,()): continue
        if (ph[i]-pl[i])/pl[i]>=0.07: continue
        L=c[i]>ph[i];lvl=ph[i] if L else pl[i]
        if abs(c[i]/lvl-1)>0.01 or qv[i]<3*av[i]: continue
        day=c[i]/c[i-96]-1
        if (L and day<=0) or (not L and day>=0): continue
        al=(c[i-8]-pl[i])/(ph[i]-pl[i])
        if (L and not .5<=al<=.85) or (not L and not .15<=al<=.5): continue
        if len(d['ft']):
            j=np.searchsorted(d['ft'],t,side='right')-1
            if j>=0 and ((L and d['fr'][j]>=0.0005) or (not L and d['fr'][j]<=-0.0005)): continue
        if t-last<12*3600: continue
        last=t;o6=d['oi'][i]/d['oi'][i-24]-1 if i>=24 and d['oi'][i-24]>0 else np.nan
        tks=tb[i]/qv[i] if qv[i]>0 else np.nan
        out.append(dict(t=t,s=s,i=int(i),side='long' if L else 'short',oi6=o6,tk=tks,dvhi=dvol_hi(t)))
    return out
def oisurge(s,d):
    c,oi=d['c'],d['oi'];out=[];last=0
    for i in range(100,len(c)-2):
        if np.isnan(oi[i]) or np.isnan(oi[i-4]) or oi[i-4]<=0: continue
        o1=oi[i]/oi[i-4]-1
        if o1<0.15: continue
        day=c[i]/c[i-96]-1;p1=c[i]/c[i-4]-1;t=int(d['t'][i])+900
        if not((day>0 and p1>0.003) or (day<0 and p1<-0.003)): continue
        L=day>0;tk=d['tb'][i]/d['qv'][i] if d['qv'][i]>0 else .5
        if (L and tk<.5) or (not L and tk>.5): continue
        if t-last<6*3600: continue
        last=t;out.append(dict(t=t,s=s,i=i,side='long' if L else 'short'))
    return out
# ---- fixed-hold helper (hourly decision points)
def hold(s,i,side,bars):
    d=C[s];j=min(i+bars,len(d['c'])-1);r=(d['c'][j]/d['c'][i]-1)*(1 if side=='long' else -1)-FEE
    r-=fund_between(d,d['t'][i]+900,d['t'][j]+900)*(1 if side=='long' else -1);return r*100,int(d['t'][j])+900
def zsig(s,arr,thr,bars,contra,win=2880,step=4):
    d=C[s];x=pd.Series(arr);z=((x-x.rolling(win,min_periods=win//2).mean())/x.rolling(win,min_periods=win//2).std()).values
    out=[];busy=0
    for i in range(win//2,len(z)-1,step):
        t=int(d['t'][i])+900
        if t<busy or np.isnan(z[i]) or abs(z[i])<thr: continue
        side=('short' if z[i]>0 else 'long') if contra else ('long' if z[i]>0 else 'short')
        r,busy=hold(s,i,side,bars);out.append((t,r,s,side))
    return out
# ---- heatmap (log-price buckets 0.25%, hourly)
TI={5:.15,10:.30,20:.25,25:.15,50:.10,100:.05};MMR=0.004
def heat(s):
    d=C[s];c,h,l,oi,gls=d['c'],d['h'],d['l'],d['oi'],d['gls'];g=np.log(1.0025)
    base=np.log(np.nanmin(l))-0.7;nb=int((np.log(np.nanmax(h))+0.7-base)/g)+2
    Lb=np.zeros(nb);Sb=np.zeros(nb);B=lambda p:np.clip(((np.log(p)-base)/g).astype(int) if isinstance(p,np.ndarray) else int((np.log(p)-base)/g),0,nb-1)
    rec=[];po=None
    for i in range(0,len(c)-4,4):
        hi=h[i:i+4].max();lo=l[i:i+4].min();px=c[i+3];o=oi[i+3]
        wl=Lb[B(lo):].sum();ws=Sb[:B(hi)+1].sum();Lb[B(lo):]=0;Sb[:B(hi)+1]=0
        if not np.isnan(o) and po:
            dd=(o-po)*px
            if dd>0:
                f=gls[i+3]/(1+gls[i+3]) if not np.isnan(gls[i+3]) else .5
                for lev,w in TI.items():
                    Lb[B(px*(1-1/lev+MMR))]+=dd*f*w;Sb[B(px*(1+1/lev-MMR))]+=dd*(1-f)*w
            elif dd<0: k=max(0,o/po);Lb*=k;Sb*=k
        if not np.isnan(o): po=o
        b0,b1,b2=B(px*0.95),B(px),B(px*1.05);l5=Lb[b0:b1+1].sum();s5=Sb[b1:b2+1].sum()
        rec.append((i+3,l5,s5,wl,ws))
    return rec
def heat_sigs(s):
    d=C[s];rec=heat(s);mg=[];sw=[];busy1=busy2=0;wl=collections.deque(maxlen=720);ws=collections.deque(maxlen=720)
    for i,l5,s5,a,b in rec:
        t=int(d['t'][i])+900;tot=l5+s5
        if len(wl)>=360 and not np.isnan(d['oi'][i]):
            if tot>0 and t>=busy1:
                im=(l5-s5)/tot
                if abs(im)>0.5: r,busy1=hold(s,i,'short' if im>0 else 'long',96);mg.append((t,r,s,'short' if im>0 else 'long'))
            if t>=busy2:
                pa=np.percentile(wl,95);pb=np.percentile(ws,95)
                if a>pa and a>0 and a>=b: r,busy2=hold(s,i,'long',48);sw.append((t,r,s,'long'))
                elif b>pb and b>0: r,busy2=hold(s,i,'short',48);sw.append((t,r,s,'short'))
        wl.append(a);ws.append(b)
    return mg,sw
# ---- stats
def stats(tr):
    r=np.array([x[1] for x in tr]) if tr else np.array([])
    if len(r)<2: return dict(n=len(r),mean=None,t=None)
    return dict(n=len(r),mean=round(float(r.mean()),4),t=round(float(r.mean()/(r.std(ddof=1)/np.sqrt(len(r)))),2),net=round(float(r.sum()),1),win=round(float((r>0).mean()),3))
def evaluate(name,tr,unit):
    tr=sorted(tr)
    if len(tr)<10: return dict(name=name,unit=unit,all=stats(tr),verdict='too few')
    mid=(tr[0][0]+tr[-1][0])/2;h1=stats([x for x in tr if x[0]<mid]);h2=stats([x for x in tr if x[0]>=mid])
    yrs={};
    for y in sorted({time.gmtime(x[0]).tm_year for x in tr}): yrs[y]=stats([x for x in tr if time.gmtime(x[0]).tm_year==y])
    yv=[v['mean'] for v in yrs.values() if v['n']>=20 and v['mean'] is not None]
    ok=h1['mean'] is not None and h2['mean'] is not None and h1['mean']>0 and h2['mean']>0 and (h2['t'] or 0)>=2 and yv and sum(m>0 for m in yv)/len(yv)>=.75
    return dict(name=name,unit=unit,span=[time.strftime('%Y-%m-%d',time.gmtime(tr[0][0])),time.strftime('%Y-%m-%d',time.gmtime(tr[-1][0]))],all=stats(tr),h1=h1,h2=h2,years=yrs,verdict='PASS' if ok else 'fail')
def one_pos(trs):
    out=[];busy=0
    for x in sorted(trs):
        if x[0]>=busy: out.append(x[:4]);busy=x[4]
    return out
R=[]
# breakouts
bk=[];[bk.extend(breakouts(s,d)) for s,d in C.items()];bk.sort(key=lambda x:x['t'])
print('breakout cands',len(bk),flush=True)
for x in bk:
    r=simR(x['s'],x['i'],x['side']);x['R'],x['t1']=(r if r else (None,None))
bk=[x for x in bk if x['R'] is not None]
T=lambda xs:[(x['t'],x['R'],x['s'],x['side'],x['t1']) for x in xs]
gO=lambda x:not(x['oi6']<-0.01) if not np.isnan(x['oi6']) else True
gT=lambda x:np.isnan(x['tk']) or not((x['side']=='long' and x['tk']<.5) or (x['side']=='short' and x['tk']>.5))
var={'breakout base (no OI/taker gate)':bk,'breakout +OI6h gate':[x for x in bk if gO(x)],'breakout +taker gate':[x for x in bk if gT(x)],
 'breakout FULL live (OI+taker)':[x for x in bk if gO(x) and gT(x)],'breakout full + DVOL above 1y median':[x for x in bk if gO(x) and gT(x) and x['dvhi'] is True],
 'breakout full + DVOL below 1y median':[x for x in bk if gO(x) and gT(x) and x['dvhi'] is False],
 'breakout full, OI-covered bars only':[x for x in bk if not np.isnan(x['oi6']) and gO(x) and gT(x)],'breakout base, OI-covered bars only':[x for x in bk if not np.isnan(x['oi6'])]}
for k,v in var.items():
    R.append(evaluate(k+' [all signals]','R',T(v)) if False else evaluate(k+' [all signals]',[t[:4] for t in T(v)],'R'))
    R.append(evaluate(k+' [one position]',one_pos(T(v)),'R'))
os_=[];[os_.extend(oisurge(s,d)) for s,d in C.items()]
ost=[]
for x in os_:
    r=simR(x['s'],x['i'],x['side'])
    if r: ost.append((x['t'],r[0],x['s'],x['side']))
R.append(evaluate('oi_surge (live rule)',ost,'R'))
print('R done',flush=True)
# fixed hold
g=[];tt=[];tk=[];mg=[];sw=[]
for s,d in C.items():
    g+=zsig(s,d['gls'],2,96,True);tt+=zsig(s,d['tls'],2,96,True)
    f1=pd.Series(d['tb']).rolling(4).sum().values;f2=pd.Series(d['qv']).rolling(4).sum().values
    tk+=zsig(s,np.where(f2>0,f1/np.where(f2>0,f2,1),np.nan),2.5,16,False)
    if np.isfinite(d['oi']).sum()>2000:
        a,b=heat_sigs(s);mg+=a;sw+=b
R.append(evaluate('global L/S contrarian |z|>2 hold 24h','%' and g,'%'))
R.append(evaluate('top-trader L/S contrarian |z|>2 hold 24h',tt,'%'))
R.append(evaluate('taker 1h flow z>2.5 continuation hold 4h',tk,'%'))
R.append(evaluate('heatmap magnet imbalance>0.5 hold 24h',mg,'%'))
R.append(evaluate('heatmap sweep-reverse p95 hold 12h',sw,'%'))
# F&G
fg=json.load(open(f'{H}/fear_greed.json'));fg=sorted((int(x['timestamp']),int(x['value'])) for x in fg)
for sym in ('BTC','ETH'):
    d=C.get(sym);out=[];busy=0
    if d is None: continue
    for ts,v in fg:
        i=d['ix'].get(ts)
        if i is None or ts<busy: continue
        if v<=20: r,busy=hold(sym,i,'long',96*7);out.append((ts,r,sym,'long'))
        elif v>=80: r,busy=hold(sym,i,'short',96*7);out.append((ts,r,sym,'short'))
    R.append(evaluate(f'Fear&Greed <=20 long / >=80 short {sym} hold 7d',out,'%'))
# Coinbase premium
cb=json.load(open(f'{H}/coinbase_btcusd_1h.json'));bn=json.load(open(f'{H}/binance_btcusdt_spot_1h.json'))
cbs=pd.Series({int(x[0]):float(x[4]) for x in cb});bns=pd.Series({int(x[0])//1000:float(x[4]) for x in bn})
pr=(cbs/bns-1).dropna().sort_index();p24=pr.rolling(24).mean();z=(p24-p24.rolling(720,min_periods=360).mean())/p24.rolling(720,min_periods=360).std()
d=C['BTC'];out=[];busy=0
for ts,zz in z.dropna().items():
    tc=ts+3600;i=d['ix'].get(tc-900)
    if i is None or tc<busy or abs(zz)<2: continue
    side='long' if zz>0 else 'short';r,busy=hold('BTC',i,side,96);out.append((tc,r,'BTC',side))
R.append(evaluate('Coinbase premium z>2 follow, BTC hold 24h',out,'%'))
json.dump(R,open(f'{H}/bt_multi.json','w'),indent=1,default=str)
for r in R:
    a=r['all'];h1=r.get('h1',{});h2=r.get('h2',{});yv={y:v['mean'] for y,v in r.get('years',{}).items()}
    print(f"{r['verdict']:4} {r['name'][:60]:60} {r['unit']} n{a['n']} avg{a['mean']} t{a['t']} | H1 {h1.get('mean')} | H2 {h2.get('mean')} t{h2.get('t')} | {yv}")
