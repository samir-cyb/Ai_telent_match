import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from core.models import ChatMessage, Application

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.application_id = self.scope['url_route']['kwargs']['application_id']
        self.room_group_name = f'chat_{self.application_id}'

        session = self.scope.get('session', {})
        self.student_id = session.get('student_id')
        self.company_id = session.get('company_id')

        if not self.student_id and not self.company_id:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        content = data.get('content')
        if not content:
            return

        if self.student_id:
            sender_type = 'student'
            sender_id = self.student_id
        elif self.company_id:
            sender_type = 'company'
            sender_id = self.company_id
        else:
            return

        message = await self.save_message(self.application_id, sender_type, sender_id, content)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': {
                    'id': str(message.id),
                    'sender_type': sender_type,
                    'sender_id': str(sender_id),
                    'content': content,
                    'timestamp': message.timestamp.isoformat(),
                }
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event['message']))

    @database_sync_to_async
    def save_message(self, application_id, sender_type, sender_id, content):
        application = Application.objects.get(id=application_id)
        return ChatMessage.objects.create(
            application=application,
            sender_type=sender_type,
            sender_id=sender_id,
            content=content
        )