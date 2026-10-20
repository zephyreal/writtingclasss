"""Versioned, original short-question bank. No model-generated answers at runtime."""
from pathlib import Path
import hashlib

ROOT=Path(__file__).parent/'question_bank'
SOURCES={
 'question':('George Mason University · Research questions','https://writingcenter.gmu.edu/writing-resources/research-based-writing/how-to-write-a-research-question'),
 'review':('Purdue OWL · Literature reviews','https://owl.purdue.edu/owl/research_and_citation/conducting_research/writing_a_literature_review.html'),
 'search':('Cornell University Library · Database searching','https://guides.library.cornell.edu/public-health/how-to-search-for-resources'),
 'structure':('George Mason University · IMRaD results and discussion','https://writingcenter.gmu.edu/writing-resources/imrad/imrad-results-discussion'),
 'abstract':('UNC Writing Center · Abstracts','https://writingcenter.unc.edu/tips-and-tools/abstracts/'),
 'methods':('PLOS One · Submission guidelines','https://journals.plos.org/plosone/s/submission-guidelines'),
 'leakage':('scikit-learn · Common pitfalls','https://scikit-learn.org/stable/common_pitfalls.html'),
 'figures':('UNC Writing Center · Figures and charts','https://writingcenter.unc.edu/tips-and-tools/figures-and-charts/'),
 'errors':('Nature Methods · Error bars','https://www.nature.com/articles/nmeth.2659'),
 'quote':('Purdue OWL · Quoting, paraphrasing and summarizing','https://owl.purdue.edu/owl/research_and_citation/using_research/quoting_paraphrasing_and_summarizing/index.html'),
 'revision':('UNC Writing Center · Revising drafts','https://writingcenter.unc.edu/tips-and-tools/revising-drafts/'),
 'ai':('COPE · Authorship and AI tools','https://doi.org/10.24318/cCVRZBms'),
}
SOURCE_MAP={1:['question']*8,2:['search','search','review','review','review','review','quote','search'],3:['structure','revision','structure','revision','methods','structure','structure','revision'],4:['abstract']*5+['review','question','abstract'],5:['methods']*4+['leakage','methods','methods','methods'],6:['structure','figures','figures','figures','errors','figures','structure','structure'],7:['revision','methods','revision','structure','quote','quote','methods','ai'],8:['revision']*8}
LEVELS=[1,1,2,2,2,3,3,1,2,2]

def load_bank():
    bank={};digest=hashlib.sha256();stems=set()
    for unit in range(1,9):
        path=ROOT/f'unit{unit}.txt';text=path.read_text(encoding='utf8');digest.update(text.encode())
        topic=0;pos=0;count=0;label=''
        for line in text.splitlines():
            if not line.strip():continue
            if line.startswith('# '):
                if topic and pos!=10:raise ValueError(f'{path}: topic must have ten questions')
                topic+=1;pos=0;label=line[2:];continue
            parts=line.split('|');pos+=1;count+=1
            if len(parts)==5:
                stem,correct,wrong1,wrong2,explanation=parts;options=[correct,wrong1,wrong2]
                shift=(unit+topic+pos)%3;options=options[shift:]+options[:shift];answer=options.index(correct);kind='choice'
                if pos>7:raise ValueError(f'{path}: expected true/false')
            elif len(parts)==3:
                stem,truth,explanation=parts
                if truth not in ('T','F') or pos<=7:raise ValueError(f'{path}: invalid true/false')
                options=['正确','错误'];answer=0 if truth=='T' else 1;kind='boolean'
            else:raise ValueError(f'{path}: invalid line')
            if stem in stems:raise ValueError(f'duplicate stem: {stem}')
            stems.add(stem)
            if len(set(options))!=len(options) or len(stem)>65 or any(len(x)>30 for x in options):raise ValueError(f'invalid short question: {stem}')
            qid=f'u{unit}-t{topic}-q{pos}'
            bank[qid]={'id':qid,'chapter_id':unit,'topic':f'u{unit}-t{topic}','topic_name':label,'kind':kind,'level':LEVELS[pos-1],'stem':stem,'options':options,'answer':answer,'explanation':explanation,'source':SOURCE_MAP[unit][topic-1]}
        if topic!=8 or pos!=10 or count!=80:raise ValueError(f'{path}: expected 80 items / 8 topics')
    return bank,digest.hexdigest()[:12]

BANK,BANK_VERSION=load_bank()
TOPICS={q['topic']:{'id':q['topic'],'name':q['topic_name'],'chapter_id':q['chapter_id']} for q in BANK.values()}
