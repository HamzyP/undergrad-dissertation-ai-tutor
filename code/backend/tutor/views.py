import logging

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from tutor.serializers import ChatRequestSerializer
from tutor.services.chat_service import get_chat_reply, stream_chat_reply
from tutor.services.question_service import (
    classify_student_intent,
    generate_consolidation_questions,
    generate_discussion_check,
    generate_explanation_outcome,
    generate_interpolated_reword,
    generate_mastery_question,
    generate_remediation,
    generate_remediation_reword,
)
from tutor.services.ollama_service import list_local_models
from tutor.ingestion.embed import warm_collection_async

logger = logging.getLogger(__name__)


def _debug_log(message: str, *args) -> None:
    if getattr(settings, "TUTOR_DEBUG_LOGS", False):
        logger.warning(message, *args)


def _default_model(models: list[str]) -> str:
    if not models:
        return ""
    if settings.OLLAMA_MODEL in models:
        return settings.OLLAMA_MODEL
    return models[0]


class ModelListView(APIView):
    def get(self, request):
        warm_collection_async()
        try:
            models = list_local_models()
        except Exception:
            logger.exception("Failed to fetch local Ollama models")
            return Response(
                {
                    "models": [],
                    "default_model": "",
                    "error": "Temporary backend error while loading local models.",
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "models": models,
                "default_model": _default_model(models),
            },
            status=status.HTTP_200_OK,
        )


class ChatView(APIView):
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        try:
            chat_response = get_chat_reply(payload)
        except Exception:
            logger.exception(
                "Tutor chat generation failed for session_id=%s topic=%s",
                payload.get("session_id"),
                payload.get("topic"),
            )
            return Response(
                {
                    "response": "Temporary backend error while generating tutor reply.",
                    "citations": [],
                    "latency_ms": 0,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "response": chat_response.response,
                "citations": [c.to_dict() for c in chat_response.citations],
                "latency_ms": chat_response.latency_ms,
            },
            status=status.HTTP_200_OK,
        )


class ChatStreamView(APIView):
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        _debug_log(
            "chat/stream request received session_id=%s topic=%s scaffold=%s message=%r",
            payload.get("session_id"),
            payload.get("topic"),
            payload.get("current_scaffold_level"),
            (payload.get("message") or "")[:120],
        )

        return StreamingHttpResponse(
            stream_chat_reply(payload),
            content_type="application/x-ndjson",
        )


