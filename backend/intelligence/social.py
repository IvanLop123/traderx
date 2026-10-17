"""Descriptive social evidence from a bounded, authorized sample; never bot verdicts."""
import re
from collections import Counter
from datetime import timedelta
import numpy as np
import pandas as pd
from backend.schemas.contracts import now


def analyze_posts(posts,observed_at=None):
    observed_at=pd.Timestamp(observed_at or now());seen=set();unique=[]
    for p in posts:
        key=p.get('id')
        if key and key in seen:continue
        if key:seen.add(key)
        unique.append(p)
    posts=unique;n=len(posts)
    if not n:return {'status':'NO_POSTS','mentions':0}
    texts=[str(p.get('text','')) for p in posts]
    normalized=[re.sub(r'\s+',' ',re.sub(r'https?://\S+','',t.lower())).strip() for t in texts]
    counts=Counter(t for t in normalized if t);duplicates=sum(c-1 for c in counts.values())
    known=[str(p['author_id']) for p in posts if p.get('author_id')];authors=Counter(known)
    concentration=sum((v/len(known))**2 for v in authors.values()) if known else None
    sentiments=[];topic=Counter();cashtags=Counter();engagement=[];times=[];reposts=[]
    for p,text in zip(posts,texts):
        words=set(re.findall(r'\b\w+\b',text.lower()));bull=bool(words&{'bullish','buy','growth','beat','upside'});bear=bool(words&{'bearish','sell','decline','miss','downside'})
        sentiments.append(int(bull)-int(bear));cashtags.update(set(re.findall(r'\$([A-Z][A-Z0-9.]{0,9})\b',text)))
        topic.update(words&{'earnings','guidance','nuclear','power','robotics','semiconductor','inflation','bitcoin','regulation','acquisition'})
        metrics=p.get('public_metrics',{});engagement.append(sum(float(v) for k,v in metrics.items() if k in ('like_count','reply_count','retweet_count','quote_count','bookmark_count') and isinstance(v,(int,float)) and np.isfinite(v) and v>=0))
        t=pd.to_datetime(p.get('created_at'),utc=True,errors='coerce');times.append(t if pd.notna(t) and t<=observed_at else pd.NaT)
        reposts.extend(str(r['id']) for r in p.get('referenced_tweets',[]) if r.get('type')=='retweeted' and r.get('id'))
    bins=[sum(pd.notna(t) and observed_at-timedelta(hours=i+1)<t<=observed_at-timedelta(hours=i) for t in times) for i in range(3)]
    s=np.array(sentiments);bull=float((s>0).mean());bear=float((s<0).mean());repost_counts=Counter(reposts)
    repeat_concentration=sum((v/len(reposts))**2 for v in repost_counts.values()) if reposts else None
    velocity=bins[0] if any(pd.notna(t) for t in times) else None
    return {'status':'OBSERVED_SAMPLE_ONLY','mentions':n,'unique_authors':len(authors),'unknown_authors':n-len(known),
        'author_concentration':concentration,'duplicate_text_fraction':duplicates/n,'repost_concentration':repeat_concentration,
        'bullish_keyword_fraction':bull,'bearish_keyword_fraction':bear,'neutral_fraction':float((s==0).mean()),'sentiment_variance':float(s.var()),'lexical_disagreement':2*min(bull,bear),
        'engagement':sum(engagement),'mention_velocity_per_hour':velocity,'mention_acceleration_per_hour2':bins[0]-bins[1] if velocity is not None else None,
        'historical_mention_zscore':None,'engagement_velocity':None,'semantic_disagreement':None,'novelty_unique_text_fraction':len(counts)/n,
        'cashtags':dict(cashtags),'topic_clusters':dict(topic),'observed_at':observed_at.isoformat(),
        'scores':{'attention':float(np.log1p(n)),'virality':float(np.log1p(sum(engagement)/n)),'sentiment':float(s.mean()),'disagreement':2*min(bull,bear),'coordination_risk':duplicates/n},
        'warnings':['Bounded provider sample: velocities count observed posts, not total market activity. No extrapolation from truncated search results.',
            'Historical z-score and engagement velocity require comparable complete repeated windows and are unavailable for this sample.',
            'Duplicate text and repost concentration are coordination proxies, not identification of bots or manipulation. Lexical scores are uncalibrated.',
            'Disagreement is potential volatility evidence; it does not establish direction.']}


