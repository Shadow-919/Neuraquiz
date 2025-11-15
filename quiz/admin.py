from django.contrib import admin
from .models import (
    UserProfile, Quiz, Question, Choice, AIMetadata, 
    QuizAttempt, UserAnswer, AIInsight
)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'role', 'created_at']
    list_filter = ['role', 'created_at']
    search_fields = ['user__username', 'user__email']


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    list_display = ['title', 'topic', 'created_by', 'difficulty', 'is_published', 'is_ai_generated', 'created_at']
    list_filter = ['difficulty', 'is_published', 'is_ai_generated', 'created_at']
    search_fields = ['title', 'topic', 'created_by__username']
    readonly_fields = ['id', 'created_at', 'updated_at']


class ChoiceInline(admin.TabularInline):
    model = Choice
    extra = 0


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['text', 'quiz', 'question_type', 'ai_generated', 'order']
    list_filter = ['question_type', 'ai_generated', 'created_at']
    search_fields = ['text', 'quiz__title']
    inlines = [ChoiceInline]
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(Choice)
class ChoiceAdmin(admin.ModelAdmin):
    list_display = ['choice_text', 'question', 'is_correct', 'order']
    list_filter = ['is_correct', 'created_at']
    search_fields = ['choice_text', 'question__text']


@admin.register(AIMetadata)
class AIMetadataAdmin(admin.ModelAdmin):
    list_display = ['question', 'temperature_used', 'semantic_similarity_score', 'created_at']
    list_filter = ['created_at']
    search_fields = ['question__text']


@admin.register(QuizAttempt)
class QuizAttemptAdmin(admin.ModelAdmin):
    list_display = ['user', 'quiz', 'score', 'correct_answers', 'total_questions', 'is_completed', 'started_at']
    list_filter = ['is_completed', 'started_at']
    search_fields = ['user__username', 'quiz__title']
    readonly_fields = ['id', 'started_at']


@admin.register(UserAnswer)
class UserAnswerAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'question', 'is_correct', 'points_earned', 'answered_at']
    list_filter = ['is_correct', 'answered_at']
    search_fields = ['attempt__user__username', 'question__text']


@admin.register(AIInsight)
class AIInsightAdmin(admin.ModelAdmin):
    list_display = ['attempt', 'insight_type', 'confidence_score', 'generated_at']
    list_filter = ['insight_type', 'generated_at']
    search_fields = ['attempt__user__username', 'content']
