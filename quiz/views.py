from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Q, Avg, Count
from django.core.paginator import Paginator
import json
import uuid
from datetime import datetime, timedelta

from .models import (
    UserProfile, Quiz, Question, Choice, AIMetadata, 
    QuizAttempt, UserAnswer, AIInsight
)
from .services import gemini_service, RateLimitError
from django.core.cache import cache
import logging

logger = logging.getLogger(__name__)


def home(request):
    """Landing page"""
    if request.user.is_authenticated:
        return redirect('quiz:dashboard')
    context = {}
    return render(request, 'quiz/home.html', context)


def login_view(request):
    """User login"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('quiz:dashboard')
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'quiz/login.html')


def register_view(request):
    """User registration"""
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        # Only allow 'student' or 'instructor' roles via the website
        role = request.POST.get('role', 'student')
        if role not in ['student', 'instructor']:
            role = 'student'

        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists.')
            return render(request, 'quiz/register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists.')
            return render(request, 'quiz/register.html')

        # Create user
        user = User.objects.create_user(username=username, email=email, password=password)

        # Create user profile with validated role (access code will be auto-generated for instructors)
        UserProfile.objects.create(user=user, role=role)

        messages.success(request, 'Account created successfully! Please log in.')
        return redirect('quiz:login')

    return render(request, 'quiz/register.html')


def logout_view(request):
    """User logout"""
    logout(request)
    return redirect('quiz:home')


@login_required
def dashboard(request):
    """User dashboard"""
    user_profile = UserProfile.objects.get(user=request.user)
    
    if user_profile.role == 'instructor':
        # Instructor dashboard
        quizzes = Quiz.objects.filter(created_by=request.user).order_by('-created_at')
        
        # Filter recent attempts to only show students who used this instructor's access code
        # Get all students who have the instructor's access code in their session or have taken quizzes
        recent_attempts = QuizAttempt.objects.filter(
            quiz__created_by=request.user
        ).select_related('user', 'quiz').order_by('-started_at')[:10]

        # Stats
        total_quizzes = quizzes.count()
        published_quizzes = quizzes.filter(is_published=True).count()
        ai_generated_quizzes = quizzes.filter(is_ai_generated=True).count()

        context = {
            'user_profile': user_profile,
            'quizzes': quizzes,
            'recent_attempts': recent_attempts,
            'total_quizzes': total_quizzes,
            'published_quizzes': published_quizzes,
            'ai_generated_quizzes': ai_generated_quizzes,
        }
        return render(request, 'quiz/instructor_dashboard.html', context)
    
    else:
        # Student dashboard
        # Get the access code from session if exists
        access_code = request.session.get('instructor_access_code', None)
        
        if access_code:
            # Find the instructor with this access code
            try:
                instructor_profile = UserProfile.objects.get(quiz_access_code=access_code, role='instructor')
                # Filter quizzes created by this instructor only
                available_quizzes = Quiz.objects.filter(
                    is_published=True,
                    created_by=instructor_profile.user
                ).order_by('-created_at')
            except UserProfile.DoesNotExist:
                available_quizzes = Quiz.objects.none()
                messages.warning(request, 'Invalid access code. Please enter a valid instructor access code.')
        else:
            # No access code entered yet
            available_quizzes = Quiz.objects.none()
        
        my_attempts = QuizAttempt.objects.filter(user=request.user).order_by('-started_at')
        completed_count = my_attempts.filter(is_completed=True).count()
        
        context = {
            'user_profile': user_profile,
            'available_quizzes': available_quizzes,
            'my_attempts': my_attempts,
            'completed_count': completed_count,
            'access_code': access_code,
        }
        return render(request, 'quiz/student_dashboard.html', context)


@login_required
def verify_access_code(request):
    """Verify and store instructor access code in session"""
    if request.method == 'POST':
        access_code = request.POST.get('access_code', '').strip()
        
        if not access_code:
            messages.error(request, 'Please enter an access code.')
            return redirect('quiz:dashboard')
        
        # Verify the access code exists and belongs to an instructor
        try:
            instructor_profile = UserProfile.objects.get(quiz_access_code=access_code, role='instructor')
            # Store the access code in session
            request.session['instructor_access_code'] = access_code
            messages.success(request, f'Access code verified! You can now view quizzes from {instructor_profile.user.username}.')
        except UserProfile.DoesNotExist:
            messages.error(request, 'Invalid access code. Please check and try again.')
        
        return redirect('quiz:dashboard')
    
    return redirect('quiz:dashboard')


@login_required
def clear_access_code(request):
    """Clear the stored access code from session"""
    if 'instructor_access_code' in request.session:
        del request.session['instructor_access_code']
        messages.success(request, 'Access code cleared.')
    return redirect('quiz:dashboard')


@login_required
def create_quiz(request):
    """Create a new quiz (instructor only)"""
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin']:
        messages.error(request, 'You do not have permission to create quizzes.')
        return redirect('quiz:dashboard')
    
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description')
        topic = request.POST.get('topic')
        difficulty = request.POST.get('difficulty')
        time_limit = int(request.POST.get('time_limit', 30))

        quiz = Quiz.objects.create(
            title=title,
            description=description,
            topic=topic,
            difficulty=difficulty,
            time_limit=time_limit,
            created_by=request.user
        )

        messages.success(request, f'Quiz "{title}" created successfully!')
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)

    return render(request, 'quiz/create_quiz.html')


@login_required
def edit_quiz(request, quiz_id):
    """Edit quiz questions"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        messages.error(request, 'You do not have permission to edit this quiz.')
        return redirect('quiz:dashboard')
    
    questions = quiz.questions.all().order_by('order')

    # counts for UI
    ai_generated_count = questions.filter(ai_generated=True).count()

    context = {
        'quiz': quiz,
        'questions': questions,
        'ai_generated_count': ai_generated_count,
        # expose whether the Gemini service is available so templates can disable UI
        'ai_enabled': gemini_service.is_configured,
    }
    return render(request, 'quiz/edit_quiz.html', context)


