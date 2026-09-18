import json
from unittest import TestCase
from unittest.mock import MagicMock, patch

from django.conf import settings
from rest_framework import status
from rest_framework.test import APITestCase

from tutor.models import Question
from tutor.services.chat_service import (
    _build_chat_retrieval_query,
    _build_system_prompt,
    generate_chat_response,
    generate_fallback_chat_response,
)
from tutor.services.prompts import (
    CLASSIFICATION_ADDENDA,
    EXPLANATION_OUTCOME_ADDENDA,
    GUARDRAIL_INSTRUCTIONS,
    SUPPORT_STRATEGY_ADDENDA,
    SYSTEM_PROMPT,
    build_hint_addendum,
)
from tutor.services.types import (
    ChatResponse,
    ConsolidationQuestion,
    DiscussionCheckResult,
    build_citations,
    build_prompt,
    response_has_no_citations,
    response_has_valid_citations,
)
from tutor.services.ollama_service import generate_text
from tutor.services.question_service import (
    ConsolidationQuestionsResult,
    MasteryQuestionResult,
    _build_consolidation_prompt,
    _build_discussion_check_prompt,
    _build_explanation_evaluation_prompt,
    _build_mastery_prompt,
    _parse_valid_consolidation_questions,
    _retrieve_consolidation_context,
    generate_discussion_check,
    generate_explanation_outcome,
    generate_consolidation_questions,
    generate_mastery_question,
)


RAG_CONTEXT = ["Mill defends liberty as protection against coercive social power."]
RAG_METADATAS = [
    {
        "source_type": "sep",
        "source_id": "liberalism",
        "title": "Liberalism",
        "section": "Liberty",
        "subsection": "Mill",
        "url": "https://example.com/liberalism",
    }
]


