from django.contrib import admin
from tutor.models import InterpolatedAttempt, ParticipantSession


class InterpolatedAttemptInline(admin.TabularInline):
    model = InterpolatedAttempt
    extra = 0
    readonly_fields = ('answered_at',)


@admin.register(ParticipantSession)
class ParticipantSessionAdmin(admin.ModelAdmin):
    list_display = ('participant_id', 'group', 'tutor_topic', 'lib_pre_correct', 'lib_post_correct', 'rep_pre_correct', 'rep_post_correct', 'final_scaffold_score', 'completed', 'started_at')
    list_filter = ('group', 'completed')
    search_fields = ('participant_id',)
    readonly_fields = ('started_at',)
    inlines = [InterpolatedAttemptInline]


@admin.register(InterpolatedAttempt)
class InterpolatedAttemptAdmin(admin.ModelAdmin):
    list_display = ('session', 'question_id', 'topic', 'correct', 'attempt_count', 'used_hint', 'rewatched', 'answered_at')
    list_filter = ('topic', 'correct')