@login_required
def quiz_stats(request, quiz_id):
    """Return quiz stats as JSON for dynamic updates"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    questions = quiz.questions.all()
    
    return JsonResponse({
        'questions_count': questions.count(),
        'ai_generated_count': questions.filter(ai_generated=True).count(),
        'time_limit': quiz.time_limit,
        'is_published': quiz.is_published,
    })


@login_required
def cancel_ai_generation(request, quiz_id):
    """Cancel an ongoing AI generation for a quiz"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check permissions
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)
    
    if request.method == 'POST':
        # Set cancellation flag
        cancel_key = f'cancel_ai_{quiz.id}'
        cache.set(cancel_key, True, timeout=60)
        
        return JsonResponse({'success': True, 'message': 'Cancellation requested'})
    
    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def generate_ai_questions(request, quiz_id):
    """Generate AI questions for a quiz, preventing duplicate generation."""
    quiz = get_object_or_404(Quiz, id=quiz_id)

    # Check permissions
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    if not gemini_service.is_configured:
        return JsonResponse({'error': 'AI service not configured.'}, status=503)

    # Parse incoming data safely
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    topic = data.get('topic', quiz.topic)
    num_questions = int(data.get('num_questions', 10))
    difficulty = data.get('difficulty', quiz.difficulty)
    additional_instructions = data.get('additional_instructions', '')
    use_demo = data.get('use_demo', False)

    # Stronger lock to prevent duplicate triggers (Render fix)
    lock_key = f'generating_ai_{quiz.id}'
    if not cache.add(lock_key, True, timeout=300):  # 5 min lock
        logger.warning(f"Duplicate AI generation ignored for quiz {quiz.id}")
        return JsonResponse({'pending': True, 'message': 'AI generation already running. Please wait.'}, status=202)

    cancel_key = f'cancel_ai_{quiz.id}'
    generated_questions = []

    try:
        # Early cancel check
        if cache.get(cancel_key):
            cache.delete(cancel_key)
            cache.delete(lock_key)
            return JsonResponse({'error': 'Generation was cancelled', 'cancelled': True}, status=400)

        # Generate questions via Gemini
        if use_demo:
            generated_questions = gemini_service.generate_questions_demo(topic=topic, num_questions=num_questions, difficulty=difficulty)
        else:
            generated_questions = gemini_service.generate_questions(
                topic=topic,
                num_questions=num_questions,
                difficulty=difficulty,
                additional_instructions=additional_instructions,
                debug_save=data.get('debug_save', False)
            )

        if not generated_questions:
            return JsonResponse({'error': 'AI returned no questions.'}, status=503)

        # Prevent over-generation (some Gemini outputs more)
        generated_questions = generated_questions[:num_questions]

        # Check again to ensure no new AI questions were saved by another concurrent request
        existing_ai_count = quiz.questions.filter(ai_generated=True).count()
        if existing_ai_count >= num_questions:
            logger.info(f"Skipped duplicate generation for quiz {quiz.id} (already generated).")
            return JsonResponse({'duplicate': True, 'message': 'AI questions already generated.'}, status=200)

        # Save questions
        saved_questions = []
        base_order = quiz.questions.count()
        seen_texts = set()

        for i, q_data in enumerate(generated_questions):
            if cache.get(cancel_key):
                break

            qtext = (q_data.get('question_text') or '').strip().lower()
            if not qtext or qtext in seen_texts:
                continue
            seen_texts.add(qtext)

            question = Question.objects.create(
                quiz=quiz,
                text=q_data['question_text'],
                question_type=q_data['question_type'],
                correct_answer=q_data['correct_answer'],
                explanation=q_data.get('explanation', ''),
                difficulty_score=int(float(q_data.get('difficulty_score', 3.0))) if q_data.get('difficulty_score') else 3,
                order=base_order + len(saved_questions),
                ai_generated=True
            )

            if q_data.get('question_type') in ['mcq_single', 'mcq_multiple']:
                choices = q_data.get('choices', []) or []
                correct_indices = []
                try:
                    correct_indices = [int(x) for x in str(q_data.get('correct_answer', '')).split(',') if x]
                except Exception:
                    correct_indices = []

                for j, ctext in enumerate(choices):
                    Choice.objects.create(
                        question=question,
                        choice_text=ctext,
                        is_correct=(j in correct_indices),
                        order=j
                    )

            AIMetadata.objects.create(
                question=question,
                temperature_used=0.7,
                repetition_penalty=1.1,
                generation_prompt=f"Generate questions about {topic}"
            )

            saved_questions.append({'id': str(question.id), 'text': question.text})

            if len(saved_questions) >= num_questions:
                break

        quiz.is_ai_generated = True
        quiz.save()

        return JsonResponse({
            'success': True,
            'questions': saved_questions,
            'message': f'Generated {len(saved_questions)} questions successfully!'
        })

    except RateLimitError as rl:
        retry = getattr(rl, "retry_after", None)
        return JsonResponse({'error': 'AI rate limit exceeded', 'retry_seconds': retry}, status=429)

    except Exception as e:
        logger.exception(f"AI generation failed for quiz {quiz.id}: {e}")
        return JsonResponse({'error': 'AI generation failed'}, status=500)

    finally:
        cache.delete(lock_key)


