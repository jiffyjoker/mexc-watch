#!/usr/bin/env python3
"""Low-risk follow-up to bt_select.py (pre-registered 14 Oct): N3 rank oi6 and N5 first + same-side cap 2 at 0.5/0.75/1% risk."""
import os,time,json
H=os.path.dirname(os.path.abspath(__file__))
src=open(f'{H}/bt_select.py').read().split('MID=')[0];g={'__file__':f'{H}/bt_select.py'};exec(compile(src,'bt_select','exec'),g)
bk=g['bk'];run=g['run'];MID=(bk[0]['t']+bk[-1]['t'])/2;yrs=sorted({time.gmtime(x['t']).tm_year for x in bk})
out=[]
for name,N,key,cap in (('N3 oi6',3,'oi6',None),('N5 first cap2',5,'first',2)):
    for r in (0.5,0.75,1.0):
        a=dict(v=name,risk=r,all=run(N,r,key,cap),h1=run(N,r,key,cap,t1=MID),h2=run(N,r,key,cap,t0=MID))
        a['years']={y:run(N,r,key,cap,t0=time.mktime((y,1,1,0,0,0,0,0,0))-time.timezone,t1=time.mktime((y+1,1,1,0,0,0,0,0,0))-time.timezone)['cagr'] for y in yrs}
        out.append(a);print(name,r,a['all'],'| H1',a['h1']['cagr'],a['h1']['mdd'],'| H2',a['h2']['cagr'],a['h2']['mdd'],a['h2']['avgR'],'|',a['years'],flush=True)
json.dump(out,open(f'{H}/bt_select2.json','w'),indent=1,default=float)
