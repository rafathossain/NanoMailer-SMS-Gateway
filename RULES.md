import logging

sms_logger = logging.getLogger('sms')
sms_logger.info("SMS sent")

txn_logger = logging.getLogger('transaction')
txn_logger.info("Payment received")

general_logger = logging.getLogger('general')
general_logger.info("User action")