@login_required
def delete_question(request, question_id):
    """Delete a question from a quiz"""
    question = get_object_or_404(Question, id=question_id)
    quiz = question.quiz
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        messages.error(request, 'You do not have permission to delete this question.')
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)

    if request.method == 'POST':
        question.delete()
        messages.success(request, 'Question deleted.')
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)

    return redirect('quiz:edit_quiz', quiz_id=quiz.id)


@login_required
def publish_quiz(request, quiz_id):
    """Publish a quiz (make visible to students)"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        messages.error(request, 'You do not have permission to publish this quiz.')
        return redirect('quiz:dashboard')

    if request.method == 'POST':
        quiz.is_published = True
        quiz.save()
        messages.success(request, f'Quiz "{quiz.title}" published.')
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)

    return redirect('quiz:edit_quiz', quiz_id=quiz.id)


@login_required
def delete_quiz(request, quiz_id):
    """Delete a quiz (instructor only)"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        messages.error(request, 'You do not have permission to delete this quiz.')
        return redirect('quiz:dashboard')

    if request.method == 'POST':
        quiz.delete()
        messages.success(request, 'Quiz deleted.')
        return redirect('quiz:dashboard')

    return redirect('quiz:dashboard')


@login_required
def edit_question(request, question_id):
    """Edit an existing question"""
    question = get_object_or_404(Question, id=question_id)
    quiz = question.quiz
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        messages.error(request, 'You do not have permission to edit this question.')
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)

    if request.method == 'POST':
        question.text = request.POST.get('text', '').strip()
        question.question_type = request.POST.get('question_type')
        # Read correct answer selection: prefer the visual selectors (radio/checkbox)
        if question.question_type == 'mcq_single':
            question.correct_answer = request.POST.get('correct_choice', '')
        elif question.question_type == 'mcq_multiple':
            multi = request.POST.getlist('correct_choices') or request.POST.getlist('correct_choice')
            question.correct_answer = ','.join([str(x) for x in multi])
        else:
            question.correct_answer = request.POST.get('correct_answer', '')
        question.explanation = request.POST.get('explanation', '')
        # Store difficulty as integer value (1-5)
        try:
            question.difficulty_score = int(float(request.POST.get('difficulty_score', 3) or 3))
        except Exception:
            question.difficulty_score = 3
        question.save()

        # Update choices (simple approach: delete existing and recreate)
        if question.question_type in ['mcq_single', 'mcq_multiple']:
            question.choices.all().delete()
            for i in range(4):
                ctext = request.POST.get(f'choice_{i}', '').strip()
                if ctext:
                    Choice.objects.create(question=question, choice_text=ctext, is_correct=False, order=i)

            # Mark correct choices based on the visual input fields
            choices_qs = question.choices.all()
            if question.question_type == 'mcq_single':
                correct_idx = request.POST.get('correct_choice')
                try:
                    cidx = int(correct_idx)
                    if 0 <= cidx < choices_qs.count():
                        choice_obj = choices_qs[cidx]
                        choice_obj.is_correct = True
                        choice_obj.save()
                except Exception:
                    pass
            elif question.question_type == 'mcq_multiple':
                selected = request.POST.getlist('correct_choices') or request.POST.getlist('correct_choice')
                for s in selected:
                    try:
                        cidx = int(s)
                        if 0 <= cidx < choices_qs.count():
                            choice_obj = choices_qs[cidx]
                            choice_obj.is_correct = True
                            choice_obj.save()
                    except Exception:
                        continue
        else:
            # Non-MCQ types: remove any choices for cleanliness
            question.choices.all().delete()

        messages.success(request, 'Question updated successfully.')
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)

    # Prefill form
    choices = list(question.choices.all())
    # Compute which choice indices are marked correct (if stored as comma-separated indices)
    correct_indices = []
    if question.correct_answer:
        try:
            correct_indices = [int(x.strip()) for x in question.correct_answer.split(',') if x.strip()!='']
        except Exception:
            correct_indices = []

    context = {
        'quiz': quiz,
        'question': question,
        'choices': choices,
        'correct_indices': correct_indices,
    }
    return render(request, 'quiz/edit_question.html', context)