class ChatEndpointTests(APITestCase):
    def test_build_chat_retrieval_query_prefers_interpolated_question_for_idk(self):
        query = _build_chat_retrieval_query(
            {
                "message": "idk",
                "topic": "liberalism",
                "interpolated_question": "What is the harm principle?",
            }
        )

        self.assertEqual(query, "liberalism What is the harm principle?")

    def test_build_chat_retrieval_query_uses_message_when_specific(self):
        query = _build_chat_retrieval_query(
            {
                "message": "How does Mill define harm?",
                "topic": "liberalism",
                "interpolated_question": "What is the harm principle?",
            }
        )

        self.assertEqual(query, "How does Mill define harm?")

    @patch("tutor.views.get_chat_reply")
    def test_chat_endpoint_passes_interpolated_question_to_service(self, mock_get_chat_reply):
        mock_get_chat_reply.return_value = ChatResponse(
            response="The harm principle says liberty is restricted only to prevent harm to others [1].",
            citations=build_citations(RAG_METADATAS),
            latency_ms=123,
        )

        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "idk",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "interpolated_question": "According to Mill, what is the main principle that should guide restrictions on individual liberties?",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_chat_reply.assert_called_once_with(
            {
                "session_id": "session-1",
                "message": "idk",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "interpolated_question": "According to Mill, what is the main principle that should guide restrictions on individual liberties?",
                "history": [],
            }
        )

    @patch("tutor.views.get_chat_reply")
    def test_chat_endpoint_passes_interpolated_answer_correct_flag(
        self,
        mock_get_chat_reply,
    ):
        mock_get_chat_reply.return_value = ChatResponse(
            response="Yes, that answer is correct because Mill only permits coercion to prevent harm to others [1].",
            citations=build_citations(RAG_METADATAS),
            latency_ms=123,
        )

        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "Because it sets a limit on state power.",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "interpolated_question": "According to Mill, what is the main principle that should guide restrictions on individual liberties?",
                "interpolated_answer_correct": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_chat_reply.assert_called_once_with(
            {
                "session_id": "session-1",
                "message": "Because it sets a limit on state power.",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "interpolated_question": "According to Mill, what is the main principle that should guide restrictions on individual liberties?",
                "interpolated_answer_correct": True,
                "history": [],
            }
        )

    @patch(
        "tutor.views.generate_explanation_outcome",
        return_value={"outcome": "partial", "gap_focus": "It misses that only harm to others justifies coercion."},
    )
    def test_explanation_evaluate_endpoint_returns_outcome(self, mock_generate_explanation_outcome):
        response = self.client.post(
            "/api/explanation/evaluate",
            data={
                "original_question": "What is the harm principle?",
                "correct_answer": "Preventing harm to others",
                "student_explanation": "It stops people being mean.",
                "topic": "liberalism",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {"outcome": "partial", "gap_focus": "It misses that only harm to others justifies coercion."},
        )
        mock_generate_explanation_outcome.assert_called_once_with(
            "What is the harm principle?",
            "Preventing harm to others",
            "It stops people being mean.",
            topic="liberalism",
            model_name=None,
        )

    @patch("tutor.views.generate_consolidation_questions")
    def test_consolidation_generate_endpoint_passes_gap_focus(self, mock_generate_consolidation_questions):
        mock_generate_consolidation_questions.return_value = ConsolidationQuestionsResult(
            questions=[],
            latency_ms=31,
        )

        response = self.client.post(
            "/api/consolidation/generate",
            data={
                "original_question": "What is the harm principle?",
                "student_explanation": "I guessed.",
                "gap_focus": "The student confuses harm with mere offence.",
                "topic": "liberalism",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_generate_consolidation_questions.assert_called_once_with(
            "What is the harm principle?",
            "I guessed.",
            gap_focus="The student confuses harm with mere offence.",
            topic="liberalism",
            model_name=None,
        )

    @patch("tutor.views.generate_discussion_check")
    def test_discussion_check_generate_endpoint_returns_question_and_explanation(self, mock_generate_discussion_check):
        mock_generate_discussion_check.return_value = DiscussionCheckResult(
            question=ConsolidationQuestion(
                question="Which case best fits Mill's harm principle [1]?",
                options=[
                    "Restricting conduct that harms others",
                    "Banning harmless offence",
                    "Punishing eccentricity",
                    "Forcing virtue by law",
                ],
                correct_index=0,
                citations=build_citations(RAG_METADATAS),
            ),
            explanation="Mill allows interference only to prevent harm to others, not mere offence.",
            latency_ms=22,
        )

        response = self.client.post(
            "/api/discussion-check/generate",
            data={
                "original_question": "What is the harm principle?",
                "student_question": "Why is offence not enough?",
                "question_classification": "philosophical",
                "topic": "liberalism",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["explanation"], "Mill allows interference only to prevent harm to others, not mere offence.")
        mock_generate_discussion_check.assert_called_once_with(
            "What is the harm principle?",
            "Why is offence not enough?",
            question_classification="philosophical",
            topic="liberalism",
            model_name=None,
        )

    def test_discussion_check_generate_endpoint_requires_original_and_student_question(self):
        response = self.client.post(
            "/api/discussion-check/generate",
            data={
                "original_question": "What is the harm principle?",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(),
            {"error": "original_question and student_question are required."},
        )

    @patch("tutor.views.logger.exception")
    @patch("tutor.views.generate_discussion_check", side_effect=RuntimeError("generation failed"))
    def test_discussion_check_generate_endpoint_returns_502_when_generation_fails(
        self,
        _mock_generate_discussion_check,
        mock_log_exception,
    ):
        response = self.client.post(
            "/api/discussion-check/generate",
            data={
                "original_question": "What is the harm principle?",
                "student_question": "Why is offence not enough?",
                "question_classification": "philosophical",
                "topic": "liberalism",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.json(),
            {"question": None, "explanation": "", "latency_ms": 0},
        )
        mock_log_exception.assert_called_once_with("Failed to generate discussion-check question")

    @patch("tutor.views.get_chat_reply")
    def test_chat_endpoint_returns_generated_response(self, mock_get_chat_reply):
        mock_get_chat_reply.return_value = ChatResponse(
            response="Generated tutor reply from Ollama.",
            citations=[],
            latency_ms=123,
        )

        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "response": "Generated tutor reply from Ollama.",
                "citations": [],
                "latency_ms": 123,
            },
        )
        mock_get_chat_reply.assert_called_once_with(
            {
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "history": [],
            }
        )

    @patch("tutor.views.get_chat_reply")
    def test_chat_endpoint_passes_optional_model_selection(self, mock_get_chat_reply):
        mock_get_chat_reply.return_value = ChatResponse(
            response="Generated tutor reply from Ollama.",
            citations=[],
            latency_ms=123,
        )

        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "model": "llama3.2:latest",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_get_chat_reply.assert_called_once_with(
            {
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "model": "llama3.2:latest",
                "history": [],
            }
        )

    def test_chat_endpoint_validates_required_fields(self):
        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "What is liberalism?",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("topic", response.json())
        self.assertIn("timestamp", response.json())
        self.assertIn("current_scaffold_level", response.json())

    @patch("tutor.views.generate_mastery_question")
    def test_mastery_generate_endpoint_returns_single_question(self, mock_generate_mastery_question):
        mock_generate_mastery_question.return_value = MasteryQuestionResult(
            question=ConsolidationQuestion(
                question="Which case fits Mill's harm principle best [1]?",
                options=[
                    "Stopping conduct that directly harms others",
                    "Banning unpopular opinions",
                    "Forcing virtue by law",
                    "Punishing harmless eccentricity",
                ],
                correct_index=0,
                citations=build_citations(RAG_METADATAS),
            ),
            latency_ms=88,
        )

        response = self.client.post(
            "/api/mastery/generate",
            data={
                "original_question": "According to Mill, what is the main principle that should guide restrictions on individual liberties?",
                "student_explanation": "Because Mill says freedom should only be limited to prevent harm to others.",
                "topic": "liberalism",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "question": {
                    "question": "Which case fits Mill's harm principle best [1]?",
                    "options": [
                        "Stopping conduct that directly harms others",
                        "Banning unpopular opinions",
                        "Forcing virtue by law",
                        "Punishing harmless eccentricity",
                    ],
                    "correct_index": 0,
                    "citations": [
                        {
                            "source_type": "sep",
                            "source_id": "liberalism",
                            "title": "Liberalism",
                            "url": "https://example.com/liberalism",
                            "location": "Liberty › Mill",
                            "start_time": None,
                        }
                    ],
                },
                "latency_ms": 88,
            },
        )
        mock_generate_mastery_question.assert_called_once_with(
            "According to Mill, what is the main principle that should guide restrictions on individual liberties?",
            "Because Mill says freedom should only be limited to prevent harm to others.",
            topic="liberalism",
            model_name=None,
        )

    @patch("tutor.views.logger.error")
    @patch("tutor.views.generate_consolidation_questions")
    def test_consolidation_generate_endpoint_returns_empty_questions_when_service_has_no_valid_items(
        self,
        mock_generate_consolidation_questions,
        mock_log_error,
    ):
        mock_generate_consolidation_questions.return_value = ConsolidationQuestionsResult(
            questions=[],
            latency_ms=31,
        )

        response = self.client.post(
            "/api/consolidation/generate",
            data={
                "original_question": "What is the harm principle?",
                "student_explanation": "I guessed.",
                "topic": "liberalism",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "questions": [],
                "latency_ms": 31,
            },
        )
        mock_generate_consolidation_questions.assert_called_once_with(
            "What is the harm principle?",
            "I guessed.",
            gap_focus=None,
            topic="liberalism",
            model_name=None,
        )
        mock_log_error.assert_called_once_with(
            "CONSOLIDATION GENERATION RETURNED 0 VALID QUESTIONS topic=%s original_question=%r student_explanation=%r gap_focus=%r",
            "liberalism",
            "What is the harm principle?",
            "I guessed.",
            None,
        )

    @patch("tutor.views.logger.error")
    @patch("tutor.views.generate_mastery_question")
    def test_mastery_generate_endpoint_returns_null_when_service_has_no_valid_item(
        self,
        mock_generate_mastery_question,
        mock_log_error,
    ):
        mock_generate_mastery_question.return_value = MasteryQuestionResult(
            question=None,
            latency_ms=27,
        )

        response = self.client.post(
            "/api/mastery/generate",
            data={
                "original_question": "What is the harm principle?",
                "student_explanation": "I think it means people should be nice.",
                "topic": "liberalism",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "question": None,
                "latency_ms": 27,
            },
        )
        mock_generate_mastery_question.assert_called_once_with(
            "What is the harm principle?",
            "I think it means people should be nice.",
            topic="liberalism",
            model_name=None,
        )
        mock_log_error.assert_called_once_with(
            "MASTERY GENERATION RETURNED NO VALID QUESTION topic=%s original_question=%r student_explanation=%r",
            "liberalism",
            "What is the harm principle?",
            "I think it means people should be nice.",
        )

    @patch("tutor.views.logger.exception")
    @patch("tutor.views.get_chat_reply")
    def test_chat_endpoint_returns_debuggable_error_response_on_service_failure(
        self,
        mock_get_chat_reply,
        mock_log_exception,
    ):
        mock_get_chat_reply.side_effect = RuntimeError("Ollama is unavailable")

        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.json(),
            {
                "response": "Temporary backend error while generating tutor reply.",
                "citations": [],
                "latency_ms": 0,
            },
        )
        mock_log_exception.assert_called_once_with(
            "Tutor chat generation failed for session_id=%s topic=%s",
            "session-1",
            "liberalism",
        )

    @patch("tutor.views.get_chat_reply")
    def test_chat_endpoint_falls_back_when_generated_reply_is_not_grounded(
        self,
        mock_get_chat_reply,
    ):
        mock_get_chat_reply.return_value = ChatResponse(
            response="Slightly beyond the video: liberalism usually stresses individual freedom. How does that connect to the point just made in the video?",
            citations=[],
            latency_ms=45,
        )

        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "response": "Slightly beyond the video: liberalism usually stresses individual freedom. How does that connect to the point just made in the video?",
                "citations": [],
                "latency_ms": 45,
            },
        )
        mock_get_chat_reply.assert_called_once_with(
            {
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "history": [],
            }
        )

    @patch("tutor.views.get_chat_reply")
    def test_chat_endpoint_uses_fallback_without_rag_context(
        self,
        mock_get_chat_reply,
    ):
        mock_get_chat_reply.return_value = ChatResponse(
            response="Slightly beyond the video: liberalism is a broad tradition about protecting freedom and limiting power. Which part of the video do you want to connect that to?",
            citations=[],
            latency_ms=33,
        )

        response = self.client.post(
            "/api/chat",
            data={
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "response": "Slightly beyond the video: liberalism is a broad tradition about protecting freedom and limiting power. Which part of the video do you want to connect that to?",
                "citations": [],
                "latency_ms": 33,
            },
        )
        mock_get_chat_reply.assert_called_once_with(
            {
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "history": [],
            }
        )


class ModelListEndpointTests(APITestCase):
    @patch("tutor.views.warm_collection_async")
    @patch("tutor.views.list_local_models")
    def test_model_list_endpoint_returns_downloaded_models(self, mock_list_local_models, mock_warm_collection_async):
        mock_list_local_models.return_value = ["llama3.2:latest", "mistral:latest"]

        response = self.client.get("/api/models")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "models": ["llama3.2:latest", "mistral:latest"],
                "default_model": "llama3.2:latest",
            },
        )
        mock_warm_collection_async.assert_called_once()

    @patch("tutor.views.warm_collection_async")
    @patch("tutor.views.list_local_models")
    def test_model_list_endpoint_prefers_configured_default_model_when_available(
        self, mock_list_local_models, mock_warm_collection_async
    ):
        mock_list_local_models.return_value = [
            "llama3.1:8b-instruct-q4_K_M",
            "llama3.2:latest",
            "mistral:latest",
        ]

        response = self.client.get("/api/models")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {
                "models": [
                    "llama3.1:8b-instruct-q4_K_M",
                    "llama3.2:latest",
                    "mistral:latest",
                ],
                "default_model": "llama3.1:8b-instruct-q4_K_M",
            },
        )
        mock_warm_collection_async.assert_called_once()

    @patch("tutor.views.logger.exception")
    @patch("tutor.views.warm_collection_async")
    @patch("tutor.views.list_local_models")
    def test_model_list_endpoint_returns_debuggable_error_response(
        self, mock_list_local_models, mock_warm_collection_async, mock_log_exception
    ):
        mock_list_local_models.side_effect = RuntimeError("Ollama is unavailable")

        response = self.client.get("/api/models")

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(
            response.json(),
            {
                "models": [],
                "default_model": "",
                "error": "Temporary backend error while loading local models.",
            },
        )
        mock_warm_collection_async.assert_called_once()
        mock_log_exception.assert_called_once_with("Failed to fetch local Ollama models")


