"""Use the real platform middleware, not a fake app without course access gates."""
from fastapi.responses import Response
from test_app import a,client
from course_access import gated_course


def test_only_navigation_bootstrap_is_public():
    assert gated_course('/courses/design/vehicle/entry.js') is None
    for path in ('/courses/design/vehicle/','/courses/design/vehicle/app.js','/courses/design/vehicle/teaching.html','/courses/design/vehicle/entry.js/other','/courses/design/gomoku/'):
        assert gated_course(path)=='design'


def test_login_page_can_load_extension_navigation():
    # Install only a synthetic public asset, without requiring the optional repository.
    async def asset():return Response('views.vehicle = {};',media_type='application/javascript')
    a.app.add_api_route('/courses/design/vehicle/entry.js',asset,methods=['GET'])
    route=a.app.routes[-1]
    try:
        c=client()
        assert c.get('/courses/design/vehicle/entry.js?v=regression').status_code==200
        assert c.get('/courses/design/vehicle/').status_code==401
        assert c.get('/courses/design/vehicle/teaching.html').status_code==401
    finally:a.app.routes.remove(route)