def window_metrics(db,data):
    """Compare explicit search windows; never interpret a page cap as complete history."""
    from datetime import datetime
    observed=pd.Timestamp(data['observed_at']);posts=data.get('data',[])
    metrics=analyze_posts(posts,observed);window=data['window'];start=pd.Timestamp(window['start']);end=pd.Timestamp(window['end']);hours=(end-start).total_seconds()/3600
    metrics.update({'window':window,'historical_mention_zscore':None,'engagement_velocity':None,'engagement_matched_posts':0,
                    'complete_window_mentions':None,'complete_window_velocity_per_hour':None,'complete_window_acceleration_per_hour2':None,'history_windows':0})
    history=[r['payload'] for r in db.records('social',limit=1000) if r['payload'].get('query')==data['query'] and r['payload'].get('window')]
    history=[p for p in history if pd.Timestamp(p.get('observed_at',p['metrics']['observed_at']))<observed]
    # Engagement is a longitudinal matched-post sample, independent of search completeness.
    previous={}
    for p in sorted(history,key=lambda p:p.get('observed_at',p['metrics']['observed_at']),reverse=True):
        for post in p.get('data',[]):previous.setdefault(post.get('id'),(post,p.get('observed_at',p['metrics']['observed_at'])))
    rates=[];revised=0
    for post in posts:
        if post.get('id') not in previous:continue
        old,t=previous[post['id']];elapsed=(observed-pd.Timestamp(t)).total_seconds()/3600
        if elapsed<=0:continue
        names=('like_count','reply_count','retweet_count','quote_count')
        before=old.get('public_metrics',{});after=post.get('public_metrics',{})
        if not all(isinstance(m.get(k),(int,float)) and np.isfinite(m[k]) and m[k]>=0 for m in (before,after) for k in names):continue
        deltas=[after[k]-before[k] for k in names]
        if min(deltas)<0:revised+=1;continue
        rates.append(sum(deltas)/elapsed)
    if rates:metrics['engagement_velocity']=sum(rates);metrics['engagement_matched_posts']=len(rates)
    metrics['engagement_counter_revisions']=revised
    complete=window.get('complete') is True and hours>0
    if complete:
        count=len({p['id'] for p in posts});metrics['complete_window_mentions']=count;metrics['complete_window_velocity_per_hour']=count/hours
        comparable={}
        for p in history:
            w=p['window'];a=pd.Timestamp(w['start']);b=pd.Timestamp(w['end'])
            if w.get('complete') is True and b<=start and abs((b-a).total_seconds()/3600-hours)<1e-6:
                comparable[(a,b)]=len({x['id'] for x in p.get('data',[])})
        # Greedily take nonoverlapping recent windows; later fetches of the same window do not multiply evidence.
        values=[];boundary=start
        for (a,b),n in sorted(comparable.items(),reverse=True):
            if b>boundary:continue
            if b==start:metrics['complete_window_acceleration_per_hour2']=(count/hours-n/hours)/hours
            values.append(n);boundary=a
            if len(values)>=28:break
        metrics['history_windows']=len(values)
        if len(values)>=8 and np.std(values,ddof=1)>0:metrics['historical_mention_zscore']=float((count-np.mean(values))/np.std(values,ddof=1))
    metrics['warnings']=[w for w in metrics.get('warnings',[]) if not w.startswith('Historical z-score')]
    metrics['warnings']+=['Complete-window counts cover this exact query and accessible provider corpus only. At least eight comparable nonoverlapping windows are required for a z-score.',
                          'Engagement velocity is observed increments per hour over matched posts only; missing posts/counters are not zero and decreasing counters are excluded. No seasonality adjustment or direction forecast.']
    metrics['status']='COMPLETE_QUERY_WINDOW' if complete else 'TRUNCATED_QUERY_WINDOW'
    return metrics