class OllamaServiceTests(TestCase):
    @patch("tutor.services.ollama_service.request.urlopen")
    @patch("tutor.services.ollama_service._fetch_available_models")
    @patch("tutor.services.ollama_service._start_ollama_server")
    @patch("tutor.services.ollama_service._is_ollama_api_running")
    def test_generate_text_starts_ollama_when_api_is_down(
        self,
        mock_is_ollama_api_running,
        mock_start_ollama_server,
        mock_fetch_available_models,
        mock_urlopen,
    ):
        mock_is_ollama_api_running.side_effect = [False, False, True]
        mock_fetch_available_models.return_value = {"llama3.2:latest"}

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"response": "Generated text", "total_duration": 5_000_000}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = generate_text(
            system_prompt="System prompt",
            prompt="Student prompt",
        )

        self.assertEqual(result.text, "Generated text")
        self.assertEqual(result.latency_ms, 5)
        mock_start_ollama_server.assert_called_once()

    @patch("tutor.services.ollama_service.request.urlopen")
    @patch("tutor.services.ollama_service._pull_model")
    @patch("tutor.services.ollama_service._fetch_available_models")
    @patch("tutor.services.ollama_service._is_ollama_api_running", return_value=True)
    def test_generate_text_pulls_model_when_missing(
        self,
        mock_is_ollama_api_running,
        mock_fetch_available_models,
        mock_pull_model,
        mock_urlopen,
    ):
        mock_fetch_available_models.side_effect = [set(), set()]

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"response": "Generated text", "total_duration": 5_000_000}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = generate_text(
            system_prompt="System prompt",
            prompt="Student prompt",
        )

        self.assertEqual(result.text, "Generated text")
        mock_pull_model.assert_called_once_with(settings.OLLAMA_MODEL)

    @patch("tutor.services.ollama_service._ensure_model_available")
    @patch("tutor.services.ollama_service._ensure_ollama_running")
    @patch("tutor.services.ollama_service.request.urlopen")
    def test_generate_text_uses_selected_model_override(
        self,
        mock_urlopen,
        mock_ensure_ollama_running,
        mock_ensure_model_available,
    ):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(
            {"response": "Generated text", "total_duration": 5_000_000}
        ).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_response

        result = generate_text(
            system_prompt="System prompt",
            prompt="Student prompt",
            model_name="mistral:latest",
        )

        self.assertEqual(result.text, "Generated text")
        mock_ensure_ollama_running.assert_called_once()
        mock_ensure_model_available.assert_called_once_with("mistral:latest")