@login_required
def add_question(request, quiz_id):
    """Add a new question to a quiz (instructor only)"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        messages.error(request, 'You do not have permission to add questions to this quiz.')
        return redirect('quiz:dashboard')

    if request.method == 'POST':
        text = request.POST.get('text', '').strip()
        question_type = request.POST.get('question_type')
        # Accept visual selection for correct choice
        if question_type == 'mcq_single':
            correct_answer = request.POST.get('correct_choice', '')
        elif question_type == 'mcq_multiple':
            correct_answer = ','.join(request.POST.getlist('correct_choices') or request.POST.getlist('correct_choice'))
        else:
            correct_answer = request.POST.get('correct_answer', '')
        explanation = request.POST.get('explanation', '')
        try:
            difficulty_score = int(float(request.POST.get('difficulty_score', 3) or 3))
        except Exception:
            difficulty_score = 3

        question = Question.objects.create(
            quiz=quiz,
            text=text,
            question_type=question_type,
            correct_answer=correct_answer,
            explanation=explanation,
            difficulty_score=difficulty_score,
            order=quiz.questions.count(),
            ai_generated=False
        )

        # If MCQ, read choices
        if question_type in ['mcq_single', 'mcq_multiple']:
            for i in range(4):
                ctext = request.POST.get(f'choice_{i}', '').strip()
                if ctext:
                    Choice.objects.create(question=question, choice_text=ctext, is_correct=False, order=i)

            # Mark correct choices based on the visual input
            choices_qs = question.choices.all()
            if question_type == 'mcq_single':
                try:
                    cidx = int(request.POST.get('correct_choice'))
                    if 0 <= cidx < choices_qs.count():
                        choice_obj = choices_qs[cidx]
                        choice_obj.is_correct = True
                        choice_obj.save()
                except Exception:
                    pass
            elif question_type == 'mcq_multiple':
                selected = request.POST.getlist('correct_choices') or request.POST.getlist('correct_choice')
                for s in selected:
                    try:
                        cidx = int(s)
                        if 0 <= cidx < choices_qs.count():
                            choice_obj = choices_qs[cidx]
                            choice_obj.is_correct = True
                            choice_obj.save()
                    except Exception:
                        continue

        messages.success(request, 'Question added successfully.')
        return redirect('quiz:edit_quiz', quiz_id=quiz.id)

    return render(request, 'quiz/add_question.html', {'quiz': quiz})


@login_required
def take_quiz(request, quiz_id):
    """Take a quiz (student interface)"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    if not quiz.is_published:
        messages.error(request, 'This quiz is not available.')
        return redirect('quiz:dashboard')
    
    # Check if user already has an active attempt
    active_attempt = QuizAttempt.objects.filter(
        user=request.user,
        quiz=quiz,
        is_completed=False
    ).first()
    
    if not active_attempt:
        # Create new attempt
        active_attempt = QuizAttempt.objects.create(
            user=request.user,
            quiz=quiz,
            total_questions=quiz.questions.count()
        )
    
    questions = quiz.questions.all().order_by('order')
    
    context = {
        'quiz': quiz,
        'attempt': active_attempt,
        'questions': questions,
    }
    return render(request, 'quiz/take_quiz.html', context)


