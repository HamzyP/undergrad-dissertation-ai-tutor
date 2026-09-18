from django.db import models


class ParticipantSession(models.Model):
    GROUP_CHOICES = [
        ('A', 'Group A'),
        ('B', 'Group B'),
        ('C', 'Group C'),
        ('D', 'Group D'),
    ]

    participant_id = models.CharField(max_length=5, unique=True, db_index=True)
    group = models.CharField(max_length=1, choices=GROUP_CHOICES)

    # Which topic had the AI tutor (derived from group)
    tutor_topic = models.CharField(max_length=32, blank=True)

    # Per-topic pre/post scores (always stored in fixed liberalism-first order regardless of group)
    lib_pre_correct = models.PositiveSmallIntegerField(null=True, blank=True)
    lib_pre_total = models.PositiveSmallIntegerField(null=True, blank=True)
    lib_post_correct = models.PositiveSmallIntegerField(null=True, blank=True)
    lib_post_total = models.PositiveSmallIntegerField(null=True, blank=True)

    rep_pre_correct = models.PositiveSmallIntegerField(null=True, blank=True)
    rep_pre_total = models.PositiveSmallIntegerField(null=True, blank=True)
    rep_post_correct = models.PositiveSmallIntegerField(null=True, blank=True)
    rep_post_total = models.PositiveSmallIntegerField(null=True, blank=True)

    final_scaffold_score = models.FloatField(null=True, blank=True)

    # Metadata
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f"Participant {self.participant_id} (Group {self.group})"


class InterpolatedAttempt(models.Model):
    session = models.ForeignKey(ParticipantSession, on_delete=models.CASCADE, related_name='interpolated_attempts')
    question_id = models.IntegerField()
    question_text = models.TextField()
    topic = models.CharField(max_length=32)

    attempt_count = models.PositiveSmallIntegerField(default=1)
    correct = models.BooleanField()
    used_hint = models.BooleanField(default=False)
    rewatched = models.BooleanField(default=False)

    # Scaffold score delta from this question
    scaffold_score_after = models.FloatField(null=True, blank=True)

    answered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['answered_at']

    def __str__(self):
        return f"Attempt by {self.session.participant_id} on Q{self.question_id}"


class ChatMessage(models.Model):
    SENDER_CHOICES = [('user', 'User'), ('tutor', 'Tutor')]

    session = models.ForeignKey(ParticipantSession, on_delete=models.CASCADE, related_name='chat_messages')
    sender = models.CharField(max_length=8, choices=SENDER_CHOICES)
    text = models.TextField()
    sent_at = models.DateTimeField()

    class Meta:
        ordering = ['sent_at']

    def __str__(self):
        return f"[{self.sender}] {self.session.participant_id} — {self.text[:40]}"


class ConsentRecord(models.Model):
    session = models.OneToOneField(ParticipantSession, on_delete=models.CASCADE, related_name='consent')
    info_sheet = models.BooleanField()
    over_18 = models.BooleanField()
    stem_student = models.BooleanField()
    consent_form = models.BooleanField()
    post_session_questionnaire = models.BooleanField()
    recorded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Consent for {self.session.participant_id} at {self.recorded_at}"


class Question(models.Model):
    TOPIC_CHOICES = [
        ("liberalism", "Liberalism"),
        ("rep-democracy", "Representative Democracy"),
    ]
    QUIZ_TYPE_CHOICES = [
        ("pre", "Pre/Post"),
        ("interpolated", "Interpolated"),
    ]

    topic = models.CharField(max_length=32, choices=TOPIC_CHOICES)
    quiz_type = models.CharField(max_length=16, choices=QUIZ_TYPE_CHOICES)
    order_index = models.PositiveIntegerField(default=0)

    question_text = models.TextField()
    option_a = models.CharField(max_length=512)
    option_b = models.CharField(max_length=512)
    option_c = models.CharField(max_length=512)
    option_d = models.CharField(max_length=512)
    # 0=A, 1=B, 2=C, 3=D
    correct_index = models.PositiveSmallIntegerField()

    # Interpolated-only fields
    timestamp = models.FloatField(null=True, blank=True)
    rewatch_start = models.FloatField(null=True, blank=True)

    transcript_excerpt = models.TextField(blank=True, default="")
    citations_json = models.TextField(default="[]")
    related_interpolated_id = models.BigIntegerField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["topic", "quiz_type", "order_index"]

    def __str__(self):
        return f"[{self.topic}/{self.quiz_type}] {self.question_text[:60]}"

    def options_list(self) -> list[str]:
        return [self.option_a, self.option_b, self.option_c, self.option_d]
