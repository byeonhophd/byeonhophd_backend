from channels.generic.websocket import AsyncWebsocketConsumer
import json
from dotenv import load_dotenv
import aiohttp
import asyncio
import uuid

load_dotenv('.env')

class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        # 고유한 conversation_id 생성 및 저장
        self.conversation_id = str(uuid.uuid4())
        self.history = [("system", "You are a helpful assistant.")]
        await self.accept()
        await self.send(text_data=json.dumps({
            "event": "conversation_id",
            "conversation_id": self.conversation_id
        }))

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json.get("message", "")
        conversation_id = text_data_json.get("conversation_id", self.conversation_id)

        if not message:
            await self.send(text_data=json.dumps({
                "event": "error",
                "message": "No message provided."
            }))
            return

        try:
            # 사용자 메시지를 대화 내역에 추가
            self.history.append(("user", message))

            # 대화 내역으로 프롬프트 생성 (선택 사항, Flask API가 관리할 경우 생략 가능)
            prompt = self.format_conversation(self.history)

            # Flask API에 메시지 전송
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'http://127.0.0.1:5000/query',
                    json={
                        'question': message,
                        'conversation_id': conversation_id
                    },
                    timeout=None  # 스트리밍 응답을 위해 타임아웃 설정 없음
                ) as resp:
                    if resp.status != 200:
                        error_msg = await resp.text()
                        await self.send(text_data=json.dumps({
                            "event": "error",
                            "message": f"Flask API error: {error_msg}"
                        }))
                        return

                    # 스트리밍 응답 처리
                    assistant_response = ''
                    async for line in resp.content:
                        line = line.decode('utf-8').strip("\n")
                        if line == 'data: [DONE]':
                            break
                        elif line.startswith('data: '):
                            data = line[len('data: '):]
                            if not data:
                                data = ' '
                            print("data: ", f"'{data}'")
                            # 누적된 어시스턴트 응답에 추가
                            assistant_response += data
                            # 클라이언트로 스트리밍된 응답 전송
                            await self.send(text_data=json.dumps({
                                "event": "on_parser_stream",
                                "output": data
                            }))
                    
                    # 어시스턴트의 전체 응답을 대화 내역에 추가
                    self.history.append(("assistant", assistant_response))

        except Exception as e:
            await self.send(text_data=json.dumps({
                "event": "error",
                "message": str(e)
            }))

    def format_conversation(self, history):
        # 대화 내역을 하나의 프롬프트 문자열로 포맷팅 (필요 시)
        prompt = ''
        for role, message in history:
            if role == 'system':
                prompt += f"{message}\n"
            elif role == 'user':
                prompt += f"User: {message}\n"
            elif role == 'assistant':
                prompt += f"Assistant: {message}\n"
        return prompt