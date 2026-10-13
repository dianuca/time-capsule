from django.apps import AppConfig


class CapsulesConfig(AppConfig):
    name = 'capsules'

    def ready(self):
        from . import signals  # noqa: F401
