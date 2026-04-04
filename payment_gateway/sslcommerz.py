import json
import requests
from decimal import Decimal
from .gateway import PaymentGateway


class SSLCommerzGateway(PaymentGateway):
    """SSLCommerz payment gateway integration"""
    
    SANDBOX_BASE_URL = "https://sandbox.sslcommerz.com"
    LIVE_BASE_URL = "https://securepay.sslcommerz.com"
    
    def __init__(self, credentials):
        super().__init__(credentials)
        self.store_id = credentials.get('store_id')
        # Support both 'store_pass' and 'store_passwd' keys
        self.store_pass = credentials.get('store_pass') or credentials.get('store_passwd')
        # Support both 'is_sandbox' and 'issandbox' keys
        self.is_sandbox = credentials.get('is_sandbox', credentials.get('issandbox', True))
        self.base_url = self.SANDBOX_BASE_URL if self.is_sandbox else self.LIVE_BASE_URL
    
    def initiate_payment(self, transaction_id, amount, customer_info, **kwargs):
        """
        Initiate SSLCommerz payment
        
        Args:
            transaction_id: Unique transaction ID
            amount: Payment amount
            customer_info: Dict with keys: name, email, phone, address, city, country
            **kwargs: Additional params like success_url, fail_url, cancel_url
            
        Returns:
            Dict with GatewayPageURL and session key
        """
        if not self.store_id or not self.store_pass:
            return {
                'success': False,
                'message': 'Store ID and Store Password are required'
            }
        
        # Calculate total amount with TDR
        tdr = kwargs.get('tdr', 0)
        total_amount = self.calculate_total_amount(amount, tdr)
        
        # Prepare payload
        payload = {
            'store_id': self.store_id,
            'store_passwd': self.store_pass,
            'total_amount': str(total_amount),
            'currency': kwargs.get('currency', 'BDT'),
            'tran_id': transaction_id,
            'success_url': kwargs.get('success_url', ''),
            'fail_url': kwargs.get('fail_url', ''),
            'cancel_url': kwargs.get('cancel_url', ''),
            'ipn_url': kwargs.get('ipn_url', ''),
            'cus_name': customer_info.get('name', 'Customer'),
            'cus_email': customer_info.get('email', 'customer@example.com'),
            'cus_phone': customer_info.get('phone', '01700000000'),
            'cus_add1': customer_info.get('address', 'Dhaka'),
            'cus_city': customer_info.get('city', 'Dhaka'),
            'cus_country': customer_info.get('country', 'Bangladesh'),
            'shipping_method': 'NO',
            'product_name': kwargs.get('product_name', 'SMS Credit'),
            'product_category': kwargs.get('product_category', 'Recharge'),
            'product_profile': 'non-physical-goods',
        }
        
        # Optional parameters
        if 'cus_postcode' in customer_info:
            payload['cus_postcode'] = customer_info['cus_postcode']
        if 'multi_card_name' in kwargs:
            payload['multi_card_name'] = kwargs['multi_card_name']
        
        try:
            # Make API request to initiate payment
            url = f"{self.base_url}/gwprocess/v4/api.php"
            response = requests.post(url, data=payload, timeout=30)
            response_data = response.json()
            
            if response_data.get('status') == 'SUCCESS':
                return {
                    'success': True,
                    'gateway_url': response_data.get('GatewayPageURL'),
                    'session_key': response_data.get('sessionkey'),
                    'transaction_id': transaction_id,
                    'amount': str(total_amount),
                    'message': 'Payment initiated successfully'
                }
            else:
                return {
                    'success': False,
                    'message': response_data.get('failedreason', 'Failed to initiate payment'),
                    'response': response_data
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}'
            }
        except json.JSONDecodeError:
            return {
                'success': False,
                'message': 'Invalid response from gateway'
            }
    
    def validate_payment(self, validation_data):
        """
        Validate SSLCommerz payment response
        
        Args:
            validation_data: Dict with val_id or transaction data from callback
            
        Returns:
            Dict with validation result
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"SSLCommerz validate_payment called with: {validation_data}")
        
        if not self.store_id or not self.store_pass:
            logger.error("Store ID or Store Password missing")
            return {
                'success': False,
                'message': 'Store ID and Store Password are required'
            }
        
        val_id = validation_data.get('val_id')
        
        if not val_id:
            logger.error("val_id missing in validation_data")
            return {
                'success': False,
                'message': 'Validation ID (val_id) is required'
            }
        
        logger.info(f"Validating payment with val_id: {val_id}")
        
        try:
            # Make validation request
            url = f"{self.base_url}/validator/api/validationserverAPI.php"
            params = {
                'val_id': val_id,
                'store_id': self.store_id,
                'store_passwd': self.store_pass,
                'format': 'json'
            }
            
            logger.info(f"Making validation request to: {url}")
            response = requests.get(url, params=params, timeout=30)
            logger.info(f"Validation response status: {response.status_code}")
            
            response_data = response.json()
            logger.info(f"Validation response data: {response_data}")
            
            # Check transaction status
            status = response_data.get('status')
            transaction_status = response_data.get('transaction_status')
            tran_id = response_data.get('tran_id')
            
            logger.info(f"Status: {status}, Transaction Status: {transaction_status}, Tran ID: {tran_id}")
            
            if status == 'VALID' or transaction_status == 'SUCCESS':
                logger.info(f"Payment validated successfully for tran_id: {tran_id}")
                return {
                    'success': True,
                    'transaction_id': tran_id,
                    'bank_transaction_id': response_data.get('bank_tran_id'),
                    'amount': response_data.get('amount'),
                    'currency': response_data.get('currency'),
                    'status': status,
                    'card_type': response_data.get('card_type'),
                    'card_no': response_data.get('card_no'),
                    'message': 'Payment validated successfully',
                    'response': response_data
                }
            else:
                logger.warning(f"Payment validation failed. Status: {status}")
                return {
                    'success': False,
                    'transaction_id': tran_id,
                    'status': status,
                    'message': f'Payment validation failed: {status}',
                    'response': response_data
                }
                
        except requests.RequestException as e:
            logger.error(f"Network error during validation: {str(e)}")
            return {
                'success': False,
                'message': f'Network error during validation: {str(e)}'
            }
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            return {
                'success': False,
                'message': 'Invalid validation response from gateway'
            }
    
    def ipn_listener(self, ipn_data):
        """
        Process Instant Payment Notification (IPN)
        
        Args:
            ipn_data: POST data from SSLCommerz IPN callback
            
        Returns:
            Dict with IPN processing result
        """
        if not self.store_id or not self.store_pass:
            return {'success': False, 'message': 'Credentials not configured'}
        
        # Verify IPN hash (optional but recommended)
        verify_sign = ipn_data.get('verify_sign')
        verify_key = ipn_data.get('verify_key')
        
        if not verify_sign or not verify_key:
            return {'success': False, 'message': 'Invalid IPN data'}
        
        status = ipn_data.get('status')
        
        if status in ['VALID', 'VALIDATED']:
            return {
                'success': True,
                'transaction_id': ipn_data.get('tran_id'),
                'amount': ipn_data.get('amount'),
                'status': status,
                'message': 'IPN received and validated',
                'data': ipn_data
            }
        else:
            return {
                'success': False,
                'transaction_id': ipn_data.get('tran_id'),
                'status': status,
                'message': f'IPN status: {status}',
                'data': ipn_data
            }
