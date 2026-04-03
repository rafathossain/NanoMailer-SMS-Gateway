from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentGateway(ABC):
    """Abstract base class for payment gateways"""
    
    def __init__(self, credentials):
        self.credentials = credentials
    
    @abstractmethod
    def initiate_payment(self, transaction_id, amount, customer_info, **kwargs):
        """
        Initiate a payment request
        
        Args:
            transaction_id: Unique transaction ID
            amount: Payment amount
            customer_info: Dict with customer details (name, email, phone, etc.)
            **kwargs: Additional gateway-specific parameters
            
        Returns:
            Dict with payment URL and session data
        """
        pass
    
    @abstractmethod
    def validate_payment(self, validation_data):
        """
        Validate a payment response/callback
        
        Args:
            validation_data: Data received from gateway callback
            
        Returns:
            Dict with validation result (success, transaction_id, message, etc.)
        """
        pass
    
    def calculate_total_amount(self, amount, tdr_percentage):
        """Calculate total amount including TDR"""
        amount = Decimal(str(amount))
        tdr_percentage = Decimal(str(tdr_percentage))
        tdr_amount = amount * (tdr_percentage / 100)
        return amount + tdr_amount
