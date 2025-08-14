from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Creates a superuser if it does not exist'

    def handle(self, *args, **options):
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@gmail.com',
                password='nawar1234'  # <-- غيرها قبل الرفع!
            )
            self.stdout.write(
                self.style.SUCCESS('Superuser "admin" created successfully!')
            )
        else:
            self.stdout.write('Superuser "admin" already exists.')