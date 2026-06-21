from django.urls import path
from core.consumers import ChatConsumer

websocket_urlpatterns = [
    path('ws/chat/<uuid:application_id>/', ChatConsumer.as_asgi()),
]