@login_required
def submit_answer(request, attempt_id):
    """Submit an answer for a question"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    
    if attempt.is_completed:
        return JsonResponse({'error': 'Quiz already completed'}, status=400)
    
    if request.method == 'POST':
        data = json.loads(request.body)
        question_id = data.get('question_id')
        answer_text = data.get('answer_text', '')
        selected_choice_ids = data.get('selected_choices', [])

        question = get_object_or_404(Question, id=question_id, quiz=attempt.quiz)

        # Get or create user answer
        user_answer, created = UserAnswer.objects.get_or_create(
            attempt=attempt,
            question=question
        )

        # Update answer
        user_answer.answer_text = answer_text
        user_answer.save()

        # Update selected choices
        if selected_choice_ids:
            choices = Choice.objects.filter(id__in=selected_choice_ids, question=question)
            user_answer.selected_choices.set(choices)

        # Check if answer is correct
        is_correct = _check_answer(question, answer_text, selected_choice_ids)
        user_answer.is_correct = is_correct
        user_answer.points_earned = 1.0 if is_correct else 0.0
        user_answer.save()

        return JsonResponse({
            'success': True,
            'is_correct': is_correct,
            'explanation': question.explanation
        })

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def finish_quiz(request, attempt_id):
    """Finish a quiz attempt"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    
    if attempt.is_completed:
        return redirect('quiz:quiz_results', attempt_id=attempt_id)

    if request.method == 'POST':
        # Calculate final score
        correct_answers = attempt.answers.filter(is_correct=True).count()
        total_questions = attempt.total_questions

        attempt.correct_answers = correct_answers
        attempt.score = (correct_answers / total_questions * 100) if total_questions > 0 else 0
        attempt.finished_at = timezone.now()
        attempt.is_completed = True

        # Calculate time taken
        if attempt.started_at:
            time_taken = (attempt.finished_at - attempt.started_at).total_seconds()
            attempt.time_taken = int(time_taken)

        attempt.save()

        # Generate AI insights
        _generate_quiz_insights(attempt)

        return redirect('quiz:quiz_results', attempt_id=attempt_id)

    return JsonResponse({'error': 'Invalid request method'}, status=405)


