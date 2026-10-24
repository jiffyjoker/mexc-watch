#!/usr/bin/env python3
"""Offline dry run for the breakout prefilter and the oi_surge mute.

Synthetic 15m klines only. Nothing here calls MEXC or reads a webhook.
"""
import contextlib, io, os, tempfile, unittest
import common, scan

def book(n=120, vol=10.0, close=101.8):
    return dict(high=[103.0]*n, low=[100.0]*n, close=[close]*n, open=[close]*n,
                vol=[float(vol)]*n, time=[1_700_000_000+900*t for t in range(n)])

def arm_long(k, i=119, vol=40.0, close=103.5):
    """Closed bar i breaks the prior 24h high (103) with room to spare under the scanner's own 1% cap."""
    k['high'][i]=max(104.0, close); k['low'][i]=102.0; k['open'][i]=102.5
    k['close'][i]=close; k['vol'][i]=vol
    return k

class DryRun(unittest.TestCase):
    def setUp(self):
        self.taker, self.post, self.dry = common.taker_buy_share, common.post, common.DRY
        self.deals=[]
        common.DRY=True
        common.taker_buy_share=lambda sym, n=100: self.deals.append(sym) or 0.62
    def tearDown(self):
        common.taker_buy_share, common.post, common.DRY = self.taker, self.post, self.dry

    def test_blocked_and_passing_klines(self):
        i=119
        passed=arm_long(book())
        self.assertEqual(scan.signals(passed, i, 1.5), [('breakout','long',103.0)])
        low=arm_long(book(), vol=10.0)
        self.deals.clear()
        reasons, info=common.breakout_check('LOW_USDT','long',103.0,low,i,oi6=2,funding=0.0001,chg24=1.5)
        self.assertEqual(reasons, ['vol_lt_2x'])
        self.assertEqual(self.deals, [])
        self.assertIsNone(info['taker_buy_pct'])
        print('BLOCKED LOW_USDT', ','.join(reasons))
        self.deals.clear()
        reasons, _=common.breakout_check('OI_USDT','long',103.0,passed,i,oi6=-2.5,funding=0.0001,chg24=1.5)
        self.assertEqual(scan.signals(passed, i, 1.5), [('breakout','long',103.0)])
        self.assertEqual(reasons, ['oi_6h_fall'])
        self.assertEqual(self.deals, [])
        print('BLOCKED OI_USDT', ','.join(reasons), '(scanner breakout, deals not fetched)')
        self.deals.clear()
        reasons, info=common.breakout_check('PASS_USDT','long',103.0,passed,i,oi6=2,funding=0.0001,chg24=1.5)
        self.assertEqual(reasons, [])
        self.assertEqual(self.deals, ['PASS_USDT'])
        self.assertEqual(info['taker_buy_pct'], 0.62)
        print('PASS PASS_USDT', info)

    def test_reason_codes_and_missing_inputs(self):
        i=119
        k=arm_long(book())
        far=arm_long(book(), close=103.0*1.02)
        self.deals.clear()
        reasons, _=common.breakout_check('X_USDT','long',103.0,far,i,oi6=1,funding=0,chg24=1)
        self.assertEqual(reasons, ['chase_gt_1.5pct'])
        self.assertEqual(self.deals, [])
        edge=arm_long(book(), close=101.5)
        reasons, _=common.breakout_check('X_USDT','long',100.0,edge,i,oi6=1,funding=0,chg24=1,taker=0.6)
        self.assertNotIn('chase_gt_1.5pct', reasons)
        reasons, _=common.breakout_check('X_USDT','long',103.0,k,i,oi6=1,funding=0,chg24=-0.1,taker=0.8)
        self.assertEqual(reasons, ['against_day'])
        reasons, _=common.breakout_check('X_USDT','S',103.0,k,i,oi6=1,funding=0,chg24=0.2,taker=0.4)
        self.assertEqual(reasons, ['against_day'])
        reasons, _=common.breakout_check('X_USDT','long',103.0,k,i,oi6=-1.01,funding=0,chg24=1,taker=0.8)
        self.assertEqual(reasons, ['oi_6h_fall'])
        reasons, _=common.breakout_check('X_USDT','long',103.0,k,i,oi6=-1,funding=0,chg24=1,taker=0.8)
        self.assertEqual(reasons, [])
        reasons, _=common.breakout_check('X_USDT','long',103.0,k,i,oi6=1,funding=0.0005,chg24=1,taker=0.8)
        self.assertEqual(reasons, ['funding_extreme'])
        reasons, _=common.breakout_check('X_USDT','short',103.0,k,i,oi6=1,funding=-0.0005,chg24=-1,taker=0.4)
        self.assertEqual(reasons, ['funding_extreme'])
        reasons, _=common.breakout_check('X_USDT','long',103.0,k,i,oi6=1,funding=0.00049,chg24=1,taker=0.5)
        self.assertEqual(reasons, [])
        self.deals.clear()
        reasons, _=common.breakout_check('X_USDT','long',103.0,k,i,oi6=1,funding=0,chg24=1)
        self.assertEqual(self.deals, ['X_USDT'])
        self.assertEqual(reasons, [])
        common.taker_buy_share=lambda sym, n=100: 0.4
        reasons, info=common.breakout_check('X_USDT','long',103.0,k,i,oi6=1,funding=0,chg24=1)
        self.assertEqual(reasons, ['taker_against'])
        self.assertEqual(info['taker_buy_pct'], 0.4)
        common.taker_buy_share=lambda sym, n=100: 0.51
        reasons, _=common.breakout_check('X_USDT','short',103.0,k,i,oi6=1,funding=0,chg24=-1)
        self.assertEqual(reasons, ['taker_against'])
        fetched=[]
        common.taker_buy_share=lambda sym, n=100: fetched.append(sym) or None
        thin=book(n=40)
        reasons, info=common.breakout_check('X_USDT','L',None,thin,10,oi6=None,funding=None,chg24=None)
        self.assertEqual(reasons, [])
        self.assertIsNone(info['taker_buy_pct'])
        self.assertEqual(fetched, ['X_USDT'])  # cheap gates had nothing to reject, so the deals read still runs and fails open
        print('MISSING inputs left the wake open', info)

    def test_oi_surge_muted_breakout_still_posts(self):
        posts=[]
        common.post=lambda body: posts.append(body) or 200
        cwd=os.getcwd(); tmp=tempfile.mkdtemp(); os.chdir(tmp); buf=io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                sent=common.commit_hits([
                    dict(signal='oi_surge',symbol='AAA_USDT',side='long',close=1.0),
                    dict(signal='breakout',symbol='BBB_USDT',side='long',close=2.0,level=1.9),
                    dict(signal='retest',symbol='CCC_USDT',side='short',close=3.0,level=3.1),
                    dict(signal='sweep',symbol='DDD_USDT',side='long',close=4.0,level=3.9),
                    dict(signal='btc_move',symbol='BTC_USDT',side='short',close=5.0),
                ])
            self.assertFalse(os.path.exists('wakes.json'))
        finally:
            os.chdir(cwd)
        self.assertIn('muted oi_surge AAA_USDT', buf.getvalue())
        self.assertEqual(sent, 4)
        self.assertEqual([p['event'] for p in posts], ['breakout','retest','sweep','btc_move'])
        blob=repr(posts)
        for needle in ('http','WEBHOOK','Authorization','ntfy','oi_surge'):
            self.assertNotIn(needle, blob)
        print('MUTED oi_surge AAA_USDT; posted', [p['event'] for p in posts])

if __name__=='__main__':
    unittest.main(verbosity=2)