class ChatServiceTests(TestCase):
    def test_response_has_valid_citations_requires_in_range_markers(self):
        self.assertTrue(response_has_valid_citations("Liberty matters [1].", 2))
        self.assertFalse(response_has_valid_citations("Liberty matters.", 2))
        self.assertFalse(response_has_valid_citations("Liberty matters [3].", 2))

    def test_response_has_no_citations_rejects_bracket_markers(self):
        self.assertTrue(response_has_no_citations("Slightly beyond the video: liberty matters."))
        self.assertFalse(response_has_no_citations("Liberty matters [1]."))

    def test_build_citations_preserves_one_entry_per_retrieved_chunk(self):
        citations = build_citations(
            [
                {
                    "source_type": "sep",
                    "source_id": "liberalism",
                    "title": "Liberalism",
                    "section": "Liberty",
                    "subsection": "Mill",
                    "url": "https://example.com/liberalism",
                },
                {
                    "source_type": "sep",
                    "source_id": "liberalism",
                    "title": "Liberalism",
                    "section": "Liberty",
                    "subsection": "Mill",
                    "url": "https://example.com/liberalism",
                },
            ]
        )

        self.assertEqual(len(citations), 2)

    def test_build_prompt_marks_correct_interpolated_answer_context(self):
        prompt = build_prompt(
            {
                "session_id": "session-1",
                "message": "Because it protects other people.",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "interpolated_question": "According to Mill, what is the main principle that should guide restrictions on individual liberties?",
                "interpolated_answer_correct": True,
            },
            retrieval_context=RAG_CONTEXT,
        )

        self.assertIn(
            "The student's selected answer to that interpolated question was already marked correct.",
            prompt,
        )
        self.assertIn(
            "If you refer to correctness, make clear that the ORIGINAL multiple-choice answer was correct; do not imply that the student's latest explanation was automatically correct unless the evaluation metadata says so.",
            prompt,
        )

    def test_build_prompt_includes_explanation_outcome_metadata(self):
        prompt = build_prompt(
            {
                "session_id": "session-1",
                "message": "Because it sets a limit on coercion.",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
                "interpolated_question": "According to Mill, what principle should guide restrictions on liberty?",
                "interpolated_answer_correct": True,
                "explanation_outcome": "partial",
                "explanation_attempt": 2,
                "explanation_gap": "It omits that the limit is harm to others, not just disapproval.",
            },
            retrieval_context=RAG_CONTEXT,
        )

        self.assertIn(
            "The student's follow-up explanation has already been evaluated as: partial.",
            prompt,
        )
        self.assertIn(
            "This is the student's explanation attempt number: 2.",
            prompt,
        )
        self.assertIn(
            "The specific gap or missing idea to address is: It omits that the limit is harm to others, not just disapproval.",
            prompt,
        )

    def test_build_system_prompt_appends_explanation_outcome_addendum_for_each_outcome(self):
        # Each outcome must inject its distinct post-answer-evaluation guidance.
        for outcome in ("correct", "partial", "incorrect"):
            with self.subTest(outcome=outcome):
                result = _build_system_prompt(
                    SYSTEM_PROMPT,
                    {"explanation_outcome": outcome},
                )
                self.assertIn(EXPLANATION_OUTCOME_ADDENDA[outcome], result)
                self.assertTrue(result.endswith(GUARDRAIL_INSTRUCTIONS))

    def test_build_system_prompt_appends_classification_addendum_for_each_class(self):
        # Question-mode addenda are mutually exclusive — exactly one is appended.
        for classification in ("needs_clarification", "philosophical", "off_concept"):
            with self.subTest(classification=classification):
                result = _build_system_prompt(
                    SYSTEM_PROMPT,
                    {"question_classification": classification},
                )
                self.assertIn(CLASSIFICATION_ADDENDA[classification], result)
                self.assertTrue(result.endswith(GUARDRAIL_INSTRUCTIONS))

    def test_build_system_prompt_appends_support_strategy_addendum(self):
        for strategy in ("simplify", "analogise"):
            with self.subTest(strategy=strategy):
                result = _build_system_prompt(
                    SYSTEM_PROMPT,
                    {"support_strategy": strategy},
                )
                self.assertIn(SUPPORT_STRATEGY_ADDENDA[strategy], result)
                self.assertTrue(result.endswith(GUARDRAIL_INSTRUCTIONS))

    def test_build_system_prompt_hint_level_takes_precedence_over_other_addenda(self):
        # The chat_service elif chain ranks hint > support > classification.
        # If both hint_level and support_strategy/classification arrive, hint wins.
        scaffold_level = "Moderate Support (L3)"
        result = _build_system_prompt(
            SYSTEM_PROMPT,
            {
                "hint_level": 2,
                "current_scaffold_level": scaffold_level,
                "support_strategy": "simplify",
                "question_classification": "needs_clarification",
            },
        )
        self.assertIn(build_hint_addendum(2, scaffold_level), result)
        self.assertTrue(result.endswith(GUARDRAIL_INSTRUCTIONS))
        self.assertNotIn(SUPPORT_STRATEGY_ADDENDA["simplify"], result)
        self.assertNotIn(CLASSIFICATION_ADDENDA["needs_clarification"], result)

    def test_build_hint_addendum_varies_by_scaffold_level(self):
        # L1 hint 1 must be more supportive than L5 hint 1 — different text, not just scaffold label.
        low = build_hint_addendum(1, "Full Support (L1)")
        mid = build_hint_addendum(1, "Moderate Support (L3)")
        high = build_hint_addendum(1, "Minimal Support (L5)")
        self.assertNotEqual(low, mid)
        self.assertNotEqual(mid, high)
        self.assertNotEqual(low, high)
        # L1 hint 1 should be more directive (mention "name the key concept" or similar)
        self.assertIn("low scaffold level", low)
        # L5 hint 1 should push independent reasoning
        self.assertIn("high scaffold level", high)

    def test_build_hint_addendum_all_three_levels_vary_for_same_scaffold(self):
        scaffold = "Moderate Support (L3)"
        h1 = build_hint_addendum(1, scaffold)
        h2 = build_hint_addendum(2, scaffold)
        h3 = build_hint_addendum(3, scaffold)
        self.assertNotEqual(h1, h2)
        self.assertNotEqual(h2, h3)
        self.assertNotEqual(h1, h3)

    def test_build_system_prompt_hint_addendum_uses_scaffold_level_from_payload(self):
        # L1 and L5 payloads with the same hint_level must produce different system prompts.
        result_l1 = _build_system_prompt(
            SYSTEM_PROMPT,
            {"hint_level": 1, "current_scaffold_level": "Full Support (L1)"},
        )
        result_l5 = _build_system_prompt(
            SYSTEM_PROMPT,
            {"hint_level": 1, "current_scaffold_level": "Minimal Support (L5)"},
        )
        self.assertNotEqual(result_l1, result_l5)

    def test_build_system_prompt_support_strategy_takes_precedence_over_classification(self):
        result = _build_system_prompt(
            SYSTEM_PROMPT,
            {
                "support_strategy": "analogise",
                "question_classification": "philosophical",
            },
        )
        self.assertIn(SUPPORT_STRATEGY_ADDENDA["analogise"], result)
        self.assertTrue(result.endswith(GUARDRAIL_INSTRUCTIONS))
        self.assertNotIn(CLASSIFICATION_ADDENDA["philosophical"], result)

    def test_build_system_prompt_does_not_conflate_explanation_outcome_with_question_addenda(self):
        # Conflation guard: an evaluated-explanation turn must not also pull in
        # the question/support addenda. explanation_outcome is independent and
        # must always be appended; the others must not appear when only the
        # explanation outcome is set.
        result = _build_system_prompt(
            SYSTEM_PROMPT,
            {"explanation_outcome": "incorrect"},
        )
        self.assertIn(EXPLANATION_OUTCOME_ADDENDA["incorrect"], result)
        for addendum in CLASSIFICATION_ADDENDA.values():
            self.assertNotIn(addendum, result)
        for addendum in SUPPORT_STRATEGY_ADDENDA.values():
            self.assertNotIn(addendum, result)
        for level in (1, 2, 3):
            self.assertNotIn(build_hint_addendum(level, "Moderate Support (L3)"), result)

    def test_build_system_prompt_explanation_outcome_combines_with_question_addenda(self):
        # When the controller sends both — e.g. the student asked a question
        # while a pending-explanation turn is still attributed an attempt —
        # explanation_outcome must be appended FIRST, then the question addendum.
        # This pins ordering so the LLM sees the evaluation context before the
        # question-mode guidance.
        result = _build_system_prompt(
            SYSTEM_PROMPT,
            {
                "explanation_outcome": "partial",
                "question_classification": "needs_clarification",
            },
        )
        outcome_idx = result.index(EXPLANATION_OUTCOME_ADDENDA["partial"])
        classification_idx = result.index(CLASSIFICATION_ADDENDA["needs_clarification"])
        self.assertLess(outcome_idx, classification_idx)

    def test_build_explanation_evaluation_prompt_includes_correct_answer_and_context(self):
        prompt = _build_explanation_evaluation_prompt(
            "What is the harm principle?",
            "Preventing harm to others",
            "It limits coercion.",
            ["Mill distinguishes harm from offence."],
        )

        self.assertIn("Correct answer: Preventing harm to others", prompt)
        self.assertIn("Student explanation: It limits coercion.", prompt)
        self.assertIn("[1] Mill distinguishes harm from offence.", prompt)

    def test_build_consolidation_prompt_includes_gap_focus(self):
        prompt = _build_consolidation_prompt(
            "What is the harm principle?",
            "It means people should be nice.",
            ["Mill distinguishes harm from offence."],
            gap_focus="The student misses that offence is not the same as harm to others.",
        )

        self.assertIn(
            "Specific gap to probe: The student misses that offence is not the same as harm to others.",
            prompt,
        )
        self.assertIn(
            "At least one question must directly test this missing idea, not just the overall concept.",
            prompt,
        )

    def test_build_discussion_check_prompt_includes_question_classification(self):
        prompt = _build_discussion_check_prompt(
            "What is the harm principle?",
            "Why is offence not enough?",
            "philosophical",
            ["Mill distinguishes harm from offence."],
        )

        self.assertIn("Student question: Why is offence not enough?", prompt)
        self.assertIn("Question classification: philosophical", prompt)
        self.assertIn("[1] Mill distinguishes harm from offence.", prompt)

    def test_parse_valid_consolidation_questions_rejects_ambiguous_correct_option(self):
        questions = _parse_valid_consolidation_questions(
            [
                {
                    "question": "Does Mill think offence alone justifies limiting speech?",
                    "options": [
                        "Yes, because offence is always harm.",
                        "No, as long as someone is offended.",
                        "Only when the state prefers it.",
                        "Only when a majority votes for it.",
                    ],
                    "correct_index": 1,
                }
            ]
        )

        self.assertEqual(questions, [])

    def test_parse_valid_consolidation_questions_accepts_valid_grounded_item(self):
        citations = build_citations(RAG_METADATAS)

        questions = _parse_valid_consolidation_questions(
            [
                {
                    "question": "Which case best fits the harm principle [1]?",
                    "options": [
                        "Restricting conduct that harms others",
                        "Banning harmless dissent",
                        "Forcing virtue by law",
                        "Punishing unpopular beliefs",
                    ],
                    "correct_index": 0,
                }
            ],
            citations=citations,
        )

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0].question, "Which case best fits the harm principle [1]?")
        self.assertEqual(questions[0].correct_index, 0)
        self.assertEqual(questions[0].citations, citations)

    def test_parse_valid_consolidation_questions_requires_citations_when_context_exists(self):
        questions = _parse_valid_consolidation_questions(
            [
                {
                    "question": "What does the harm principle focus on?",
                    "options": [
                        "Preventing harm to others",
                        "Obeying tradition",
                        "Avoiding disagreement",
                        "Following majority rule",
                    ],
                    "correct_index": 0,
                }
            ],
            citations=build_citations(RAG_METADATAS),
        )

        self.assertEqual(questions, [])

    def test_parse_valid_consolidation_questions_rejects_out_of_range_citation_marker(self):
        questions = _parse_valid_consolidation_questions(
            [
                {
                    "question": "Which case best fits the harm principle [2]?",
                    "options": [
                        "Restricting conduct that harms others",
                        "Banning harmless dissent",
                        "Forcing virtue by law",
                        "Punishing unpopular beliefs",
                    ],
                    "correct_index": 0,
                }
            ],
            citations=build_citations(RAG_METADATAS),
        )

        self.assertEqual(questions, [])

    def test_parse_valid_consolidation_questions_rejects_overlapping_incorrect_option(self):
        questions = _parse_valid_consolidation_questions(
            [
                {
                    "question": "What does the harm principle focus on?",
                    "options": [
                        "Preventing harm to others",
                        "Preventing harm to others in society",
                        "Obeying tradition",
                        "Avoiding disagreement",
                    ],
                    "correct_index": 0,
                }
            ]
        )

        self.assertEqual(questions, [])

    def test_build_consolidation_prompt_includes_original_question_and_context(self):
        prompt = _build_consolidation_prompt(
            "What is the harm principle?",
            "It means people should be nice.",
            ["Mill distinguishes harm from offence."],
        )

        self.assertIn("Original interpolated question: What is the harm principle?", prompt)
        self.assertIn("[1] Mill distinguishes harm from offence.", prompt)

    def test_build_mastery_prompt_includes_student_strength_and_context(self):
        prompt = _build_mastery_prompt(
            "What is the harm principle?",
            "It limits coercion to cases where someone harms others.",
            ["Mill distinguishes harm from offence."],
        )

        self.assertIn("Student's strong explanation: It limits coercion to cases where someone harms others.", prompt)
        self.assertIn("[1] Mill distinguishes harm from offence.", prompt)

    @patch("tutor.services.chat_service.generate_text")
    def test_generate_chat_response_retries_until_output_is_cited(self, mock_generate_text):
        mock_generate_text.side_effect = [
            MagicMock(text="Liberty matters.", latency_ms=10),
            MagicMock(text="Liberty matters because it protects choice [1].", latency_ms=12),
        ]

        result = generate_chat_response(
            payload={
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
            },
            retrieval_context=RAG_CONTEXT,
            retrieval_metadatas=RAG_METADATAS,
        )

        self.assertEqual(result.response, "Liberty matters because it protects choice [1].")
        self.assertEqual(len(result.citations), 1)
        self.assertEqual(mock_generate_text.call_count, 2)

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.generate_text")
    def test_generate_explanation_outcome_returns_valid_label(
        self,
        mock_generate_text,
        mock_retrieve_consolidation_context,
    ):
        mock_generate_text.return_value = MagicMock(
            text='{"outcome":"incorrect","gap_focus":"The student confuses harm with mere offence."}',
            latency_ms=9,
        )

        outcome = generate_explanation_outcome(
            original_question="What is the harm principle?",
            correct_answer="Preventing harm to others",
            student_explanation="It means the state should stop offensive speech.",
            topic="liberalism",
        )

        self.assertEqual(
            outcome,
            {
                "outcome": "incorrect",
                "gap_focus": "The student confuses harm with mere offence.",
            },
        )
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.generate_text")
    def test_generate_discussion_check_returns_question_and_explanation(
        self,
        mock_generate_text,
        mock_retrieve_consolidation_context,
    ):
        mock_generate_text.return_value = MagicMock(
            text=json.dumps(
                {
                    "question": {
                        "question": "Which case best fits the harm principle [1]?",
                        "options": [
                            "Restricting conduct that harms others",
                            "Banning harmless offence",
                            "Punishing harmless eccentricity",
                            "Forcing virtue by law",
                        ],
                        "correct_index": 0,
                    },
                    "explanation": "Mill distinguishes harm to others from mere offence, so only the first case justifies coercion.",
                }
            ),
            latency_ms=11,
        )

        result = generate_discussion_check(
            original_question="What is the harm principle?",
            student_question="Why is offence not enough?",
            question_classification="needs_clarification",
            topic="liberalism",
        )

        self.assertIsNotNone(result.question)
        self.assertEqual(result.question.correct_index, 0)
        self.assertEqual(
            result.explanation,
            "Mill distinguishes harm to others from mere offence, so only the first case justifies coercion.",
        )
        self.assertEqual(result.latency_ms, 11)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=([], []),
    )
    @patch("tutor.services.question_service.logger.warning")
    @patch("tutor.services.question_service.generate_text")
    def test_generate_discussion_check_returns_empty_result_when_no_context(
        self,
        mock_generate_text,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        result = generate_discussion_check(
            original_question="What is the harm principle?",
            student_question="Why is offence not enough?",
            question_classification="needs_clarification",
            topic="liberalism",
        )

        self.assertIsNone(result.question)
        self.assertEqual(result.explanation, "")
        self.assertEqual(result.latency_ms, 0)
        mock_generate_text.assert_not_called()
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )
        mock_log_warning.assert_called_once_with("No usable RAG context found for discussion-check generation")

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.logger.warning")
    @patch("tutor.services.question_service.generate_text")
    def test_generate_discussion_check_retries_after_invalid_json(
        self,
        mock_generate_text,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        mock_generate_text.side_effect = [
            MagicMock(text="not json", latency_ms=5),
            MagicMock(
                text=json.dumps(
                    {
                        "question": {
                            "question": "Which case best fits the harm principle [1]?",
                            "options": [
                                "Restricting conduct that harms others",
                                "Banning harmless offence",
                                "Punishing harmless eccentricity",
                                "Forcing virtue by law",
                            ],
                            "correct_index": 0,
                        },
                        "explanation": "Mill distinguishes harm to others from mere offence, so only the first case justifies coercion.",
                    }
                ),
                latency_ms=7,
            ),
        ]

        result = generate_discussion_check(
            original_question="What is the harm principle?",
            student_question="Why is offence not enough?",
            question_classification="needs_clarification",
            topic="liberalism",
        )

        self.assertIsNotNone(result.question)
        self.assertEqual(result.question.correct_index, 0)
        self.assertEqual(result.latency_ms, 12)
        self.assertEqual(mock_generate_text.call_count, 2)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )
        mock_log_warning.assert_called_once_with(
            "Discussion-check generation returned invalid JSON on attempt %s",
            1,
        )

    @patch("tutor.services.chat_service.generate_text")
    def test_generate_chat_response_raises_when_model_never_returns_valid_citations(
        self,
        mock_generate_text,
    ):
        mock_generate_text.side_effect = [
            MagicMock(text="Liberty matters.", latency_ms=10),
            MagicMock(text="Still uncited.", latency_ms=12),
        ]

        with self.assertRaisesRegex(
            ValueError,
            "LLM reply failed validation after retry.",
        ):
            generate_chat_response(
                payload={
                    "session_id": "session-1",
                    "message": "What is liberalism?",
                    "topic": "liberalism",
                    "timestamp": 120,
                    "current_scaffold_level": "Moderate Support",
                },
                retrieval_context=RAG_CONTEXT,
                retrieval_metadatas=RAG_METADATAS,
            )

    @patch("tutor.services.chat_service.generate_text")
    def test_generate_fallback_chat_response_retries_until_output_has_no_citations(
        self,
        mock_generate_text,
    ):
        mock_generate_text.side_effect = [
            MagicMock(text="Slightly beyond the video: liberty matters [1]. What do you notice in the video?", latency_ms=10),
            MagicMock(text="Slightly beyond the video: liberty matters for limiting coercion. How does that fit the example from the video?", latency_ms=12),
        ]

        result = generate_fallback_chat_response(
            {
                "session_id": "session-1",
                "message": "What is liberalism?",
                "topic": "liberalism",
                "timestamp": 120,
                "current_scaffold_level": "Moderate Support",
            }
        )

        self.assertEqual(
            result.response,
            "Slightly beyond the video: liberty matters for limiting coercion. How does that fit the example from the video?",
        )
        self.assertEqual(result.citations, [])
        self.assertEqual(mock_generate_text.call_count, 2)

    @patch("tutor.services.chat_service.generate_text")
    def test_generate_fallback_chat_response_raises_when_output_keeps_citations(
        self,
        mock_generate_text,
    ):
        mock_generate_text.side_effect = [
            MagicMock(text="Slightly beyond the video: liberty matters [1].", latency_ms=10),
            MagicMock(text="Still cited [1].", latency_ms=12),
        ]

        with self.assertRaisesRegex(
            ValueError,
            "LLM reply failed validation after retry.",
        ):
            generate_fallback_chat_response(
                {
                    "session_id": "session-1",
                    "message": "What is liberalism?",
                    "topic": "liberalism",
                    "timestamp": 120,
                    "current_scaffold_level": "Moderate Support",
                }
            )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.logger.warning")
    @patch("tutor.services.question_service.generate_text")
    def test_generate_consolidation_questions_retries_when_first_attempt_is_ambiguous(
        self,
        mock_generate_text,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        mock_generate_text.side_effect = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question": "Does offence alone justify restricting liberty [1]?",
                            "options": [
                                "Yes, whenever people feel upset.",
                                "No, as long as someone is offended.",
                                "Only if custom supports it.",
                                "Only if most people agree.",
                            ],
                            "correct_index": 1,
                        },
                        {
                            "question": "What does liberty protect?",
                            "options": [
                                "Personal choice",
                                "Blind obedience",
                                "State control",
                                "Social uniformity",
                            ],
                            "correct_index": 0,
                        },
                    ]
                ),
                latency_ms=10,
            ),
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question": "Does offence alone justify restricting liberty [1]?",
                            "options": [
                                "Yes, because offence is the same as harm.",
                                "No, because Mill distinguishes offence from harm to others.",
                                "Only if a leader commands it.",
                                "Only if elections demand it.",
                            ],
                            "correct_index": 1,
                        },
                        {
                            "question": "What does liberty protect in self-regarding matters [1]?",
                            "options": [
                                "Personal choice in self-regarding matters",
                                "Blind obedience to majority opinion",
                                "State control of every decision",
                                "Social pressure to conform",
                            ],
                            "correct_index": 0,
                        },
                    ]
                ),
                latency_ms=12,
            ),
        ]

        result = generate_consolidation_questions(
            original_question="What is the harm principle?",
            student_explanation="It means people should just be nice.",
            gap_focus="The student confuses harm with mere offence.",
            topic="liberalism",
        )

        self.assertEqual(len(result.questions), 2)
        self.assertEqual(result.questions[0].correct_index, 1)
        self.assertEqual(len(result.questions[0].citations), 1)
        self.assertEqual(result.latency_ms, 22)
        self.assertEqual(mock_generate_text.call_count, 2)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )
        mock_log_warning.assert_any_call(
            "%s produced %s valid item(s) on attempt %s",
            "Consolidation question generation",
            0,
            1,
        )
        sent_prompt = mock_generate_text.call_args_list[0].kwargs["prompt"]
        self.assertIn(
            "Specific gap to probe: The student confuses harm with mere offence.",
            sent_prompt,
        )
        retry_system_prompt = mock_generate_text.call_args_list[1].kwargs["system_prompt"]
        self.assertIn("## Output correction", retry_system_prompt)
        self.assertIn(
            "Each question stem MUST include at least one inline citation marker like [1] or [2] from the retrieved chunks.",
            retry_system_prompt,
        )
        self.assertIn(
            "IMPORTANT: your previous attempt had no valid citation marker",
            retry_system_prompt,
        )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.logger.warning")
    @patch("tutor.services.question_service.generate_text")
    def test_generate_consolidation_questions_safely_skips_invalid_items_after_retry(
        self,
        mock_generate_text,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        invalid_payload = json.dumps(
            [
                {
                    "question": "What does liberty protect [1]?",
                    "options": [
                        "Personal choice",
                        "Personal choice in society",
                        "State control",
                        "Tradition",
                    ],
                    "correct_index": 0,
                }
            ]
        )
        mock_generate_text.side_effect = [
            MagicMock(text=invalid_payload, latency_ms=10),
            MagicMock(text=invalid_payload, latency_ms=12),
        ]

        result = generate_consolidation_questions(
            original_question="What is liberty?",
            student_explanation="It means doing whatever you want.",
            topic="liberalism",
        )

        self.assertEqual(result.questions, [])
        self.assertEqual(result.latency_ms, 22)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is liberty?",
            topic="liberalism",
        )
        mock_log_warning.assert_any_call(
            "%s rejection details on attempt %s: %s",
            "Consolidation question generation",
            1,
            "item 1: one or more distractors overlap too much with the correct option",
        )
        mock_log_warning.assert_any_call(
            "%s rejection details on attempt %s: %s",
            "Consolidation question generation",
            2,
            "item 1: one or more distractors overlap too much with the correct option",
        )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.logger.warning")
    @patch("tutor.services.question_service.generate_text")
    def test_generate_consolidation_questions_preserves_best_partial_result_across_retries(
        self,
        mock_generate_text,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        mock_generate_text.side_effect = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question": "Which case best fits the harm principle [1]?",
                            "options": [
                                "Restricting conduct that harms others",
                                "Banning opinions that offend people",
                                "Compelling moral improvement by law",
                                "Silencing harmless dissent",
                            ],
                            "correct_index": 0,
                        }
                    ]
                ),
                latency_ms=10,
            ),
            MagicMock(text='{"question":"bad"}', latency_ms=12),
        ]

        result = generate_consolidation_questions(
            original_question="What is the harm principle?",
            student_explanation="I guessed.",
            topic="liberalism",
        )

        self.assertEqual(len(result.questions), 1)
        self.assertEqual(result.questions[0].correct_index, 0)
        self.assertEqual(result.latency_ms, 22)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )
        mock_log_warning.assert_any_call(
            "%s produced %s valid item(s) on attempt %s",
            "Consolidation question generation",
            0,
            2,
        )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=([], []),
    )
    @patch("tutor.services.question_service.logger.warning")
    def test_generate_consolidation_questions_returns_empty_when_rag_missing(
        self,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        result = generate_consolidation_questions(
            original_question="What is liberty?",
            student_explanation="It means doing whatever you want.",
            topic="liberalism",
        )

        self.assertEqual(result.questions, [])
        self.assertEqual(result.latency_ms, 0)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is liberty?",
            topic="liberalism",
        )
        mock_log_warning.assert_called_once_with("No usable RAG context found for consolidation question generation")

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.logger.warning")
    @patch("tutor.services.question_service.generate_text")
    def test_generate_mastery_question_retries_until_single_valid_question(
        self,
        mock_generate_text,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        mock_generate_text.side_effect = [
            MagicMock(text='{"question":"bad"}', latency_ms=10),
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question": "Which case best fits the harm principle [1]?",
                            "options": [
                                "Restricting conduct that harms others",
                                "Banning opinions that offend people",
                                "Compelling moral improvement by law",
                                "Silencing harmless dissent",
                            ],
                            "correct_index": 0,
                        }
                    ]
                ),
                latency_ms=12,
            ),
        ]

        result = generate_mastery_question(
            original_question="What is the harm principle?",
            student_explanation="It limits coercion to harm-prevention.",
            topic="liberalism",
        )

        self.assertIsNotNone(result.question)
        self.assertEqual(result.question.correct_index, 0)
        self.assertEqual(len(result.question.citations), 1)
        self.assertEqual(result.latency_ms, 22)
        self.assertEqual(mock_generate_text.call_count, 2)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )
        mock_log_warning.assert_any_call(
            "%s produced %s valid item(s) on attempt %s",
            "Mastery question generation",
            0,
            1,
        )
        mock_log_warning.assert_any_call(
            "%s raw output on attempt %s: %r",
            "Mastery question generation",
            1,
            '{"question":"bad"}',
        )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=(["Mill distinguishes harm from offence."], RAG_METADATAS),
    )
    @patch("tutor.services.question_service.generate_text")
    def test_generate_mastery_question_stops_after_first_valid_grounded_item(
        self,
        mock_generate_text,
        mock_retrieve_consolidation_context,
    ):
        mock_generate_text.side_effect = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question": "Which case best fits the harm principle [1]?",
                            "options": [
                                "Restricting conduct that harms others",
                                "Banning opinions that offend people",
                                "Compelling moral improvement by law",
                                "Silencing harmless dissent",
                            ],
                            "correct_index": 0,
                        }
                    ]
                ),
                latency_ms=10,
            ),
            MagicMock(text='{"question":"bad"}', latency_ms=12),
        ]

        result = generate_mastery_question(
            original_question="What is the harm principle?",
            student_explanation="It limits coercion to harm-prevention.",
            topic="liberalism",
        )

        self.assertIsNotNone(result.question)
        self.assertEqual(result.question.correct_index, 0)
        self.assertEqual(result.question.question, "Which case best fits the harm principle [1]?")
        self.assertEqual(result.latency_ms, 10)
        self.assertEqual(mock_generate_text.call_count, 1)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is the harm principle?",
            topic="liberalism",
        )

    @patch(
        "tutor.services.question_service._retrieve_consolidation_context",
        return_value=([], []),
    )
    @patch("tutor.services.question_service.logger.warning")
    def test_generate_mastery_question_returns_empty_when_rag_missing(
        self,
        mock_log_warning,
        mock_retrieve_consolidation_context,
    ):
        result = generate_mastery_question(
            original_question="What is liberty?",
            student_explanation="It protects self-regarding choice.",
            topic="liberalism",
        )

        self.assertIsNone(result.question)
        self.assertEqual(result.latency_ms, 0)
        mock_retrieve_consolidation_context.assert_called_once_with(
            "What is liberty?",
            topic="liberalism",
        )
        mock_log_warning.assert_called_once_with("No usable RAG context found for mastery question generation")


