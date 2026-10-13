seen_reset=True
"""Merge X search result files (agent-tools dumps) into raw/posts.jsonl; print per-account status."""
import json,glob,re,os,sys
D='/workspace/agent-tools';OUT='raw/posts.jsonl'
seen={};st={}
if False:
    for l in open(OUT): p=json.loads(l);seen[p['id']]=p
for f in glob.glob(D+'/*.txt'):
    s=open(f).read();i=s.find('{');j=s.rfind('}')
    if i<0: continue
    try: z=json.loads(s[i:j+1])
    except Exception:
        # strip trailing notes
        m=re.search(r'(\{"data".*\})\s*\n',s,re.S)
        if not m: continue
        try: z=json.loads(m.group(1))
        except Exception: continue
    if 'data' not in z or not z['data'] or 'text' not in z['data'][0]: continue
    U={u['id']:u.get('username') for u in z.get('includes',{}).get('users',[])}
    if len({p.get('author_id') for p in z['data']})>3:
        import shutil;shutil.copy(f,'raw/crowd_'+os.path.basename(f));continue
    for p in z['data']:
        u=U.get(p.get('author_id')) or (p.get('url','').split('/')[3] if p.get('url') else None)
        seen[p['id']]=dict(id=p['id'],user=u,t=p['created_at'],text=p['text'],src=os.path.basename(f))
    u=U.get(z['data'][0].get('author_id'))
    st.setdefault(u,[]).append((min(p['created_at'] for p in z['data']),z['meta'].get('next_token'),len(z['data']),os.path.basename(f)))
with open(OUT,'w') as o:
    for p in seen.values(): o.write(json.dumps(p)+'\n')
import collections
c=collections.Counter(p['user'] for p in seen.values())
for u,v in sorted(st.items(),key=lambda x:str(x[0])):
    oldest=min(v);print(u,c[u],'oldest',oldest[0][:10],'next',oldest[1],sum(x[2] for x in v))
