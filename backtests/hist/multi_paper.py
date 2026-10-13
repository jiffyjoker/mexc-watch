#!/usr/bin/env python3
"""PAPER ONLY multi-position sim (adopted to paper 14 Oct from bt_select2: N3, 0.5% risk, rank same-bar ties by OI 6h rise).
Every 5 min re-derives from paper/book.json (which simulates every wake with guard exits): takes breakout wakes that
passed the live prefilters (no 'prefilter' in real_reasons), max 3 open, one per coin, 0.5% of equity risk each, compounding
from the paper start equity, margin <= half equity. Writes paper/multi_book.json. No orders, no wakes, no private API."""
import json,os,time
for k in list(os.environ):
    if k.startswith('MEXC_'): del os.environ[k]
P=os.path.dirname(os.path.abspath(__file__));N=3;RISK=0.5
def oi6(sym,t):
    try: return json.load(open(os.path.join(P,'..','state.json'))).get('oi',{}).get(sym,{}).get('oi_6h_pct') or 0
    except Exception: return 0
def build():
    b=json.load(open(f'{P}/book.json'));eq0=b['start_equity'];eq=eq0;pk=eq;mdd=0;opn=[];taken=[];skipped=0
    c=[t for t in b['trades'] if t.get('signal') in ('breakout','retest') and 'prefilter' not in (t.get('real_reasons') or '') and t['status'] in ('open','closed')]
    c.sort(key=lambda t:(t['t_open']//900,-oi6(t['symbol'],t['t_open'])))
    for t in c:
        for p in [p for p in opn if p.get('t_close') and p['t_close']<=t['t_open']]:
            eq+=p['pnl'];opn.remove(p);pk=max(pk,eq);mdd=max(mdd,(pk-eq)/pk)
        if len(opn)>=N or any(p['symbol']==t['symbol'] for p in opn): skipped+=1;continue
        ru=eq*RISK/100;vol=int(ru/(t['R']*t['cs'])) if t['R']>0 else 0
        if vol<1: skipped+=1;continue
        m=vol*t['cs']*t['entry']/t.get('leverage',20)
        if m+sum(p['m'] for p in opn)>eq/2: skipped+=1;continue
        R=t.get('R_net') if t['status']=='closed' else t.get('mark_R',0)
        p=dict(symbol=t['symbol'],side=t['side'],open=t['open'],t_close=t.get('t_close') if t['status']=='closed' else None,status=t['status'],R=R,pnl=R*vol*t['cs']*t['R'],m=m,vol=vol)
        opn.append(p);taken.append(p)
    for p in [p for p in opn if p['t_close']]: eq+=p['pnl'];opn.remove(p)
    pk=max(pk,eq);mdd=max(mdd,(pk-eq)/pk)
    json.dump(dict(updated=time.strftime('%Y-%m-%d %H:%M'),rule='N3 risk0.5% oi6 rank',start=eq0,equity=round(eq,4),open=len(opn),
        closed=sum(1 for p in taken if p['t_close']),netR=round(sum(p['R'] for p in taken if p['t_close']),3),maxdd_pct=round(mdd*100,2),skipped=skipped,trades=taken),
        open(f'{P}/multi_book.json','w'),indent=1)
if __name__=='__main__':
    while True:
        try: build()
        except Exception as e: print(time.strftime('%m-%d %H:%M'),'err',repr(e)[:150],flush=True)
        time.sleep(300)
