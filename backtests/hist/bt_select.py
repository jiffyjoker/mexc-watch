#!/usr/bin/env python3
"""Signal-SELECTION backtest on multi-year Binance data (paper research, no live effect).
Candidates = live breakout rules + OI6h + taker gates (from bt_multi.py). Pre-registered variants (14 Oct 2026, before results):
 max concurrent N in {1,2,3,5}, risk 5%/N per trade and 2.5% fixed; selection within the same 15m bar ranked by
 first-come(alphabetical), volume multiple, OI 6h change, arm-time location (best = deepest in favour), distance past level (smallest);
 same-direction cap 2 (BTC-correlation cap); US session 13-21 UTC. Sizing: small start equity, MEXC contract size (today) min 1 contract,
 20x isolated, margin <= half equity. Pick on H1, validate on H2 + per year."""
import os,sys,json,time,math,collections,numpy as np
H=os.path.dirname(os.path.abspath(__file__));os.environ['SAVE']='1'
src=open(f'{H}/bt_multi.py').read().split('R=[]')[0]
src=src.replace("out.append(dict(t=t,s=s,i=int(i),side='long' if L else 'short',oi6=o6,tk=tks,dvhi=dvol_hi(t)))",
 "out.append(dict(t=t,s=s,i=int(i),side='long' if L else 'short',oi6=o6,tk=tks,dvhi=dvol_hi(t),vm=qv[i]/av[i],dist=abs(c[i]/lvl-1),loc=(al if L else 1-al)))")
g={'__file__':f'{H}/bt_multi.py'};exec(compile(src,'bt_multi','exec'),g)
C=g['C'];bk=[];[bk.extend(g['breakouts'](s,d)) for s,d in C.items()]
gO=lambda x:np.isnan(x['oi6']) or x['oi6']>=-0.01
gT=lambda x:np.isnan(x['tk']) or not((x['side']=='long' and x['tk']<.5) or (x['side']=='short' and x['tk']>.5))
bk=[x for x in bk if gO(x) and gT(x)]
for x in bk:
    r=g['simR'](x['s'],x['i'],x['side'])
    x['R'],x['t1']=r if r else (None,None)
    d=C[x['s']];e=d['c'][x['i']];x['px']=e
    atr=float(np.mean(d['h'][max(0,x['i']-13):x['i']+1]-d['l'][max(0,x['i']-13):x['i']+1]))
    x['sp']=g['S'].rules_stop(x['side']=='long',e,d['h'][x['i']],d['l'][x['i']],atr)[1]
bk=[x for x in bk if x['R'] is not None];bk.sort(key=lambda x:(x['t'],x['s']))
print('cands',len(bk),flush=True)
CS=json.load(open(f'{H}/mexc_cs.json'))
KEYS={'first':lambda x:0,'volmult':lambda x:-x['vm'],'oi6':lambda x:-(x['oi6'] if not np.isnan(x['oi6']) else -9),'location':lambda x:-x['loc'],'dist':lambda x:x['dist']}
def run(N,risk,key='first',samecap=None,us=False,eq0=65.0,t0=None,t1=None):
    eq=eq0;pk=eq;mdd=0;opn=[];tr=[];rej=0
    by=collections.OrderedDict()
    for x in bk:
        if (t0 and x['t']<t0) or (t1 and x['t']>=t1): continue
        if us and not 13<=time.gmtime(x['t']).tm_hour<21: continue
        by.setdefault(x['t'],[]).append(x)
    for t,xs in by.items():
        # close finished
        for p in sorted([p for p in opn if p['t1']<=t],key=lambda p:p['t1']):
            eq+=p['pnl'];opn.remove(p);pk=max(pk,eq);mdd=max(mdd,(pk-eq)/pk)
        for x in sorted(xs,key=KEYS[key]):
            if len(opn)>=N: break
            if any(p['s']==x['s'] for p in opn): continue
            if samecap and sum(p['side']==x['side'] for p in opn)>=samecap: continue
            cs=CS.get(x['s'],(None,1))[0]
            if not cs: rej+=1;continue
            ru=eq*risk/100;vol=math.floor(ru/(x['px']*x['sp']/100*cs))
            if vol<1: rej+=1;continue
            margin=vol*cs*x['px']/20
            if margin+sum(p['m'] for p in opn)>eq/2: rej+=1;continue
            ra=vol*cs*x['px']*x['sp']/100
            opn.append(dict(s=x['s'],side=x['side'],t1=x['t1'],pnl=x['R']*ra,m=margin));tr.append((t,x['R']))
        if eq<5: break
    for p in opn: eq+=p['pnl']
    pk=max(pk,eq);mdd=max(mdd,(pk-eq)/pk)
    T0=t0 or bk[0]['t'];T1=t1 or bk[-1]['t'];yrs=(T1-T0)/31557600
    r=[R for _,R in tr]
    return dict(n=len(r),pd=round(len(r)/((T1-T0)/86400),2),avgR=round(float(np.mean(r)),3) if r else None,
      end=round(eq,2),cagr=round(((eq/eq0)**(1/yrs)-1)*100,1) if eq>0 and yrs>0 else None,mdd=round(mdd*100,1),rej=rej)
MID=(bk[0]['t']+bk[-1]['t'])/2
V=[]
for N in (1,2,3,5):
    for rk in ('5/N','2.5'):
        risk=5/N if rk=='5/N' else 2.5
        for key in KEYS:
            V.append(dict(N=N,risk=rk,key=key,cap=None,us=False))
for N in (2,3,5): V.append(dict(N=N,risk='5/N',key='first',cap=2,us=False))
for N in (1,3): V.append(dict(N=N,risk='5/N',key='first',cap=None,us=True))
out=[]
yrs=sorted({time.gmtime(x['t']).tm_year for x in bk})
for v in V:
    risk=5/v['N'] if v['risk']=='5/N' else 2.5
    a=dict(N=v['N'],risk=v['risk'],key=v['key'],cap=v['cap'],us=v['us'])
    a['all']=run(v['N'],risk,v['key'],v['cap'],v['us'])
    a['h1']=run(v['N'],risk,v['key'],v['cap'],v['us'],t1=MID);a['h2']=run(v['N'],risk,v['key'],v['cap'],v['us'],t0=MID)
    a['years']={y:run(v['N'],risk,v['key'],v['cap'],v['us'],t0=time.mktime((y,1,1,0,0,0,0,0,0))-time.timezone,t1=time.mktime((y+1,1,1,0,0,0,0,0,0))-time.timezone)['avgR'] for y in yrs}
    out.append(a)
    print(f"N{a['N']} risk{a['risk']:4} {a['key']:9} cap{a['cap']} us{int(a['us'])} | ALL {a['all']} | H1 {a['h1']['avgR']} cagr{a['h1']['cagr']} dd{a['h1']['mdd']} | H2 {a['h2']['avgR']} cagr{a['h2']['cagr']} dd{a['h2']['mdd']} | {a['years']}",flush=True)
json.dump(out,open(f'{H}/bt_select.json','w'),indent=1)
