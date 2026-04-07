import json
import requests
from decimal import Decimal

from django.conf import settings

from .gateway import PaymentGateway


class AamarPayGateway(PaymentGateway):
    """aamarPay payment gateway integration"""
    
    SANDBOX_BASE_URL = "https://sandbox.aamarpay.com"
    LIVE_BASE_URL = "https://secure.aamarpay.com"
    
    def __init__(self, credentials):
        super().__init__(credentials)
        self.store_id = credentials.get('store_id')
        self.signature_key = credentials.get('signature_key')
        self.is_sandbox = credentials.get('is_sandbox', True)
        self.base_url = self.SANDBOX_BASE_URL if self.is_sandbox else self.LIVE_BASE_URL
    
    def initiate_payment(self, transaction_id, amount, customer_info, **kwargs):
        """
        Initiate aamarPay payment
        
        Args:
            transaction_id: Unique transaction ID
            amount: Payment amount
            customer_info: Dict with keys: name, email, phone, address, city, country
            **kwargs: Additional params like success_url, fail_url, cancel_url
            
        Returns:
            Dict with payment_url and transaction data
        """
        if not self.store_id or not self.signature_key:
            return {
                'success': False,
                'message': 'Store ID and Signature Key are required'
            }
        
        # Calculate total amount with TDR
        tdr = kwargs.get('tdr', 0)
        total_amount = self.calculate_total_amount(amount, tdr)
        
        success_url = kwargs.get('success_url', '')
        fail_url = kwargs.get('fail_url', '')
        cancel_url = kwargs.get('cancel_url', '')
        
        if not settings.DEBUG:
            success_url = str(success_url).replace('http://', 'https://')
            fail_url = str(fail_url).replace('http://', 'https://')
            cancel_url = str(cancel_url).replace('http://', 'https://')
        
        # Prepare payload for aamarPay
        payload = {
            'store_id': self.store_id,
            'signature_key': self.signature_key,
            'amount': str(total_amount),
            'currency': kwargs.get('currency', 'BDT'),
            'tran_id': transaction_id,
            'success_url': success_url,
            'fail_url': fail_url,
            'cancel_url': cancel_url,
            'cus_name': customer_info.get('name', 'Customer'),
            'cus_email': customer_info.get('email', 'customer@example.com'),
            'cus_phone': customer_info.get('phone', '01700000000'),
            'cus_add1': customer_info.get('address', 'Dhaka'),
            'cus_city': customer_info.get('city', 'Dhaka'),
            'cus_country': customer_info.get('country', 'Bangladesh'),
            'desc': kwargs.get('product_name', 'SMS Credit Recharge'),
            'type': 'json',
        }
        
        # Optional parameters
        if 'cus_postcode' in customer_info:
            payload['cus_postcode'] = customer_info['cus_postcode']
        if 'cus_add2' in customer_info:
            payload['cus_add2'] = customer_info['cus_add2']
        if 'opt_a' in kwargs:
            payload['opt_a'] = kwargs['opt_a']
        if 'opt_b' in kwargs:
            payload['opt_b'] = kwargs['opt_b']
        if 'opt_c' in kwargs:
            payload['opt_c'] = kwargs['opt_c']
        if 'opt_d' in kwargs:
            payload['opt_d'] = kwargs['opt_d']
        
        try:
            # Make API request to initiate payment
            url = f"{self.base_url}/index.php"
            response = requests.post(url, data=payload, timeout=30)
            response_data = response.json()
            
            # aamarPay returns a JSON response with payment_url
            if response_data.get('result') == 'true' and response_data.get('payment_url'):
                return {
                    'success': True,
                    'gateway_url': response_data.get('payment_url'),
                    'session_key': response_data.get('session_key', ''),
                    'transaction_id': transaction_id,
                    'amount': str(total_amount),
                    'message': 'Payment initiated successfully'
                }
            else:
                return {
                    'success': False,
                    'message': response_data.get('reason', 'Failed to initiate payment'),
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
        Validate aamarPay payment response
        
        Args:
            validation_data: Dict with data from callback (mer_txnid, pay_txnid, etc.)
            
        Returns:
            Dict with validation result
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"AamarPay validate_payment called with: {validation_data}")
        
        if not self.store_id or not self.signature_key:
            logger.error("Store ID or Signature Key missing")
            return {
                'success': False,
                'message': 'Store ID and Signature Key are required'
            }
        
        # aamarPay sends these parameters in the callback
        mer_txnid = validation_data.get('mer_txnid') or validation_data.get('tran_id')
        pay_txnid = validation_data.get('pay_txnid') or validation_data.get('bank_tran_id')
        amount = validation_data.get('amount')
        currency = validation_data.get('currency', 'BDT')
        
        # Check for status in POST data
        status = validation_data.get('pay_status') or validation_data.get('status')
        
        if not mer_txnid:
            logger.error("Transaction ID missing in validation data")
            return {
                'success': False,
                'message': 'Transaction ID is required'
            }
        
        logger.info(f"Validating payment for tran_id: {mer_txnid}, status: {status}")
        
        # For aamarPay, we need to verify the payment via their verification API
        try:
            # Make verification request
            url = f"{self.base_url}/api/v1/trxcheck/request.php"
            params = {
                'store_id': self.store_id,
                'signature_key': self.signature_key,
                'request_id': mer_txnid,
                'type': 'json',
            }
            
            logger.info(f"Making verification request to: {url}")
            response = requests.get(url, params=params, timeout=30)
            logger.info(f"Verification response status: {response.status_code}")
            
            response_data = response.json()
            logger.info(f"Verification response data: {response_data}")
            
            # Check if it's a list or dict response
            if isinstance(response_data, list) and len(response_data) > 0:
                payment_info = response_data[0]
            elif isinstance(response_data, dict):
                payment_info = response_data
            else:
                payment_info = {}
            
            pay_status = payment_info.get('pay_status', '').upper()
            
            if pay_status == 'SUCCESSFUL' or status == 'SUCCESSFUL':
                logger.info(f"Payment validated successfully for tran_id: {mer_txnid}")
                return {
                    'success': True,
                    'transaction_id': mer_txnid,
                    'bank_transaction_id': payment_info.get('pg_txnid') or pay_txnid,
                    'amount': payment_info.get('amount') or amount,
                    'currency': currency,
                    'status': 'SUCCESSFUL',
                    'card_type': payment_info.get('card_type', 'N/A'),
                    'message': 'Payment validated successfully',
                    'response': response_data
                }
            else:
                logger.warning(f"Payment validation failed. Status: {pay_status}")
                return {
                    'success': False,
                    'transaction_id': mer_txnid,
                    'status': pay_status,
                    'message': f'Payment validation failed: {pay_status}',
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
        Process Instant Payment Notification (IPN) from aamarPay
        
        Args:
            ipn_data: POST data from aamarPay IPN callback
            
        Returns:
            Dict with IPN processing result
        """
        if not self.store_id or not self.signature_key:
            return {'success': False, 'message': 'Credentials not configured'}
        
        pay_status = ipn_data.get('pay_status', '').upper()
        mer_txnid = ipn_data.get('mer_txnid')
        
        if pay_status == 'SUCCESSFUL':
            return {
                'success': True,
                'transaction_id': mer_txnid,
                'amount': ipn_data.get('amount'),
                'status': pay_status,
                'message': 'IPN received and validated',
                'data': ipn_data
            }
        else:
            return {
                'success': False,
                'transaction_id': mer_txnid,
                'status': pay_status,
                'message': f'IPN status: {pay_status}',
                'data': ipn_data
            }
