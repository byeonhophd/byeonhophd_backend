from django.urls import path  
from . import views  
  
  
urlpatterns = [  
    path('ws/chat/', views.ChatConsumer.as_asgi()),
    path('search/', views.ClauseSearchView.as_view(), name='clause_search'),
    path('rss/', views.RssRetrieveView.as_view(), name='rss_retrieve'), 
]