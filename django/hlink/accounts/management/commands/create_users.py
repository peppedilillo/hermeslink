from typing import NamedTuple

from django.core.management.base import BaseCommand

from accounts.models import CustomUser

class UserRecord(NamedTuple):
    username: str
    password: str
    email: str
    gang: str


def read_user_records(filename: str) -> list[UserRecord]:
    """Read user records from a file and return a list of UserRecord objects."""
    records = []
    with open(filename, 'r') as file:
        for line in file:
            if line.strip():  # Skip empty lines
                fields = line.strip().split()
                if len(fields) == 4:
                    records.append(UserRecord(*fields))
    return records


class Command(BaseCommand):
    help = (
        "Adds a list of users to the db.\n\n"
        "Usage: python manage.py create_users <user-filename>\n"
        "<user-filename> should consists of a plain text file with one user entry per line.\n"
        "A line entry is composed of a username, password, email, and gang flag (either 's', 'm' or 'v')."
    )

    def add_arguments(self, parser):
        parser.add_argument("filename")

    def handle(self, *args, **options):
        user_records = read_user_records(options['filename'])
        for u in user_records:
            print(u)
            try:
                CustomUser.objects.create_user(
                    username=u.username,
                    password=u.password,
                    email=u.email,
                    gang=u.gang,
                )
            except Exception:
                self.stdout.write(f"Failed adding user {u.username} to database.")
                raise
            self.stdout.write(f"Successfully added user {u.username}.")