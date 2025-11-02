from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = "Create or update the Django superuser (for Render PostgreSQL)"

    def handle(self, *args, **kwargs):
        User = get_user_model()
        username = "Shadow"
        email = "test46ge8g4@gmail.com"
        password = "Qwerty123"  # change if you like

        user, created = User.objects.get_or_create(username=username, defaults={
            "email": email,
            "is_staff": True,
            "is_superuser": True,
        })

        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created successfully."))
        else:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.WARNING(f"Superuser '{username}' already existed. Password updated."))
