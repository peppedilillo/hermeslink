import random
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from accounts.models import CustomUser
from configs.models import Configuration, SPACECRAFTS_NAMES
from hermes import CONFIG_TYPES
from hermes import CONFIG_SIZE


CONFIG_NUM = 1000
USERNAMES = [
    'engineer1', 'engineer2', 'engineer3', 'engineer4', 'engineer5',
    'scientist1', 'scientist2', 'scientist3', 'scientist4',
    'manager1', 'manager2',
]


class Command(BaseCommand):
    help = f'Generates {CONFIG_NUM} test Configuration objects for search testing'

    def handle(self, *args, **options):
        self.stdout.write('Starting test data generation...')
        test_users = self.create_test_users()
        self.generate_configurations(test_users)
        self.stdout.write(self.style.SUCCESS('Successfully generated 1000 test Configuration objects'))

    def create_test_users(self):
        """Create test users for authors and uplinkers"""
        users = []
        for username in USERNAMES:
            user, created = CustomUser.objects.get_or_create(
                username=username,
                defaults={
                    'email': f'{username}@example.com',
                    'first_name': username.capitalize(),
                    'is_staff': username.startswith('manager'),
                    'gang': 's' if username.startswith('scientist') else ('m' if username.startswith('engineer') else 'v'),
                }
            )

            if created:
                user.set_password('password123')
                user.save()
                self.stdout.write(f'Created test user: {username}')
            else:
                self.stdout.write(f'Using existing user: {username}')

            users.append(user)

        return users

    def generate_configurations(self, users):
        """Generate multiple configuration objects with varied data"""
        def random_dt(dt1, dt2):
            timestamp1 = dt1.timestamp()
            timestamp2 = dt2.timestamp()
            random_timestamp = random.uniform(timestamp1, timestamp2)
            return timezone.make_aware(datetime.fromtimestamp(random_timestamp))

        start_date = timezone.datetime(2023, 1, 1)
        end_date = timezone.now()

        configs = []
        for i in range(CONFIG_NUM):
            config_date = random_dt(start_date, end_date)
            author = random.choice([*filter(lambda x: x.username.startswith('scientist'), users)])

            # determine if it's submitted (80% chance)
            is_submitted = random.random() < 0.8
            submit_time = config_date if is_submitted else None

            # determine if it's uplinked (60% of submitted are uplinked)
            uplinked = False
            uplinked_by = None
            uplink_time = None

            if is_submitted and random.random() < 0.6:
                uplinked = True
                uplinked_by = random.choice([*filter(lambda x: x.username.startswith('engineer'), users)])
                uplink_time = random_dt(submit_time, end_date)

            # select random model with weighted distribution
            # H1, H2 are more common, H6 is rare
            model_weights = [0.25, 0.25, 0.20, 0.15, 0.10, 0.05]
            model = random.choices(SPACECRAFTS_NAMES, weights=model_weights, k=1)[0]

            # select random configuration
            nconfigs = random.randint(1, len(CONFIG_TYPES))
            config_types = random.sample(CONFIG_TYPES, nconfigs)
            config_data = {ct: b"x" * CONFIG_SIZE[ct] for ct in config_types}


            # Create configuration
            config = Configuration(
                date=config_date,
                author=author,
                submitted=is_submitted,
                submit_time=submit_time,
                uplinked=uplinked,
                uplinked_by=uplinked_by,
                uplink_time=uplink_time,
                model=model,
                **config_data,
            )

            configs.append(config)

            if (i + 1) % 100 == 0:
                self.stdout.write(f'Generated {i + 1} configurations')

        # Bulk create all configurations
        Configuration.objects.bulk_create(configs)
        self.stdout.write(f'Saved {len(configs)} configurations to database')
