from .sslcommerz import SSLCommerzGateway
from .aamarpay import AamarPayGateway


class GatewayFactory:
    """Factory class to get the appropriate payment gateway"""
    
    GATEWAY_CLASSES = {
        'SSLCOMMERZ': SSLCommerzGateway,
        'AAMARPAY': AamarPayGateway,
    }
    
    @classmethod
    def get_gateway(cls, gateway_class, credentials):
        """
        Get the appropriate gateway instance
        
        Args:
            gateway_class: String identifier for the gateway (e.g., 'SSLCOMMERZ')
            credentials: Dict with gateway credentials
            
        Returns:
            PaymentGateway instance
            
        Raises:
            ValueError: If gateway class is not supported
        """
        gateway_class = gateway_class.upper()
        
        if gateway_class not in cls.GATEWAY_CLASSES:
            raise ValueError(f"Unsupported gateway class: {gateway_class}. "
                           f"Supported classes: {list(cls.GATEWAY_CLASSES.keys())}")
        
        gateway_cls = cls.GATEWAY_CLASSES[gateway_class]
        return gateway_cls(credentials)
    
    @classmethod
    def register_gateway(cls, name, gateway_class):
        """Register a new gateway class"""
        cls.GATEWAY_CLASSES[name.upper()] = gateway_class
    
    @classmethod
    def get_supported_gateways(cls):
        """Get list of supported gateway classes"""
        return list(cls.GATEWAY_CLASSES.keys())
