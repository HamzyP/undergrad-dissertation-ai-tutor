import csv

from django.http import HttpResponse
from django.utils import timezone as django_timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response

from tutor.models import ChatMessage, ConsentRecord, InterpolatedAttempt, ParticipantSession

TUTOR_TOPIC_FOR_GROUP = {
    'A': 'liberalism',
    'B': 'rep-democracy',
    'C': 'rep-democracy',
    'D': 'liberalism',
}


def _pct(correct, total):
    if correct is None or not total:
        return ''
    return round(correct / total * 100, 1)


def _gain(post_pct, pre_pct):
    if not isinstance(pre_pct, float) or not isinstance(post_pct, float):
        return ''
    return round(post_pct - pre_pct, 1)


@api_view(['POST'])
def session_create(request):
    data = request.data
    participant_id = data.get('participant_id', '')
    group = data.get('group', '')

    if not participant_id or len(participant_id) != 5 or not participant_id.isdigit():
        return Response({'error': 'participant_id must be a 5-digit string'}, status=400)
    if group not in ('A', 'B', 'C', 'D'):
        return Response({'error': 'group must be A, B, C, or D'}, status=400)

    session, created = ParticipantSession.objects.get_or_create(
        participant_id=participant_id,
        defaults={
            'group': group,
            'tutor_topic': TUTOR_TOPIC_FOR_GROUP[group],
        },
    )

    return Response({'id': session.id, 'created': created}, status=201 if created else 200)


@api_view(['POST'])
def attempt_record(request, participant_id):
    try:
        session = ParticipantSession.objects.get(participant_id=participant_id)
    except ParticipantSession.DoesNotExist:
        return Response({'error': 'Session not found'}, status=404)

    data = request.data
    required = ('question_id', 'question_text', 'topic', 'correct', 'attempt_count')
    missing = [f for f in required if f not in data]
    if missing:
        return Response({'error': f'Missing fields: {", ".join(missing)}'}, status=400)

    attempt = InterpolatedAttempt.objects.create(
        session=session,
        question_id=data['question_id'],
        question_text=data['question_text'],
        topic=data['topic'],
        correct=data['correct'],
        attempt_count=data['attempt_count'],
        used_hint=data.get('used_hint', False),
        rewatched=data.get('rewatched', False),
        scaffold_score_after=data.get('scaffold_score_after'),
    )

    return Response({'attempt_id': attempt.id}, status=201)


@api_view(['POST'])
def session_finalise(request, participant_id):
    try:
        session = ParticipantSession.objects.get(participant_id=participant_id)
    except ParticipantSession.DoesNotExist:
        return Response({'error': 'Session not found'}, status=404)

    data = request.data

    # Per-topic scores — frontend sends them keyed by topic name
    for field in (
        'lib_pre_correct', 'lib_pre_total',
        'lib_post_correct', 'lib_post_total',
        'rep_pre_correct', 'rep_pre_total',
        'rep_post_correct', 'rep_post_total',
        'final_scaffold_score',
    ):
        if field in data:
            setattr(session, field, data[field])

    session.completed = True
    session.completed_at = django_timezone.now()
    session.save()

    # Persist chat history if provided
    messages = data.get('chat_messages', [])
    if messages:
        ChatMessage.objects.filter(session=session).delete()
        ChatMessage.objects.bulk_create([
            ChatMessage(
                session=session,
                sender=m['sender'],
                text=m['text'],
                sent_at=m['sent_at'],
            )
            for m in messages
            if m.get('sender') in ('user', 'tutor') and m.get('text') and m.get('sent_at')
        ])

    return Response({'ok': True})


