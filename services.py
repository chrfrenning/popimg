import os
import requests
from datetime import datetime, timedelta, timezone
from azure.communication.email import EmailClient
from azure.storage.blob import BlobServiceClient, BlobSasPermissions, generate_blob_sas
from config import AZURE_STORAGE_CS, AZURE_COMMS_CS, EMAIL_SENDER_ADDRESS
from config import CONTENT_SAFETY_ENDPOINT, CONTENT_SAFETY_KEY

class EmailService:
    def __init__(self, connection_string = AZURE_COMMS_CS, sender_address = EMAIL_SENDER_ADDRESS):
        self.connection_string = connection_string
        self.sender_address = sender_address

    def send_email(self, recipientAddress, subject, body, wait_success = False):
        try:
            client = EmailClient.from_connection_string(self.connection_string)

            # if body starts with <!DOCTYPE html> then it is html content
            if body.startswith('<!DOCTYPE html>'):
                message = {
                    "senderAddress": self.sender_address,
                    "recipients":  {
                        "to": [{"address": recipientAddress }],
                    },
                    "content": {
                        "subject": subject,
                        "html": body,
                    }
                }
            else:
                message = {
                    "senderAddress": self.sender_address,
                    "recipients":  {
                        "to": [{"address": recipientAddress }],
                    },
                    "content": {
                        "subject": subject,
                        "plainText": body,
                    }
                }

            poller = client.begin_send(message)
            if not wait_success:
                return True
            
            result = poller.result()
            if result['error'] is not None:
                return False
            else:
                return True

        except Exception as ex:
            print(ex)
            return False
        
ORIGINALS_CONTAINER_NAME = 'orgs'
PREVIEWS_CONTAINER_NAME = 'pvs'

class BlobService:
    def __init__(self, connection_string = AZURE_STORAGE_CS):
        self.connection_string = connection_string
        self.blob_service_client = BlobServiceClient.from_connection_string(connection_string)

    def _upload_file_to_blob(self, local_file_name, container_name, blob_name, overwrite=False):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        with open(local_file_name, "rb") as data:
            blob_client.upload_blob(data, overwrite=overwrite)
        return blob_client.url
    
    def _upload_bytes_to_blob(self, data, container_name, blob_name, overwrite=False):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        blob_client.upload_blob(data, overwrite=overwrite)
        return blob_client.url

    def _download_file_from_blob(self, container_name, blob_name, local_file_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        with open(local_file_name, "wb") as my_blob:
            download_stream = blob_client.download_blob()
            my_blob.write(download_stream.readall())
        return local_file_name
    
    def _download_bytes_from_blob(self, container_name, blob_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        return blob_client.download_blob().readall()
    
    def _delete_blob(self, container_name, blob_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        blob_client.delete_blob()
        return True
    
    def _get_blob_sas_url(self, container_name, blob_name):
        blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
        blob_client = blob_service_client.get_blob_client(container=container_name, blob=blob_name)
        account_name, account_key = blob_client.account_name, blob_client.credential.account_key

        sas_token = generate_blob_sas(
            account_name=account_name,
            container_name=container_name,
            blob_name=blob_name,
            account_key=account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(hours=1)
        )

        # compose full url with token
        return f'https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}?{sas_token}'

    def upload_image(self, image_id, image_data, container_name = ORIGINALS_CONTAINER_NAME):
        return self._upload_bytes_to_blob(image_data, container_name, image_id)
    
    def get_image_url(self, image_id, container_name = ORIGINALS_CONTAINER_NAME):
        return self._get_blob_sas_url(container_name, image_id)
    
    def get_image(self, image_id, container_name = ORIGINALS_CONTAINER_NAME):
        return self._download_bytes_from_blob(container_name, image_id)
    
class ModerationService:
    def __init__(self, endpoint = CONTENT_SAFETY_ENDPOINT, key = CONTENT_SAFETY_KEY):
        self.endpoint = endpoint
        self.key = key

    def check_content(self, blob_url, threshold = 3):
        # NOTE: Does not support webp, we must convert to JPG
        # Also nice to make small resized version to speed up moderation
        request = {
            "image" : {
                "blobUrl": blob_url
            },
            "categories": ["Hate", "SelfHarm", "Sexual", "Violence"],
            "outputType": "FourSeverityLevels"
        }
        headers = {
            "Content-Type": "application/json",
            "Ocp-Apim-Subscription-Key": self.key
        }
        full_endpoint = f'{self.endpoint}/contentsafety/image:analyze?api-version=2024-09-01'
        response = requests.post(full_endpoint, json=request, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        result = response.json()
        for category in result['categoriesAnalysis']:
            if category["severity"] >= threshold:
                return False
        return True
    
#if __name__ == '__main__':
    #ModerationService().check_content("https://n1rw2sshgg.blob.core.windows.net/images/Liz-Gs8658g.200h.webp")
    #ModerationService().check_content("https://images.nubilefilms.com/assets/common/images/tubeTourThumbs/909/692/909692/thumbCropped_909692.jpg")
    #ModerationService().check_content("https://www.cosleylaw.com/images/easyblog_images/male-victim-domestic-abuse-violence.jpg")