@login_required
def quiz_results(request, attempt_id):
    """Display quiz results"""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    
    if not attempt.is_completed:
        messages.error(request, 'Quiz not completed yet.')
        return redirect('quiz:take_quiz', quiz_id=attempt.quiz.id)
    
    # Get insights
    insights = attempt.insights.all()
    # Compute derived metrics for template clarity
    wrong_answers = (attempt.total_questions or 0) - (attempt.correct_answers or 0)

    # Format time taken as mm:ss string
    formatted_time = None
    if attempt.time_taken is not None:
        mins = attempt.time_taken // 60
        secs = attempt.time_taken % 60
        formatted_time = f"{mins:02d}:{secs:02d}"

    # Average time per question in seconds (float) if available
    avg_time_per_question = None
    if attempt.time_taken and attempt.total_questions:
        try:
            avg_time_per_question = round(float(attempt.time_taken) / float(attempt.total_questions), 1)
        except Exception:
            avg_time_per_question = None

    # Build detailed per-question results so student can review answers
    detailed_results = []
    for idx, question in enumerate(attempt.quiz.questions.all().order_by('order')):
        ua = attempt.answers.filter(question=question).first()
        if ua:
            if question.question_type in ['mcq_single', 'mcq_multiple']:
                selected = []
                for choice in ua.selected_choices.all():
                    selected.append(choice.choice_text)
                student_answer = ', '.join(selected) if selected else ''
            else:
                student_answer = ua.answer_text or ''
            status = 'correct' if ua.is_correct else 'wrong'
        else:
            student_answer = ''
            status = 'unattempted'

        # Compute canonical correct answer display
        correct_display = ''
        if question.question_type in ['mcq_single', 'mcq_multiple']:
            correct_choices = question.choices.filter(is_correct=True).values_list('choice_text', flat=True)
            correct_display = ', '.join(list(correct_choices))
        else:
            correct_display = question.correct_answer or ''

        detailed_results.append({
            'number': idx + 1,
            'question_id': question.id,
            'text': question.text,
            'type': question.question_type,
            'student_answer': student_answer,
            'correct_answer': correct_display,
            'status': status,
            'explanation': question.explanation,
        })

    context = {
        'attempt': attempt,
        'insights': insights,
        'wrong_answers': wrong_answers,
        'formatted_time': formatted_time,
        'avg_time_per_question': avg_time_per_question,
        'detailed_results': detailed_results,
    }
    return render(request, 'quiz/quiz_results.html', context)


