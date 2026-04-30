from comtele_sdk.textmessage_service import TextMessageService

from RoadLabsAPI.settings import credentials


def send_sms(sender, content, receivers):
    """
    Send an SMS using the COMTELE API
    """
    sms_service = TextMessageService(credentials.COMTELE_API_KEY)
    sms_service.send(sender, content, receivers)
