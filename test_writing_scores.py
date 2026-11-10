import json
import pytest
from test_writing_workflow import setup,upload,detail
from test_app import a
import writing_workflow as w

def set_weights(t,aid,weights):
    return t.put(f'/api/assignments/{aid}',json={'title':'科研写作','workflow':True,'round_weights':weights})

def test_all_rounds_suggestions_teacher_scores_and_weighted_final(setup):
    t,s,other,aid,calls=setup
    assert set_weights(t,aid,[10,20,30,40]).status_code==200
    for n,score in enumerate([50,60,70,80],1):
        assert upload(s,aid,n).status_code==200
        d=detail(s,aid);sid=d['submission_id'];rid=d['rounds'][-1]['id']
        assert a.run_review(sid)
        private=t.get(f'/api/teacher/writing/submissions/{sid}').json()
        assert private['rounds'][-1]['review']['score']==85
        assert private['grading']['total'] is None
        assert s.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':100}).status_code==403
        assert t.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':score,'feedback':f'教师第{n}轮反馈','published':True}).status_code==200
        assert detail(s,aid)['rounds'][-1]['teacher_score']==score
        assert detail(s,aid)['score'] is None
        assert detail(s,aid)['grading']['total'] is None
    assert t.get(f'/api/teacher/writing/submissions/{sid}').json()['grading']['total']==70
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':99,'feedback':'不能手填总分','published':True}).status_code==409
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':70,'feedback':'已复核四轮','published':True}).status_code==200
    assert detail(s,aid)['score']==70
    assert set_weights(t,aid,[25,25,25,25]).status_code==409
    assert t.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':99}).status_code==409
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':70,'feedback':'撤回重新计算','published':False}).status_code==200
    assert set_weights(t,aid,[25,25,25,25]).status_code==200
    assert t.get(f'/api/teacher/writing/submissions/{sid}').json()['grading']['total']==65
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':65,'feedback':'重新确认','published':True}).status_code==200


def test_missing_round_scores_not_zero_and_weights_validation(setup):
    t,s,other,aid,calls=setup
    assert set_weights(t,aid,[25,25,25,25]).status_code==200
    assert set_weights(t,aid,[20,20,20,20]).status_code==400
    assert set_weights(t,aid,[-1,1,0,100]).status_code==400
    for n in range(1,5):
        assert upload(s,aid,n).status_code==200
        d=detail(s,aid);sid=d['submission_id'];assert a.run_review(sid)
    assert t.post(f'/api/teacher/submissions/{sid}/grade',json={'score':0,'feedback':'缺项不能计零','published':True}).status_code==409
    d=t.get(f'/api/teacher/writing/submissions/{sid}').json()
    assert d['grading']['total'] is None and d['grading']['missing']==[1,2,3,4]
    assert other.get(f'/api/writing/assignments/{aid}').json()['rounds']==[]


def test_round_draft_hidden_and_manual_feedback_can_be_scored(setup):
    t,s,other,aid,calls=setup
    assert upload(s,aid,1).status_code==200
    d=detail(s,aid);sid=d['submission_id'];rid=d['rounds'][0]['id']
    assert t.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':60}).status_code==409
    assert t.post(f'/api/teacher/writing/submissions/{sid}/manual-feedback',json={'feedback':'本轮材料已经明确，请继续补充研究问题与支持证据。'}).status_code==200
    assert t.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':60,'feedback':'教师草稿','published':False}).status_code==200
    assert detail(s,aid)['rounds'][0]['teacher_score'] is None
    assert t.post(f'/api/teacher/writing/rounds/{rid}/grade',json={'score':61,'feedback':'教师确认','published':True}).status_code==200
    assert detail(s,aid)['rounds'][0]['teacher_score']==61
