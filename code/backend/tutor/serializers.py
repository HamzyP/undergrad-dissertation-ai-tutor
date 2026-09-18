import json

from rest_framework import serializers

from tutor.models import Question


class ChatRequestSerializer(serializers.Serializer):
    session_id = serializers.CharField()
    message = serializers.CharField()
    topic = serializers.CharField()
    timestamp = serializers.IntegerField()
    current_scaffold_level = serializers.CharField()
    model = serializers.CharField(required=False, allow_blank=False)
    interpolated_question = serializers.CharField(required=False, allow_blank=False)
    interpolated_answer_correct = serializers.BooleanField(required=False)
    explanation_outcome = serializers.ChoiceField(
        choices=["correct", "partial", "incorrect"],
        required=False,
    )
    explanation_attempt = serializers.IntegerField(required=False, min_value=1)
    explanation_gap = serializers.CharField(required=False, allow_blank=False)
    question_classification = serializers.CharField(required=False, allow_blank=False)
    support_strategy = serializers.CharField(required=False, allow_blank=False)
    hint_level = serializers.IntegerField(required=False, min_value=1, max_value=3)
    history = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        required=False,
        default=list,
    )


class QuestionSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()
    citations = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = [
            "id",
            "topic",
            "quiz_type",
            "order_index",
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "options",
            "correct_index",
            "timestamp",
            "rewatch_start",
            "transcript_excerpt",
            "citations",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at", "transcript_excerpt", "citations"]

    def get_options(self, obj):
        return obj.options_list()

    def get_citations(self, obj):
        try:
            parsed = json.loads(obj.citations_json or "[]")
        except json.JSONDecodeError:
            # Old or manually edited rows may contain malformed JSON; keep the API resilient.
            return []
        return parsed if isinstance(parsed, list) else []
