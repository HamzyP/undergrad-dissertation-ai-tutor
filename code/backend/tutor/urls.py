from django.urls import path

from tutor.views import (
    ChatStreamView,
    ChatView,
    ConsolidationGenerateView,
    DiscussionCheckGenerateView,
    ExplanationEvaluateView,
    IntentClassifyView,
    InterpolatedRewordView,
    MasteryGenerateView,
    ModelListView,
    RemediationGenerateView,
    RemediationRewordView,
)
from tutor.views_questions import question_detail, question_generate, question_list_create
from tutor.views_participants import attempt_record, consent_record, export_csv, session_create, session_delete, session_finalise, sessions_list
from tutor.views_rag_debug import (
    rag_add_url,
    rag_corpus,
    rag_ingest_pending,
    rag_query,
    rag_source_deactivate,
    rag_source_delete,
    rag_transcript_download,
    rag_upload_transcript,
)

urlpatterns = [
    path("models", ModelListView.as_view(), name="models"),
    path("chat", ChatView.as_view(), name="chat"),
    path("chat/stream", ChatStreamView.as_view(), name="chat-stream"),
    path("explanation/evaluate", ExplanationEvaluateView.as_view(), name="explanation-evaluate"),
    path("discussion-check/generate", DiscussionCheckGenerateView.as_view(), name="discussion-check-generate"),
    path("consolidation/generate", ConsolidationGenerateView.as_view(), name="consolidation-generate"),
    path("mastery/generate", MasteryGenerateView.as_view(), name="mastery-generate"),
    path("intent/classify", IntentClassifyView.as_view(), name="intent-classify"),
    path("remediation/generate", RemediationGenerateView.as_view(), name="remediation-generate"),
    path("remediation/reword", RemediationRewordView.as_view(), name="remediation-reword"),
    path("interpolated/reword", InterpolatedRewordView.as_view(), name="interpolated-reword"),

    path("questions/", question_list_create, name="question-list-create"),
    path("questions/<int:pk>/", question_detail, name="question-detail"),
    path("questions/generate/", question_generate, name="question-generate"),

    path("participants/", sessions_list, name="participant-sessions-list"),
    path("participants/create/", session_create, name="participant-session-create"),
    path("participants/export/", export_csv, name="participant-export-csv"),
    path("participants/<str:participant_id>/", session_delete, name="participant-session-delete"),
    path("participants/<str:participant_id>/consent/", consent_record, name="participant-consent-record"),
    path("participants/<str:participant_id>/attempt/", attempt_record, name="participant-attempt-record"),
    path("participants/<str:participant_id>/finalise/", session_finalise, name="participant-session-finalise"),

    path("rag-debug/corpus/", rag_corpus, name="rag-debug-corpus"),
    path("rag-debug/query/", rag_query, name="rag-debug-query"),
    path("rag-debug/sources/<str:source_type>/<str:source_id>/deactivate/", rag_source_deactivate, name="rag-debug-source-deactivate"),
    path("rag-debug/sources/<str:source_type>/<str:source_id>/", rag_source_delete, name="rag-debug-source-delete"),
    path("rag-debug/upload/transcript/", rag_upload_transcript, name="rag-debug-upload-transcript"),
    path("rag-debug/sources/url/add/", rag_add_url, name="rag-debug-add-url"),
    path("rag-debug/sources/url/ingest/", rag_ingest_pending, name="rag-debug-ingest-pending"),
    path("rag-debug/transcripts/<str:filename>", rag_transcript_download, name="rag-debug-transcript-download"),
]
