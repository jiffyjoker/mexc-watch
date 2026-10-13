#!/usr/bin/env python3
"""Estimated liquidation heatmap (CoinGlass/Hyblock-style model) from Binance vision 5m metrics only.
price = sum_open_interest_value / sum_open_interest. Each 5m OI increase = new positions opened at that price,
split long/short by global account L/S ratio, spread over leverage tiers; liq px = entry*(1 -/+ 1/lev + mmr).
OI decreases close existing bands pro-rata; bands are wiped when price trades through them.
Output per bar: USD of estimated long-liq below and short-liq above within +-1/2/5%.  Usage: liq_heatmap.py SYM"""
import sys,os,zipfile,csv,io,glob,json
TIERS={5:.15,10:.30,20:.25,25:.15,50:.10,100:.05}; MMR=0.004
def load(sym):
    rows=[]
    for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)),'vision_metrics',sym,'*.zip'))):
        z=zipfile.ZipFile(f)
        for r in csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]))):
            try: oi=float(r['sum_open_interest']); v=float(r['sum_open_interest_value']); ls=float(r['count_long_short_ratio'] or 1)
            except: continue
            if oi>0: rows.append((r['create_time'],v/oi,oi,ls))
    return rows
def run(sym):
    rows=load(sym); bands=[]  # [liqpx, side, usd]
    out=[]; prev=None
    for t,px,oi,ls in rows:
        if prev:
            # wipe crossed bands (approx: between prev px and px)
            lo,hi=min(prev[1],px),max(prev[1],px)
            bands=[b for b in bands if not (lo<=b[0]<=hi)]
            d=(oi-prev[2])*px
            if d>0:
                fl=ls/(1+ls)
                for lev,wt in TIERS.items():
                    bands.append([px*(1-1/lev+MMR),'L',d*fl*wt]); bands.append([px*(1+1/lev-MMR),'S',d*(1-fl)*wt])
            elif d<0:
                k=max(0,oi/prev[2])
                for b in bands: b[2]*=k
            bands=[b for b in bands if b[2]>1]
        r={'t':t,'px':round(px,6)}
        for p in (1,2,5):
            r[f'L{p}']=round(sum(b[2] for b in bands if b[1]=='L' and b[0]>=px*(1-p/100)))
            r[f'S{p}']=round(sum(b[2] for b in bands if b[1]=='S' and b[0]<=px*(1+p/100)))
        out.append(r); prev=(t,px,oi)
    return out
if __name__=='__main__':
    o=run(sys.argv[1]); print(len(o),'bars'); [print(x) for x in o[-3:]]
