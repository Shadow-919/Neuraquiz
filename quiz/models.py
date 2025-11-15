from django.db import models
from django.contrib.auth.models import User
import uuid
import random
import string


class UserProfile(models.Model):
    """Extended user profile with role information"""
    ROLE_CHOICES = [
        ('student', 'Student'),
        ('instructor', 'Instructor'),
        ('admin', 'Admin'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='student')
    bio = models.TextField(blank=True, null=True)
    profile_picture = models.ImageField(upload_to='profiles/', blank=True, null=True)
    quiz_access_code = models.CharField(max_length=6, unique=True, null=True, blank=True, help_text='6-digit access code for instructor quizzes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username} ({self.role})"
    
    def save(self, *args, **kwargs):
        # Auto-generate quiz access code for instructors if not already set
        if self.role == 'instructor' and not self.quiz_access_code:
            self.quiz_access_code = self.generate_unique_access_code()
        super().save(*args, **kwargs)
    
    @staticmethod
    def generate_unique_access_code():
        """Generate a unique 6-digit access code"""
        while True:
            code = ''.join(random.choices(string.digits, k=6))
            if not UserProfile.objects.filter(quiz_access_code=code).exists():
                return code


class Quiz(models.Model):
    """Quiz model containing questions and metadata"""
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    topic = models.CharField(max_length=100)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_quizzes')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='easy')
    time_limit = models.PositiveIntegerField(default=30, help_text="Time limit in minutes")
    is_published = models.BooleanField(default=False)
    is_ai_generated = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.title
    
    @property
    def total_questions(self):
        return self.questions.count()
    
    @property
    def total_time_seconds(self):
        return self.time_limit * 60


class Question(models.Model):
    """Question model for quiz questions"""
    QUESTION_TYPES = [
        ('mcq_single', 'Multiple Choice (Single)'),
        ('mcq_multiple', 'Multiple Choice (Multiple)'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    text = models.TextField()
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES)
    correct_answer = models.TextField(help_text="For MCQ: comma-separated indices, For True/False: true/false, For Short Answer: the answer")
    explanation = models.TextField(blank=True, null=True)
    image_url = models.URLField(blank=True, null=True)
    ai_generated = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['order', 'created_at']
    
    def __str__(self):
        return f"{self.quiz.title} - Question {self.order + 1}"


class Choice(models.Model):
    """Choice model for multiple choice questions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='choices')
    choice_text = models.TextField()
    is_correct = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.question.text[:50]}... - {self.choice_text[:30]}..."


class AIMetadata(models.Model):
    """Metadata for AI-generated content"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='ai_metadata')
    temperature_used = models.FloatField(default=0.7)
    repetition_penalty = models.FloatField(default=1.1)
    semantic_similarity_score = models.FloatField(blank=True, null=True)
    api_response_id = models.CharField(max_length=100, blank=True, null=True)
    generation_prompt = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"AI Metadata for {self.question.text[:30]}..."


class QuizAttempt(models.Model):
    """Model for tracking quiz attempts"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='quiz_attempts')
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='attempts')
    score = models.FloatField(default=0.0)
    total_questions = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)
    time_taken = models.PositiveIntegerField(blank=True, null=True, help_text="Time taken in seconds")
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.quiz.title} ({self.score}%)"
    
    @property
    def percentage_score(self):
        if self.total_questions > 0:
            return round((self.correct_answers / self.total_questions) * 100, 2)
        return 0.0


class UserAnswer(models.Model):
    """Model for storing user answers to questions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='answers')
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    answer_text = models.TextField(blank=True, null=True)
    selected_choices = models.ManyToManyField(Choice, blank=True)
    is_correct = models.BooleanField(default=False)
    points_earned = models.FloatField(default=0.0)
    answered_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['attempt', 'question']
    
    def __str__(self):
        return f"{self.attempt.user.username} - {self.question.text[:30]}..."


class AIInsight(models.Model):
    """Model for storing AI-generated insights about quiz performance"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attempt = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name='insights')
    insight_type = models.CharField(max_length=50)  # e.g., 'strength', 'weakness', 'recommendation'
    content = models.TextField()
    confidence_score = models.FloatField(default=0.0)
    generated_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"AI Insight for {self.attempt.user.username} - {self.insight_type}"