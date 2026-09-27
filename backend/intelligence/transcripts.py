"""Deterministic transcript structure and lexical research; never asserts semantic intent."""
import re
from backend.intelligence.documents import narrative_features,question_answer

def speaker_role(speaker):
    label=speaker.lower()
    if 'operator' in label:return 'operator'
    if 'analyst' in label:return 'analyst'
    if re.search(r'\b(ceo|cfo|coo|chief|management|president|investor relations)\b',label):return 'management'
    return 'unknown'

def transcript_research(text,previous=None):
    turns=[];current=None;qa_section=False
    for line in text.splitlines():
        match=re.match(r'^([\w .()&/-]{1,120}):\s*(.*)',line)
        if match:
            if current:turns.append(current)
            speaker,content=match.groups()
            if re.search(r'question[- ]and[- ]answer|q\s*&\s*a',content,re.I):qa_section=True
            role=speaker_role(speaker)
            if role=='analyst':qa_section=True
            current={'speaker':speaker,'role':role,'section':'qa' if qa_section else 'prepared','text':content}
        elif current:current['text']+='\n'+line
    if current:turns.append(current)
    pairs=[];question=None;answers=[]
    def flush():
        if question and answers:
            answer='\n'.join(answers);metrics=question_answer(question['text'],answer)
            pairs.append({'question':question['text'],'answer':answer,'analyst':question['speaker'],**metrics,
                          'lexical_evasiveness_proxy':min(1,max(0,1-metrics['lexical_overlap']))})
    for turn in turns:
        if turn['role']=='analyst':flush();question=turn;answers=[]
        elif turn['role']=='management' and question:answers.append(turn['text'])
        elif turn['role']=='operator':flush();question=None;answers=[]
    flush()
    narrative=narrative_features(text)
    sentences=re.split(r'(?<=[.!?])\s+|\n+',text)
    commitments=[s for s in sentences if re.search(r'\b(expect|guidance|forecast|target|anticipate|project)\w*\b',s,re.I) and re.search(r'\d',s)]
    metrics={'transcript_hedge_fraction':narrative['hedge_fraction'],'transcript_numeric_density':narrative['numeric_mentions']/max(1,narrative['word_count']),
             'transcript_guidance_quote_count':len(commitments),'transcript_bottleneck_mentions':len(narrative['bottlenecks']),
             'qa_lexical_evasiveness_proxy':None,'qa_numeric_specificity':None,'qa_hedging_fraction':None}
    if pairs:
        metrics['qa_lexical_evasiveness_proxy']=sum(p['lexical_evasiveness_proxy'] for p in pairs)/len(pairs)
        metrics['qa_numeric_specificity']=sum(p['numerical_specificity'] for p in pairs)/len(pairs)
        metrics['qa_hedging_fraction']=sum(p['hedging'] for p in pairs)/len(pairs)
    previous_metrics=previous.get('metrics',{}) if previous else {}
    changes={key:{'previous':previous_metrics[key],'current':value,'absolute_change':value-previous_metrics[key]} for key,value in metrics.items() if value is not None and previous_metrics.get(key) is not None}
    return {'method':'transcript-lexical-v2','metrics':metrics,'turns':turns,'qa_pairs':pairs,'guidance_quotes':commitments,
            'bottlenecks':narrative['bottlenecks'],'themes':narrative['themes'],'changes':changes,
            'unknown_speaker_turns':sum(t['role']=='unknown' for t in turns),'semantic_evasiveness':None,
            'warnings':['Speaker roles require explicit analyst/management labels; unknown speakers are not guessed.',
                        'Lexical overlap is not semantic directness, deception, or predictive confidence.',
                        'Changes require an earlier distinct reporting period available at analysis time.']}
