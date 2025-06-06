from manage import app
from asgiref.wsgi import WsgiToAsgi
from mangum import Mangum

asgi_app = WsgiToAsgi(app)
handler = Mangum(asgi_app, lifespan="off")
