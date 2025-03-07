from django.db.models import Model


class LogRouter:
    """A custom router for the logger database"""

    def db_for_read(self, model: Model, **hints):
        model_name = model._meta.model_name
        if model_name == "logentry":
            return "logdb"
        else:
            return None

    def db_for_write(self, model: Model, **hints):
        model_name = model._meta.model_name
        if model_name == "logentry":
            return "logdb"
        else:
            return None

    def allow_migrate(self, db: str, app_label: str, model_name: str = None, **hints):
        if model_name == "logentry":
            return db == "logdb"
        else:
            return db == "default"
