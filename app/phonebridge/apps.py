from django.apps import AppConfig

class PhonebridgeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'phonebridge'
    verbose_name = 'Phone Bridge'
    
    def ready(self):
        # Import signals if you have any
        pass