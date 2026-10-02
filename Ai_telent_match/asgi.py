"""
ASGI config for Ai_telent_match project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ai_telent_match.settings')

application = get_asgi_application()

from django.conf import settings
if settings.ENABLE_CHAT:
    from channels.routing import ProtocolTypeRouter, URLRouter
    from channels.sessions import SessionMiddlewareStack
    from channels.security.websocket import AllowedHostsOriginValidator
    from .routing import websocket_urlpatterns
    application = ProtocolTypeRouter({
        'http': application,
        'websocket': AllowedHostsOriginValidator(SessionMiddlewareStack(URLRouter(websocket_urlpatterns))),
    })