@login_required
def delete_attempts(request, quiz_id):
    """Allow a user to delete their attempts for a particular quiz."""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    if request.method == 'POST':
        # Delete only the current user's attempts for this quiz
        QuizAttempt.objects.filter(user=request.user, quiz=quiz).delete()
        messages.success(request, 'Your quiz attempt history has been deleted.')
        return redirect('quiz:dashboard')

    messages.error(request, 'Invalid request method.')
    return redirect('quiz:dashboard')


@login_required
def delete_attempt(request, attempt_id):
    """Delete a single quiz attempt (the row) for the current user."""
    attempt = get_object_or_404(QuizAttempt, id=attempt_id, user=request.user)
    if request.method == 'POST':
        attempt.delete()
        messages.success(request, 'The selected attempt has been deleted.')
        return redirect('quiz:dashboard')

    messages.error(request, 'Invalid request method.')
    return redirect('quiz:dashboard')


@login_required
def generate_ai_status(request, quiz_id):
    """Return whether AI generation is currently in progress for a quiz and ai_generated count."""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    user_profile = UserProfile.objects.get(user=request.user)
    if user_profile.role not in ['instructor', 'admin'] and quiz.created_by != request.user:
        return JsonResponse({'error': 'Permission denied'}, status=403)

    lock_key = f'generating_ai_{quiz.id}'
    in_progress = cache.get(lock_key) is not None
    ai_generated_count = quiz.questions.filter(ai_generated=True).count()

    return JsonResponse({'in_progress': bool(in_progress), 'ai_generated_count': ai_generated_count})


def _check_answer(question, answer_text, selected_choice_ids):
    """Check if an answer is correct"""
    if question.question_type == 'true_false':
        return answer_text.lower() == question.correct_answer.lower()
    
    elif question.question_type == 'short_answer':
        return answer_text.lower().strip() == question.correct_answer.lower().strip()
    
    elif question.question_type in ['mcq_single', 'mcq_multiple']:
        correct_indices = [int(x) for x in question.correct_answer.split(',')]
        correct_choices = Choice.objects.filter(
            question=question,
            is_correct=True
        ).values_list('id', flat=True)
        
        selected_choices = Choice.objects.filter(id__in=selected_choice_ids)
        selected_correct = selected_choices.filter(is_correct=True).count()
        selected_incorrect = selected_choices.filter(is_correct=False).count()
        
        if question.question_type == 'mcq_single':
            return selected_correct == 1 and selected_incorrect == 0
        else:  # mcq_multiple
            return selected_correct == len(correct_indices) and selected_incorrect == 0
    
    return False


def _generate_quiz_insights(attempt):
    """Generate AI insights for quiz performance"""
    if not gemini_service.is_configured:
        return
    
    # Prepare attempt data
    attempt_data = {
        'quiz_title': attempt.quiz.title,
        'score': attempt.score,
        'time_taken': attempt.time_taken,
        'correct_answers': attempt.correct_answers,
        'total_questions': attempt.total_questions,
    }
    
    # Get difficulty breakdown
    difficulty_breakdown = {}
    for answer in attempt.answers.all():
        difficulty = answer.question.difficulty_score
        if difficulty not in difficulty_breakdown:
            difficulty_breakdown[difficulty] = {'correct': 0, 'total': 0}
        difficulty_breakdown[difficulty]['total'] += 1
        if answer.is_correct:
            difficulty_breakdown[difficulty]['correct'] += 1
    
    attempt_data['difficulty_breakdown'] = difficulty_breakdown
    
    # Generate insights
    insights_data = gemini_service.generate_quiz_insights(attempt_data)
    
    # Save insights
    for insight_data in insights_data:
        AIInsight.objects.create(
            attempt=attempt,
            insight_type=insight_data.get('insight_type', 'general'),
            content=insight_data.get('content', ''),
            confidence_score=insight_data.get('confidence_score', 0.5)
        )