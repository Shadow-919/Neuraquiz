from django.core.management.base import BaseCommand, CommandError
from quiz.services import gemini_service
from quiz.models import Quiz, Question, Choice, AIMetadata

class Command(BaseCommand):
    help = 'Generate AI questions for a quiz (development only)'

    def add_arguments(self, parser):
        parser.add_argument('quiz_id', type=str, help='UUID of the quiz')
        parser.add_argument('--n', type=int, default=3, help='Number of questions to generate')

    def handle(self, *args, **options):
        quiz_id = options['quiz_id']
        n = options['n']

        try:
            quiz = Quiz.objects.get(id=quiz_id)
        except Quiz.DoesNotExist:
            raise CommandError(f'Quiz {quiz_id} not found')

        if not gemini_service.is_configured:
            self.stderr.write('Gemini service not configured. Aborting.')
            return

        self.stdout.write(f'Generating {n} questions for quiz {quiz_id}...')
        questions = gemini_service.generate_questions(topic=quiz.topic, num_questions=n, difficulty=quiz.difficulty)

        if not questions:
            self.stderr.write('No questions returned by Gemini service. Check server logs for details.')
            return

        created = 0
        for i, q in enumerate(questions):
            question = Question.objects.create(
                quiz=quiz,
                text=q.get('question_text','')[:4000],
                question_type=q.get('question_type','short_answer'),
                correct_answer=q.get('correct_answer',''),
                explanation=q.get('explanation',''),
                order=quiz.questions.count() + i,
                ai_generated=True
            )

            if q.get('question_type') in ['mcq_single','mcq_multiple']:
                choices = q.get('choices', [])
                correct = q.get('correct_answer','')
                correct_indices = []
                try:
                    correct_indices = [int(x) for x in str(correct).split(',') if str(x).strip()!='']
                except Exception:
                    correct_indices = []
                for idx, ct in enumerate(choices):
                    Choice.objects.create(question=question, choice_text=ct, is_correct=(idx in correct_indices), order=idx)
            elif q.get('question_type') == 'true_false':
                # Create True and False choices for true/false questions
                correct_answer = str(q.get('correct_answer', '')).lower().strip()
                Choice.objects.create(
                    question=question,
                    choice_text='True',
                    is_correct=(correct_answer == 'true'),
                    order=0
                )
                Choice.objects.create(
                    question=question,
                    choice_text='False',
                    is_correct=(correct_answer == 'false'),
                    order=1
                )

            AIMetadata.objects.create(question=question, temperature_used=0.7, repetition_penalty=1.1, generation_prompt=f'Generated for CLI: {quiz.topic}')
            created += 1

        quiz.is_ai_generated = True
        quiz.save()

        self.stdout.write(self.style.SUCCESS(f'Created {created} questions for quiz {quiz_id}'))
