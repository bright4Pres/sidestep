from django.apps import AppConfig


class BrtConfig(AppConfig):
    name = 'brt'

    def ready(self):
        import brt.signals
