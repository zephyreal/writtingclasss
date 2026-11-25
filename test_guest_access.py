import pytest
from test_app import client

@pytest.mark.parametrize('method,path,body',[
 ('get','/api/chapters',None),
 ('get','/api/practice/session',None),
 ('post','/api/practice/session',{}),
 ('get','/api/assignments',None),
 ('get','/api/teacher/students',None),
 ('get','/api/english/profile',None),
 ('post','/api/english/realtime/sessions',{'topic_id':'test'}),
 ('get','/api/arena',None),
 ('get','/courses/design/gomoku/',None),
 ('get','/courses/design/vehicle/',None),
 ('get','/api/courses/writing/messages',None),
 ('post','/api/courses/writing/messages',{'body':'游客不能发布'}),
 ('get','/api/courses/design/messages',None),
])
def test_guest_cannot_access_private_data_or_actions(method,path,body):
    c=client();r=c.request(method,path,**({'json':body} if body is not None else {}))
    assert r.status_code==401,(path,r.status_code,r.text)


def test_guest_assets_are_public():
    c=client()
    assert 'id="guestEnter"' in c.get('/').text
    r=c.get('/static/guest-mode.js')
    assert r.status_code==200 and 'showGuestPage' in r.text