@api_view(['POST'])
def consent_record(request, participant_id):
    try:
        session = ParticipantSession.objects.get(participant_id=participant_id)
    except ParticipantSession.DoesNotExist:
        return Response({'error': 'Session not found'}, status=404)

    data = request.data
    required = ('info_sheet', 'over_18', 'stem_student', 'consent_form', 'post_session_questionnaire')
    missing = [f for f in required if f not in data]
    if missing:
        return Response({'error': f'Missing fields: {", ".join(missing)}'}, status=400)

    if not all(data[f] for f in required):
        return Response({'error': 'All consent fields must be true'}, status=400)

    record, _ = ConsentRecord.objects.update_or_create(
        session=session,
        defaults={
            'info_sheet': data['info_sheet'],
            'over_18': data['over_18'],
            'stem_student': data['stem_student'],
            'consent_form': data['consent_form'],
            'post_session_questionnaire': data['post_session_questionnaire'],
        },
    )
    return Response({'recorded_at': record.recorded_at}, status=201)


@api_view(['DELETE'])
def session_delete(request, participant_id):
    try:
        session = ParticipantSession.objects.get(participant_id=participant_id)
    except ParticipantSession.DoesNotExist:
        return Response({'error': 'Session not found'}, status=404)
    session.delete()
    return Response(status=204)


@api_view(['GET'])
def sessions_list(request):
    sessions = ParticipantSession.objects.prefetch_related('interpolated_attempts', 'chat_messages').all()
    data = []
    for s in sessions:
        attempts = list(s.interpolated_attempts.values(
            'question_id', 'question_text', 'topic', 'correct',
            'attempt_count', 'used_hint', 'rewatched', 'scaffold_score_after', 'answered_at'
        ))
        chat = list(s.chat_messages.values('sender', 'text', 'sent_at'))
        data.append({
            'participant_id': s.participant_id,
            'group': s.group,
            'tutor_topic': s.tutor_topic,
            'lib_pre_correct': s.lib_pre_correct,
            'lib_pre_total': s.lib_pre_total,
            'lib_post_correct': s.lib_post_correct,
            'lib_post_total': s.lib_post_total,
            'rep_pre_correct': s.rep_pre_correct,
            'rep_pre_total': s.rep_pre_total,
            'rep_post_correct': s.rep_post_correct,
            'rep_post_total': s.rep_post_total,
            'final_scaffold_score': s.final_scaffold_score,
            'completed': s.completed,
            'started_at': s.started_at,
            'completed_at': s.completed_at,
            'interpolated_attempts': attempts,
            'chat_messages': chat,
        })
    return Response(data)


