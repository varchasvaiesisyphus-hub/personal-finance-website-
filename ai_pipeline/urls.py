"""
ai_pipeline/urls.py

Mount these under /api/ai/ in financeproject/urls.py:

    path('api/ai/', include('ai_pipeline.urls')),
"""
from django.urls import path

from . import views

urlpatterns = [
    path("insights/latest/", views.api_latest_insights, name="ai-insights-latest"),
    path("insights/<int:pk>/feedback/", views.api_insight_feedback, name="ai-insight-feedback"),
]