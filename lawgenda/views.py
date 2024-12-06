import aiohttp
from dotenv import load_dotenv
import feedparser
import json
import requests
import uuid

from channels.generic.websocket import AsyncWebsocketConsumer
from django.db.models import Q
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Clause
from .serializers import ClauseSerializer

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
                    'http://127.0.0.1:5001/query',
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
                        line = line.decode('utf-8')
                        if line == 'data: [DONE]\n':
                            break
                        elif line.startswith('data: '):
                            data = line[len('data: '):].strip("\n")
                            if not data:
                                data = '\n'
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


class ClauseSearchView(APIView):
    def get(self, request):
        query = request.GET.get('q', '')
        clauses = Clause.objects.filter(
            Q(identifier__icontains=query) | Q(content__icontains=query)
        ).order_by('id')  # 안정적인 정렬을 위해 order_by 추가

        paginator = PageNumberPagination()
        paginator.page_size = 10  # 페이지당 항목 수 설정 (settings.py에서 설정했다면 생략 가능)
        result_page = paginator.paginate_queryset(clauses, request)
        serializer = ClauseSerializer(result_page, many=True)
        return paginator.get_paginated_response(serializer.data)


class RssRetrieveView(APIView):
    """
    API 엔드포인트: RSS 피드를 가져와서 JSON 형식으로 반환합니다.
    """
    @method_decorator(cache_page(60*10))
    def get(self, request):
        rss_url = 'https://www.easylaw.go.kr/CSP/RssNewRetrieve.laf?topMenu=serviceUl7'
        try:
            # RSS 피드 가져오기
            response = requests.get(rss_url, timeout=10)
            response.raise_for_status()  # 상태 코드가 200이 아니면 예외 발생
        except requests.RequestException as e:
            return Response(
                {"error": "RSS 피드 가져오기 실패", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        
        # RSS 피드 파싱
        feed = feedparser.parse(response.content)
        
        # 피드 파싱 에러 체크
        if feed.bozo:
            return Response(
                {"error": "RSS 피드 파싱 실패", "details": str(feed.bozo_exception)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        # JSON 형식으로 변환
        rss_json = {
            "feed": {
                "title": feed.feed.get("title", ""),
                "link": feed.feed.get("link", ""),
                "description": feed.feed.get("description", ""),
                "language": feed.feed.get("language", ""),
                "pubDate": feed.feed.get("pubDate", ""),  # 필요 시 추가
                # 필요에 따라 다른 피드 수준의 필드 추가
            },
            "items": []
        }

        for entry in feed.entries:
            rss_json["items"].append({
                "title": entry.get("title", "").strip(),
                "link": entry.get("link", "").strip(),
                "description": entry.get("description", "").strip(),
                "pubDate": entry.get("published", "").strip(),
                "category": entry.get("category", "").strip(),
                # 필요에 따라 다른 아이템 수준의 필드 추가
            })

        return Response(rss_json, status=status.HTTP_200_OK)