from app import app as fastapi_app
from asgi2wsgi import ASGI2WSGI

application = ASGI2WSGI(fastapi_app)
