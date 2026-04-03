"""
ReveSMS API Integration
"""
import requests
import json
import re
import logging
from decimal import Decimal

logger = logging.getLogger(__name__)
sms_logger = logging.getLogger('sms')


class ReveSMSProvider:
    """
    ReveSMS API Provider for sending SMS
    """
    BASE_URL = "http://smpp.revesms.com"
    HTTP_PORT = 7788

    def __init__(self, credentials):
        """
        Initialize ReveSMS provider

        Args:
            credentials: Dict with 'api_key', 'secret_key', 'sender_id'
        """
        self.api_key = credentials.get('api_key')
        self.secret_key = credentials.get('secret_key')
        self.sender_id = credentials.get('sender_id', 'NanoMailer')

        if not self.api_key or not self.secret_key:
            raise ValueError("API Key and Secret Key are required for ReveSMS")

    @staticmethod
    def _has_unicode(text):
        """Check if text contains Unicode characters"""
        unicode_pattern = re.compile(r'[\u0080-\uFFFF]')
        return bool(unicode_pattern.search(text))

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

        payload = json.dumps({
            "apikey": self.api_key,
            "secretkey": self.secret_key,
            "callerID": sender_id or self.sender_id,
            "toUser": recipient,
            "messageContent": message
        })

        headers = {
            'Content-Type': 'application/json'
        }

        try:
            logger.info(f"Sending SMS to {recipient} via ReveSMS")
            sms_logger.info(f"SMS request initiated - Recipient: {recipient}, Sender: {sender_id or self.sender_id}")

            response = requests.post(
                f"{self.BASE_URL}:{self.HTTP_PORT}/sendtext",
                headers=headers,
                data=payload,
                timeout=30
            )

            response_data = response.json()
            logger.info(f"ReveSMS response: {response_data}")
            sms_logger.info(f"SMS response received - Recipient: {recipient}, Status: {response.status_code}")

            # Check if SMS was delivered based on Status code
            if self._is_sms_delivered(response_data):
                message_id = response_data.get('Message_ID')
                sms_logger.info(f"SMS sent successfully - Recipient: {recipient}, MessageID: {message_id}")
                return {
                    'success': True,
                    'message': 'SMS sent successfully',
                    'message_id': message_id,
                    'response': response_data
                }
            else:
                error_msg = response_data.get('message', 'Unknown error')
                logger.error(f"ReveSMS send failed: {error_msg}")
                sms_logger.error(f"SMS send failed - Recipient: {recipient}, Error: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg,
                    'response': response_data
                }

        except requests.RequestException as e:
            logger.error(f"ReveSMS network error: {str(e)}")
            sms_logger.error(f"SMS network error - Recipient: {recipient}, Error: {str(e)}")
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'response': None
            }
        except json.JSONDecodeError as e:
            logger.error(f"ReveSMS invalid JSON response: {str(e)}")
            sms_logger.error(f"SMS invalid JSON response - Recipient: {recipient}, Error: {str(e)}")
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
            sms_logger.info("Balance check request initiated")

            url = f"{self.BASE_URL}/sms/smsConfiguration/smsClientBalance.jsp?client=flarezen"
            headers = {
                'Content-Type': 'application/json'
            }

            response = requests.get(url, headers=headers, timeout=30)
            response_data = response.json()

            logger.info(f"ReveSMS balance response: {response_data}")
            sms_logger.info(f"Balance check response received - Status: {response.status_code}")

            if 'Balance' in response_data:
                balance = float(response_data['Balance'])
                sms_logger.info(f"Balance check successful - Balance: {balance}")
                return {
                    'success': True,
                    'balance': Decimal(str(balance)),
                    'currency': 'BDT',
                    'message': f"Balance: {balance} BDT",
                    'response': response_data
                }
            else:
                error_msg = 'Balance not found in response'
                logger.error(f"ReveSMS balance check failed: {error_msg}")
                sms_logger.error(f"Balance check failed - Error: {error_msg}")
                return {
                    'success': False,
                    'message': error_msg,
                    'response': response_data
                }

        except requests.RequestException as e:
            logger.error(f"ReveSMS balance check network error: {str(e)}")
            sms_logger.error(f"Balance check network error - Error: {str(e)}")
            return {
                'success': False,
                'message': f'Network error: {str(e)}',
                'response': None
            }
        except json.JSONDecodeError as e:
            logger.error(f"ReveSMS balance check invalid JSON: {str(e)}")
            sms_logger.error(f"Balance check invalid JSON response - Error: {str(e)}")
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
        # ReveSMS doesn't provide a separate status endpoint in the working implementation
        # Status is returned in the send response
        return {
            'success': True,
            'status': 'unknown',
            'message': 'Status check not available for this provider'
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

    @staticmethod
    def _is_sms_delivered(response):
        """
        Check if SMS was delivered based on response Status code

        Args:
            response: Response dict from send_sms

        Returns:
            True if delivered, False otherwise
        """
        try:
            delivery_status = int(response.get('Status', -1))
            if delivery_status == 0:
                return True
        except (ValueError, TypeError):
            pass
        return False


def get_revesms_provider(credentials):
    """
    Factory function to get ReveSMS provider instance

    Args:
        credentials: Dict with api_key, secret_key, sender_id

    Returns:
        ReveSMSProvider instance
    """
    return ReveSMSProvider(credentials)