class QuestionGenerationEndpointTests(APITestCase):
    @patch("tutor.views_questions._select_interpolated_chunks")
    @patch("tutor.views_questions.generate_text")
    def test_pre_question_generation_persists_grounding_citations(
        self,
        mock_generate_text,
        mock_select_interpolated_chunks,
    ):
        mock_select_interpolated_chunks.return_value = [
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 30,
                    "end_time": 45,
                },
                "Coercion is justified only to prevent harm to others.",
            ),
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 60,
                    "end_time": 75,
                },
                "Mill distinguishes harm from mere offence.",
            ),
        ]
        mock_generate_text.side_effect = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question_text": "According to Mill, when is coercion justified?",
                            "option_a": "To prevent harm to others",
                            "option_b": "To enforce private virtue",
                            "option_c": "To suppress unpopular views",
                            "option_d": "To punish harmless offence",
                            "correct_index": 0,
                            "support_quote": "Coercion is justified only to prevent harm to others.",
                        }
                    ]
                ),
                latency_ms=11,
            ),
            MagicMock(
                text="YES The excerpt states the condition for justified coercion directly.",
                latency_ms=7,
            ),
        ]

        response = self.client.post(
            "/api/questions/generate/",
            data={"topic": "liberalism", "quiz_type": "pre", "count": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = response.json()["created"][0]
        self.assertEqual(len(created["citations"]), 1)
        self.assertEqual(created["citations"][0]["source_type"], "transcript")
        self.assertEqual(created["citations"][0]["location"], "0:30–0:45")
        self.assertEqual(created["transcript_excerpt"], "Coercion is justified only to prevent harm to others.")
        self.assertEqual(created["timestamp"], 45.0)
        self.assertEqual(created["rewatch_start"], 30.0)

        saved = Question.objects.get(id=created["id"])
        self.assertEqual(saved.transcript_excerpt, "Coercion is justified only to prevent harm to others.")
        self.assertEqual(json.loads(saved.citations_json)[0]["source_type"], "transcript")

    @patch("tutor.views_questions._check_question_grounding")
    @patch("tutor.views_questions.generate_text")
    @patch("tutor.views_questions._select_interpolated_chunks")
    def test_interpolated_question_generation_persists_transcript_citation(
        self,
        mock_select_interpolated_chunks,
        mock_generate_text,
        mock_check_question_grounding,
    ):
        mock_select_interpolated_chunks.return_value = [
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 12,
                    "end_time": 28,
                },
                "Mill says the only reason to limit liberty is to prevent harm to others.",
            )
        ]
        mock_generate_text.return_value = MagicMock(
            text=json.dumps(
                [
                    {
                        "question_text": "What reason does Mill give for limiting liberty?",
                        "option_a": "Preventing harm to others",
                        "option_b": "Promoting shared morality",
                        "option_c": "Avoiding public disagreement",
                        "option_d": "Rewarding good character",
                        "correct_index": 0,
                        "support_quote": "the only reason to limit liberty is to prevent harm to others",
                    }
                ]
            ),
            latency_ms=13,
        )
        mock_check_question_grounding.return_value = ("ok", "Supported by the excerpt.")

        response = self.client.post(
            "/api/questions/generate/",
            data={"topic": "liberalism", "quiz_type": "interpolated", "count": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = response.json()["created"][0]
        self.assertEqual(created["transcript_excerpt"], "Mill says the only reason to limit liberty is to prevent harm to others.")
        self.assertEqual(len(created["citations"]), 1)
        self.assertEqual(created["citations"][0]["source_type"], "transcript")
        self.assertEqual(created["citations"][0]["start_time"], 12)

    def test_question_list_exposes_saved_citations(self):
        question = Question.objects.create(
            topic="liberalism",
            quiz_type="pre",
            order_index=0,
            question_text="What is Mill's harm principle?",
            option_a="Prevent harm to others",
            option_b="Promote virtue",
            option_c="Punish offence",
            option_d="Protect tradition",
            correct_index=0,
            transcript_excerpt="Coercion is justified only to prevent harm to others.",
            citations_json=json.dumps(
                [
                    {
                        "source_type": "transcript",
                        "source_id": "liberalism-video",
                        "title": "Lecture: liberalism",
                        "url": "",
                        "location": "0:30–0:45",
                        "start_time": 30,
                    }
                ]
            ),
        )

        response = self.client.get("/api/questions/?topic=liberalism&quiz_type=pre")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()[0]["id"], question.id)
        self.assertEqual(response.json()[0]["citations"][0]["location"], "0:30–0:45")
        self.assertEqual(response.json()[0]["transcript_excerpt"], "Coercion is justified only to prevent harm to others.")


    @patch("tutor.views_questions._select_interpolated_chunks")
    @patch("tutor.views_questions.generate_text")
    def test_pre_question_generation_retries_until_requested_count_without_duplicates(
        self,
        mock_generate_text,
        mock_select_interpolated_chunks,
    ):
        Question.objects.create(
            topic="liberalism",
            quiz_type="pre",
            order_index=0,
            question_text="According to Mill, when is coercion justified?",
            option_a="To prevent harm to others",
            option_b="To enforce virtue",
            option_c="To silence dissent",
            option_d="To punish offence",
            correct_index=0,
            transcript_excerpt="Coercion is justified only to prevent harm to others.",
        )
        mock_select_interpolated_chunks.return_value = [
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 30,
                    "end_time": 45,
                },
                "Coercion is justified only to prevent harm to others.",
            ),
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 60,
                    "end_time": 75,
                },
                "Mill distinguishes harm from mere offence.",
            ),
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 90,
                    "end_time": 105,
                },
                "Mill rejects coercion for mere offence alone.",
            ),
        ]
        mock_generate_text.side_effect = [
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question_text": "What distinction does Mill draw between harm and offence?",
                            "option_a": "Harm can justify coercion; offence alone cannot",
                            "option_b": "Offence is worse than harm",
                            "option_c": "Harm and offence are identical",
                            "option_d": "Offence justifies coercion more than harm",
                            "correct_index": 0,
                            "support_quote": "Mill distinguishes harm from mere offence.",
                        },
                    ]
                ),
                latency_ms=11,
            ),
            MagicMock(
                text="YES The excerpt states the distinction directly.",
                latency_ms=7,
            ),
            MagicMock(
                text=json.dumps(
                    [
                        {
                            "question_text": "Why does Mill reject coercion for mere offence alone?",
                            "option_a": "Because offence alone is not harm to others",
                            "option_b": "Because offence always strengthens liberty",
                            "option_c": "Because offence is identical to fraud",
                            "option_d": "Because offence is worse than violence",
                            "correct_index": 0,
                            "support_quote": "Mill rejects coercion for mere offence alone.",
                        }
                    ]
                ),
                latency_ms=9,
            ),
            MagicMock(
                text="YES The excerpt explains why mere offence alone is insufficient.",
                latency_ms=6,
            ),
        ]

        response = self.client.post(
            "/api/questions/generate/",
            data={"topic": "liberalism", "quiz_type": "pre", "count": 2},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.json()["created"]), 2)
        self.assertEqual(
            Question.objects.filter(topic="liberalism", quiz_type="pre").count(),
            3,
        )
        saved_texts = list(
            Question.objects
            .filter(topic="liberalism", quiz_type="pre")
            .order_by("order_index")
            .values_list("question_text", flat=True)
        )
        self.assertEqual(len(saved_texts), len(set(saved_texts)))
        saved_excerpts = list(
            Question.objects
            .filter(topic="liberalism", quiz_type="pre")
            .order_by("order_index")
            .values_list("transcript_excerpt", flat=True)
        )
        self.assertEqual(len(saved_excerpts), len(set(saved_excerpts)))

    @patch("tutor.views_questions._check_question_grounding")
    @patch("tutor.views_questions.generate_text")
    @patch("tutor.views_questions._select_interpolated_chunks")
    def test_interpolated_generation_skips_previously_used_excerpt(
        self,
        mock_select_interpolated_chunks,
        mock_generate_text,
        mock_check_question_grounding,
    ):
        Question.objects.create(
            topic="liberalism",
            quiz_type="interpolated",
            order_index=0,
            question_text="Existing question",
            option_a="A",
            option_b="B",
            option_c="C",
            option_d="D",
            correct_index=0,
            transcript_excerpt="First excerpt text.",
        )
        mock_select_interpolated_chunks.return_value = [
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 10,
                    "end_time": 20,
                },
                "First excerpt text.",
            ),
            (
                {
                    "source_type": "transcript",
                    "source_id": "liberalism-video",
                    "topic": "liberalism",
                    "start_time": 30,
                    "end_time": 40,
                },
                "Second excerpt text.",
            ),
        ]
        mock_generate_text.return_value = MagicMock(
            text=json.dumps(
                [
                    {
                        "question_text": "What does the second excerpt say?",
                        "option_a": "It states a different point",
                        "option_b": "It repeats the first excerpt",
                        "option_c": "It contains no claim",
                        "option_d": "It rejects the lecture",
                        "correct_index": 0,
                        "support_quote": "Second excerpt text.",
                    }
                ]
            ),
            latency_ms=13,
        )
        mock_check_question_grounding.return_value = ("ok", "Supported by the excerpt.")

        response = self.client.post(
            "/api/questions/generate/",
            data={"topic": "liberalism", "quiz_type": "interpolated", "count": 1},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        created = response.json()["created"][0]
        self.assertEqual(created["transcript_excerpt"], "Second excerpt text.")


class ParticipantSessionTests(APITestCase):
    def test_create_session_returns_201_on_new_participant(self):
        response = self.client.post(
            "/api/participants/create/",
            data={"participant_id": "12345", "group": "A"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["created"])

    def test_create_session_returns_200_if_participant_already_exists(self):
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "12345", "group": "A"},
            format="json",
        )
        response = self.client.post(
            "/api/participants/create/",
            data={"participant_id": "12345", "group": "A"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["created"])

    def test_create_session_rejects_non_5_digit_id(self):
        response = self.client.post(
            "/api/participants/create/",
            data={"participant_id": "abc", "group": "A"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_session_rejects_invalid_group(self):
        response = self.client.post(
            "/api/participants/create/",
            data={"participant_id": "12345", "group": "Z"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_create_session_sets_tutor_topic_from_group(self):
        from tutor.models import ParticipantSession
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "99001", "group": "A"},
            format="json",
        )
        session = ParticipantSession.objects.get(participant_id="99001")
        self.assertEqual(session.tutor_topic, "liberalism")

    def test_finalise_session_saves_scores_and_marks_complete(self):
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "55555", "group": "B"},
            format="json",
        )
        response = self.client.post(
            "/api/participants/55555/finalise/",
            data={
                "lib_pre_correct": 4, "lib_pre_total": 7,
                "lib_post_correct": 6, "lib_post_total": 7,
                "rep_pre_correct": 3, "rep_pre_total": 7,
                "rep_post_correct": 5, "rep_post_total": 7,
                "final_scaffold_score": 1.75,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        from tutor.models import ParticipantSession
        session = ParticipantSession.objects.get(participant_id="55555")
        self.assertTrue(session.completed)
        self.assertEqual(session.lib_pre_correct, 4)
        self.assertEqual(session.lib_post_correct, 6)
        self.assertEqual(session.rep_pre_correct, 3)
        self.assertEqual(session.rep_post_correct, 5)
        self.assertAlmostEqual(session.final_scaffold_score, 1.75)
        self.assertIsNotNone(session.completed_at)

    def test_finalise_session_saves_chat_messages(self):
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "55556", "group": "A"},
            format="json",
        )
        messages = [
            {"sender": "tutor", "text": "What is the harm principle?", "sent_at": "2026-01-01T10:00:00Z"},
            {"sender": "user",  "text": "It limits liberty to prevent harm.", "sent_at": "2026-01-01T10:00:05Z"},
        ]
        self.client.post(
            "/api/participants/55556/finalise/",
            data={"lib_pre_correct": 5, "lib_pre_total": 7, "chat_messages": messages},
            format="json",
        )
        from tutor.models import ChatMessage
        saved = list(ChatMessage.objects.filter(session__participant_id="55556").order_by('sent_at'))
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[0].sender, "tutor")
        self.assertEqual(saved[1].text, "It limits liberty to prevent harm.")

    def test_finalise_session_returns_404_for_unknown_participant(self):
        response = self.client.post(
            "/api/participants/00000/finalise/",
            data={"lib_pre_correct": 3, "lib_pre_total": 7},
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_record_attempt_creates_row_linked_to_session(self):
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "77777", "group": "C"},
            format="json",
        )
        response = self.client.post(
            "/api/participants/77777/attempt/",
            data={
                "question_id": 42,
                "question_text": "What is the harm principle?",
                "topic": "liberalism",
                "correct": True,
                "attempt_count": 1,
                "used_hint": False,
                "rewatched": False,
                "scaffold_score_after": 2.0,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        from tutor.models import InterpolatedAttempt
        attempt = InterpolatedAttempt.objects.get(id=response.data["attempt_id"])
        self.assertEqual(attempt.question_id, 42)
        self.assertTrue(attempt.correct)
        self.assertEqual(attempt.session.participant_id, "77777")

    def test_record_attempt_returns_400_when_fields_missing(self):
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "88888", "group": "D"},
            format="json",
        )
        response = self.client.post(
            "/api/participants/88888/attempt/",
            data={"question_id": 1},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_record_attempt_returns_404_for_unknown_participant(self):
        response = self.client.post(
            "/api/participants/00001/attempt/",
            data={
                "question_id": 1,
                "question_text": "Q",
                "topic": "liberalism",
                "correct": True,
                "attempt_count": 1,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 404)

    def test_record_consent_saves_all_five_required_fields(self):
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "54321", "group": "A"},
            format="json",
        )
        response = self.client.post(
            "/api/participants/54321/consent/",
            data={
                "info_sheet": True,
                "over_18": True,
                "stem_student": True,
                "consent_form": True,
                "post_session_questionnaire": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        from tutor.models import ConsentRecord
        record = ConsentRecord.objects.get(session__participant_id="54321")
        self.assertTrue(record.info_sheet)
        self.assertTrue(record.over_18)
        self.assertTrue(record.stem_student)
        self.assertTrue(record.consent_form)
        self.assertTrue(record.post_session_questionnaire)

    def test_record_consent_requires_post_session_questionnaire_field(self):
        self.client.post(
            "/api/participants/create/",
            data={"participant_id": "54322", "group": "B"},
            format="json",
        )
        response = self.client.post(
            "/api/participants/54322/consent/",
            data={
                "info_sheet": True,
                "over_18": True,
                "stem_student": True,
                "consent_form": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("post_session_questionnaire", response.data["error"])

    def test_sessions_list_returns_all_sessions(self):
        self.client.post("/api/participants/create/", data={"participant_id": "11111", "group": "A"}, format="json")
        self.client.post("/api/participants/create/", data={"participant_id": "22222", "group": "B"}, format="json")
        response = self.client.get("/api/participants/")
        self.assertEqual(response.status_code, 200)
        ids = [s["participant_id"] for s in response.data]
        self.assertIn("11111", ids)
        self.assertIn("22222", ids)

    def test_export_csv_sessions_returns_csv_content(self):
        self.client.post("/api/participants/create/", data={"participant_id": "33333", "group": "A"}, format="json")
        response = self.client.get("/api/participants/export/?table=sessions")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        content = b"".join(response.streaming_content).decode() if hasattr(response, "streaming_content") else response.content.decode()
        self.assertIn("participant_id", content)
        self.assertIn("33333", content)

    def test_delete_session_removes_record_and_returns_204(self):
        self.client.post("/api/participants/create/", data={"participant_id": "66666", "group": "A"}, format="json")
        response = self.client.delete("/api/participants/66666/")
        self.assertEqual(response.status_code, 204)
        from tutor.models import ParticipantSession
        self.assertFalse(ParticipantSession.objects.filter(participant_id="66666").exists())

    def test_delete_session_also_removes_linked_attempts(self):
        self.client.post("/api/participants/create/", data={"participant_id": "77701", "group": "B"}, format="json")
        self.client.post(
            "/api/participants/77701/attempt/",
            data={"question_id": 1, "question_text": "Q", "topic": "liberalism", "correct": True, "attempt_count": 1},
            format="json",
        )
        self.client.delete("/api/participants/77701/")
        from tutor.models import InterpolatedAttempt, ParticipantSession
        self.assertFalse(ParticipantSession.objects.filter(participant_id="77701").exists())
        self.assertFalse(InterpolatedAttempt.objects.filter(session__participant_id="77701").exists())

    def test_delete_session_returns_404_for_unknown_participant(self):
        response = self.client.delete("/api/participants/00002/")
        self.assertEqual(response.status_code, 404)

    def test_export_csv_attempts_returns_csv_content(self):
        self.client.post("/api/participants/create/", data={"participant_id": "44444", "group": "C"}, format="json")
        self.client.post(
            "/api/participants/44444/attempt/",
            data={"question_id": 1, "question_text": "Q", "topic": "liberalism", "correct": False, "attempt_count": 2},
            format="json",
        )
        response = self.client.get("/api/participants/export/?table=attempts")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode() if hasattr(response, "streaming_content") else response.content.decode()
        self.assertIn("44444", content)
        self.assertIn("False", content)

    def test_export_csv_consent_includes_post_session_questionnaire_column(self):
        self.client.post("/api/participants/create/", data={"participant_id": "44445", "group": "C"}, format="json")
        self.client.post(
            "/api/participants/44445/consent/",
            data={
                "info_sheet": True,
                "over_18": True,
                "stem_student": True,
                "consent_form": True,
                "post_session_questionnaire": True,
            },
            format="json",
        )

        response = self.client.get("/api/participants/export/?table=consent")
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content).decode() if hasattr(response, "streaming_content") else response.content.decode()
        self.assertIn("post_session_questionnaire", content)
        self.assertIn("44445", content)