def _parse_question_generation_request(request) -> tuple[str, str, str | None, str | None, str | None] | Response:
    original_question = request.data.get("original_question", "")
    student_explanation = request.data.get("student_explanation", "")
    if not original_question or not student_explanation:
        return Response(
            {"error": "original_question and student_explanation are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return (
        original_question,
        student_explanation,
        request.data.get("gap_focus") or None,
        request.data.get("topic") or None,
        request.data.get("model"),
    )


def _parse_explanation_evaluation_request(request) -> tuple[str, str, str, str | None, str | None] | Response:
    original_question = request.data.get("original_question", "")
    correct_answer = request.data.get("correct_answer", "")
    student_explanation = request.data.get("student_explanation", "")
    if not original_question or not correct_answer or not student_explanation:
        return Response(
            {"error": "original_question, correct_answer, and student_explanation are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return (
        original_question,
        correct_answer,
        student_explanation,
        request.data.get("topic") or None,
        request.data.get("model"),
    )


def _parse_discussion_check_request(request) -> tuple[str, str, str | None, str | None, str | None] | Response:
    original_question = request.data.get("original_question", "")
    student_question = request.data.get("student_question", "")
    if not original_question or not student_question:
        return Response(
            {"error": "original_question and student_question are required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return (
        original_question,
        student_question,
        request.data.get("question_classification") or None,
        request.data.get("topic") or None,
        request.data.get("model"),
    )


class ConsolidationGenerateView(APIView):
    def post(self, request):
        parsed = _parse_question_generation_request(request)
        if isinstance(parsed, Response):
            return parsed
        original_question, student_explanation, gap_focus, topic, model = parsed

        try:
            result = generate_consolidation_questions(
                original_question,
                student_explanation,
                gap_focus=gap_focus,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to generate consolidation questions")
            return Response({"questions": [], "latency_ms": 0}, status=status.HTTP_502_BAD_GATEWAY)

        if not result.questions:
            logger.error(
                "CONSOLIDATION GENERATION RETURNED 0 VALID QUESTIONS topic=%s original_question=%r student_explanation=%r gap_focus=%r",
                topic,
                original_question,
                student_explanation,
                gap_focus,
            )

        return Response(
            {
                "questions": [q.to_dict() for q in result.questions],
                "latency_ms": result.latency_ms,
            },
            status=status.HTTP_200_OK,
        )


class ExplanationEvaluateView(APIView):
    def post(self, request):
        parsed = _parse_explanation_evaluation_request(request)
        if isinstance(parsed, Response):
            return parsed
        original_question, correct_answer, student_explanation, topic, model = parsed

        try:
            result = generate_explanation_outcome(
                original_question,
                correct_answer,
                student_explanation,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to evaluate explanation outcome")
            return Response({"outcome": "partial", "gap_focus": ""}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(result, status=status.HTTP_200_OK)


class DiscussionCheckGenerateView(APIView):
    def post(self, request):
        parsed = _parse_discussion_check_request(request)
        if isinstance(parsed, Response):
            return parsed
        original_question, student_question, question_classification, topic, model = parsed

        try:
            result = generate_discussion_check(
                original_question,
                student_question,
                question_classification=question_classification,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to generate discussion-check question")
            return Response(
                {"question": None, "explanation": "", "latency_ms": 0},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "question": result.question.to_dict() if result.question else None,
                "explanation": result.explanation,
                "latency_ms": result.latency_ms,
            },
            status=status.HTTP_200_OK,
        )


class MasteryGenerateView(APIView):
    def post(self, request):
        parsed = _parse_question_generation_request(request)
        if isinstance(parsed, Response):
            return parsed
        original_question, student_explanation, _gap_focus, topic, model = parsed

        try:
            result = generate_mastery_question(
                original_question,
                student_explanation,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to generate mastery question")
            return Response({"question": None, "latency_ms": 0}, status=status.HTTP_502_BAD_GATEWAY)

        if result.question is None:
            logger.error(
                "MASTERY GENERATION RETURNED NO VALID QUESTION topic=%s original_question=%r student_explanation=%r",
                topic,
                original_question,
                student_explanation,
            )

        return Response(
            {
                "question": result.question.to_dict() if result.question else None,
                "latency_ms": result.latency_ms,
            },
            status=status.HTTP_200_OK,
        )


class IntentClassifyView(APIView):
    def post(self, request):
        message = request.data.get("message", "")
        if not message:
            return Response(
                {"error": "message is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interpolated_question = request.data.get("interpolated_question") or None
        topic = request.data.get("topic") or None
        model = request.data.get("model") or None

        try:
            intent = classify_student_intent(
                message,
                interpolated_question=interpolated_question,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to classify student intent")
            return Response({"intent": "evaluate_response"}, status=status.HTTP_200_OK)

        return Response({"intent": intent}, status=status.HTTP_200_OK)


class RemediationGenerateView(APIView):
    def post(self, request):
        original_question = request.data.get("original_question", "")
        correct_answer = request.data.get("correct_answer", "")
        if not original_question or not correct_answer:
            return Response(
                {"error": "original_question and correct_answer are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        topic = request.data.get("topic") or None
        model = request.data.get("model") or None

        try:
            result = generate_remediation(
                original_question,
                correct_answer,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to generate remediation content")
            return Response(
                {"explanation": f"The correct answer is: {correct_answer}.", "easy_question": None, "hint": ""},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "explanation": result.explanation,
                "easy_question": result.easy_question.to_dict() if result.easy_question else None,
                "hint": result.hint,
                "latency_ms": result.latency_ms,
            },
            status=status.HTTP_200_OK,
        )


class RemediationRewordView(APIView):
    def post(self, request):
        original_question = request.data.get("original_question", "")
        hint = request.data.get("hint", "")
        if not original_question:
            return Response(
                {"error": "original_question is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        topic = request.data.get("topic") or None
        model = request.data.get("model") or None

        try:
            result = generate_remediation_reword(
                original_question,
                hint,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to generate reworded remediation question")
            return Response({"question": None, "latency_ms": 0}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "question": result.question.to_dict() if result.question else None,
                "latency_ms": result.latency_ms,
            },
            status=status.HTTP_200_OK,
        )


class InterpolatedRewordView(APIView):
    def post(self, request):
        original_question = request.data.get("original_question", "")
        original_options = request.data.get("original_options")
        correct_index = request.data.get("correct_index")
        scaffold_level = request.data.get("scaffold_level", "")
        if not original_question or not isinstance(original_options, list) or correct_index is None:
            return Response(
                {"error": "original_question, original_options, and correct_index are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        topic = request.data.get("topic") or None
        model = request.data.get("model") or None

        try:
            result = generate_interpolated_reword(
                original_question,
                original_options,
                correct_index,
                scaffold_level,
                topic=topic,
                model_name=model,
            )
        except Exception:
            logger.exception("Failed to generate reworded interpolated question")
            return Response({"question": None, "latency_ms": 0}, status=status.HTTP_502_BAD_GATEWAY)

        return Response(
            {
                "question": result.question.to_dict() if result.question else None,
                "latency_ms": result.latency_ms,
            },
            status=status.HTTP_200_OK,
        )