@api_view(['GET'])
def export_csv(request):
    which = request.GET.get('table', 'sessions')
    response = HttpResponse(content_type='text/csv')

    if which == 'attempts':
        response['Content-Disposition'] = 'attachment; filename="interpolated_attempts.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'participant_id', 'group', 'tutor_topic',
            'question_id', 'question_text', 'topic',
            'answered_correctly', 'attempt_count', 'used_hint', 'rewatched',
            'scaffold_score_after', 'answered_at',
        ])
        for attempt in InterpolatedAttempt.objects.select_related('session').order_by('session__participant_id', 'answered_at'):
            s = attempt.session
            writer.writerow([
                s.participant_id, s.group, s.tutor_topic,
                attempt.question_id, attempt.question_text, attempt.topic,
                attempt.correct, attempt.attempt_count, attempt.used_hint, attempt.rewatched,
                attempt.scaffold_score_after,
                attempt.answered_at.strftime('%Y-%m-%d %H:%M:%S') if attempt.answered_at else '',
            ])

    elif which == 'chat':
        response['Content-Disposition'] = 'attachment; filename="chat_history.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'participant_id', 'group', 'tutor_topic',
            'turn', 'sender', 'offset_seconds', 'sent_at', 'message',
        ])
        current_pid = None
        turn = 0
        session_start = None
        for msg in ChatMessage.objects.select_related('session').order_by('session__participant_id', 'sent_at'):
            s = msg.session
            if s.participant_id != current_pid:
                current_pid = s.participant_id
                turn = 0
                session_start = msg.sent_at
            turn += 1
            if session_start and msg.sent_at:
                offset = round((msg.sent_at - session_start).total_seconds())
            else:
                offset = ''
            writer.writerow([
                s.participant_id, s.group, s.tutor_topic,
                turn, msg.sender, offset,
                msg.sent_at.strftime('%Y-%m-%d %H:%M:%S') if msg.sent_at else '',
                msg.text,
            ])

    elif which == 'consent':
        response['Content-Disposition'] = 'attachment; filename="consent_records.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'participant_id', 'group',
            'info_sheet', 'over_18', 'stem_student', 'consent_form', 'post_session_questionnaire',
            'recorded_at',
        ])
        for r in ConsentRecord.objects.select_related('session').order_by('session__participant_id'):
            s = r.session
            writer.writerow([
                s.participant_id, s.group,
                r.info_sheet, r.over_18, r.stem_student, r.consent_form, r.post_session_questionnaire,
                r.recorded_at.strftime('%Y-%m-%d %H:%M:%S') if r.recorded_at else '',
            ])

    else:
        # sessions (default) — fixed column order: liberalism first, rep-democracy second
        response['Content-Disposition'] = 'attachment; filename="participant_sessions.csv"'
        writer = csv.writer(response)
        writer.writerow([
            'participant_id', 'group', 'ai_tutor_topic',
            # Liberalism (fixed first regardless of group)
            'lib_pre_questions_correct', 'lib_pre_questions_total', 'lib_pre_pct',
            'lib_post_questions_correct', 'lib_post_questions_total', 'lib_post_pct',
            'lib_gain_pct',
            # Rep-democracy (fixed second)
            'rep_pre_questions_correct', 'rep_pre_questions_total', 'rep_pre_pct',
            'rep_post_questions_correct', 'rep_post_questions_total', 'rep_post_pct',
            'rep_gain_pct',
            # Overall
            'overall_pre_pct', 'overall_post_pct', 'overall_gain_pct',
            'final_scaffold_score',
            'completed', 'started_at', 'completed_at', 'duration_minutes',
        ])
        for s in ParticipantSession.objects.all():
            lib_pre = _pct(s.lib_pre_correct, s.lib_pre_total)
            lib_post = _pct(s.lib_post_correct, s.lib_post_total)
            rep_pre = _pct(s.rep_pre_correct, s.rep_pre_total)
            rep_post = _pct(s.rep_post_correct, s.rep_post_total)

            # Overall: sum both topics
            overall_pre_c = (s.lib_pre_correct or 0) + (s.rep_pre_correct or 0)
            overall_pre_t = (s.lib_pre_total or 0) + (s.rep_pre_total or 0)
            overall_post_c = (s.lib_post_correct or 0) + (s.rep_post_correct or 0)
            overall_post_t = (s.lib_post_total or 0) + (s.rep_post_total or 0)
            overall_pre = _pct(overall_pre_c, overall_pre_t)
            overall_post = _pct(overall_post_c, overall_post_t)

            if s.started_at and s.completed_at:
                duration = round((s.completed_at - s.started_at).total_seconds() / 60, 1)
            else:
                duration = ''

            writer.writerow([
                s.participant_id, s.group, s.tutor_topic,
                s.lib_pre_correct, s.lib_pre_total, lib_pre,
                s.lib_post_correct, s.lib_post_total, lib_post,
                _gain(lib_post, lib_pre),
                s.rep_pre_correct, s.rep_pre_total, rep_pre,
                s.rep_post_correct, s.rep_post_total, rep_post,
                _gain(rep_post, rep_pre),
                overall_pre, overall_post, _gain(overall_post, overall_pre),
                s.final_scaffold_score,
                s.completed,
                s.started_at.strftime('%Y-%m-%d %H:%M:%S') if s.started_at else '',
                s.completed_at.strftime('%Y-%m-%d %H:%M:%S') if s.completed_at else '',
                duration,
            ])

    return response
