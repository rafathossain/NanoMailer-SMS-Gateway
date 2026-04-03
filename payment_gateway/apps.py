from django.apps import AppConfig


class PaymentGatewayConfig(AppConfig):
    name = 'payment_gateway'
    
    def ready(self):
        import payment_gateway.signals  # noqa
