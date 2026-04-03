"""
ReveSMS API Integration
API Documentation: https://www.revesms.com/developers
"""
import requests
import json
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)


class ReveSMSProvider:
    """
    ReveSMS API Provider for sending SMS
    """
    BASE_URL = "https://api.revesms.com"
    
    def __init__(self, credentials):
        """
        Initialize ReveSMS provider
        
        Args:
            credentials: Dict with 'api_key', 'api_secret', 'sender_id' (optional)
        """
        self.api_key = credentials.get('api_key')
        self.api_secret = credentials.get('api_secret')
        self.default_sender_id = credentials.get('sender_id', 'NanoMailer')
        
        if not self.api_key or not self.api_secret:
            raise ValueError("API Key and API Secret are required for ReveSMS")
    
    def send_sms(self, recipient, message, sender_id=None, message_type='TEXT'):
        """
        Send SMS via ReveSMS API
        
        Args:
            recipient: Phone number (e.g., 8801XXXXXXXXX or 01XXXXXXXXX)
            message: SMS message content
            sender_id: Sender ID (optional, uses default if not provided)
            message_type: 'TEXT' or 'UNICODE'
            
        Returns:
            Dict with success status and response data
        """
        if not recipient or not message:
            return {
                'success': False,
                'message': 'Recipient and message are required',
                'response': None
            }
        
        # Format recipient number (ensure it starts with 880)
        recipient = self._format_number(recipient)
        
        # Determine if message is Unicode
        if self._is_unicode(message):
            message_type = 'UNICODE'
        
        payload = {
            'apiKey': self.api_key,
            'apiSecret': self.api_secret,
            'recipient': recipient,
            'message': message,
            'senderId': sender_id or self.default_sender_id,
            'messageType': message_type
        }
        
        try:
            logger.info(f"Sending SMS to {recipient} via ReveSMS")
            
            response = requests.post(
                f"{self.BASE_URL}/v1/sms/send",
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=30
            )
            
            response_data = response.json()
            logger.info(f"ReveSMS response: {response_data}")
            
            if response.status_code == 200 and response_data.get('success'):
                return {
                    'success': True,
                    'message': 'SMS sent successfully',
                    'message_id': response_data.get('data', {}).get('messageId'),
                    'response': response_data
                }
            else:
                error_msg = response_data.get('message', 'Unknown error')
                logger.error(f"ReveSMS send failed: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg,
                    'response': response_data
                }
                
        except requests.RequestException as e:
            logger.error(f"ReveSMS network error: {str(e)}")
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'response': None
            }
        except json.JSONDecodeError as e:
            logger.error(f"ReveSMS invalid JSON response: {str(e)}")
            return {
                'success': False,
                'message': 'Invalid response from SMS gateway',
                'response': None
            }
    
    def check_balance(self):
        """
        Check ReveSMS account balance
        
        Returns:
            Dict with success status and balance info
        """
        try:
            logger.info("Checking ReveSMS balance")
            
            response = requests.get(
                f"{self.BASE_URL}/v1/account/balance",
                params={
                    'apiKey': self.api_key,
                    'apiSecret': self.api_secret
                },
                timeout=30
            )
            
            response_data = response.json()
            logger.info(f"ReveSMS balance response: {response_data}")
            
            if response.status_code == 200 and response_data.get('success'):
                data = response_data.get('data', {})
                return {
                    'success': True,
                    'balance': Decimal(str(data.get('balance', 0))),
                    'currency': data.get('currency', 'BDT'),
                    'message': f"Balance: {data.get('balance', 0)} {data.get('currency', 'BDT')}",
                    'response': response_data
                }
            else:
                error_msg = response_data.get('message', 'Unknown error')
                logger.error(f"ReveSMS balance check failed: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg,
                    'response': response_data
                }
                
        except requests.RequestException as e:
            logger.error(f"ReveSMS balance check network error: {str(e)}")
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'response': None
            }
        except json.JSONDecodeError as e:
            logger.error(f"ReveSMS balance check invalid JSON: {str(e)}")
            return {
                'success': False,
                'message': 'Invalid response from SMS gateway',
                'response': None
            }
    
    def get_delivery_status(self, message_id):
        """
        Get delivery status of a sent SMS
        
        Args:
            message_id: The message ID returned from send_sms
            
        Returns:
            Dict with delivery status
        """
        try:
            response = requests.get(
                f"{self.BASE_URL}/v1/sms/status",
                params={
                    'apiKey': self.api_key,
                    'apiSecret': self.api_secret,
                    'messageId': message_id
                },
                timeout=30
            )
            
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('success'):
                return {
                    'success': True,
                    'status': response_data.get('data', {}).get('status'),
                    'response': response_data
                }
            else:
                return {
                    'success': False,
                    'message': response_data.get('message', 'Failed to get status'),
                    'response': response_data
                }
                
        except requests.RequestException as e:
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'response': None
            }
    
    def _format_number(self, number):
        """
        Format phone number to international format (8801XXXXXXXXX)
        
        Args:
            number: Phone number in various formats
            
        Returns:
            Formatted number
        """
        # Remove any non-digit characters
        number = ''.join(filter(str.isdigit, number))
        
        # If starts with 01, replace with 8801
        if number.startswith('01') and len(number) == 11:
            number = '88' + number
        
        return number
    
    def _is_unicode(self, message):
        """
        Check if message contains Unicode characters (Bangla/non-ASCII)
        
        Args:
            message: SMS message
            
        Returns:
            True if Unicode, False otherwise
        """
        try:
            message.encode('ascii')
            return False
        except UnicodeEncodeError:
            return True


def get_revesms_provider(credentials):
    """
    Factory function to get ReveSMS provider instance
    
    Args:
        credentials: Dict with api_key, api_secret, sender_id
        
    Returns:
        ReveSMSProvider instance
    """
    return ReveSMSProvider(credentials)
