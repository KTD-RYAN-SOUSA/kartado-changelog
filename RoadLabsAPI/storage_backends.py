from botocore.exceptions import ClientError
from django.conf import settings
from storages.backends.s3 import S3Storage
from storages.utils import clean_name


class S3Boto3Storage2Step(S3Storage):
    def _save(self, name, content):
        if content.size:
            return super()._save(name, content)
        else:
            cleaned_name = clean_name(name)
            return cleaned_name

    def get_post_url(self, name):
        name = self._normalize_name(clean_name(name))
        post = self.bucket.meta.client.generate_presigned_post(self.bucket.name, name)
        return post

    def e_tag(self, name):
        name = self._normalize_name(clean_name(name))
        try:
            return self.connection.meta.client.head_object(
                Bucket=self.bucket_name, Key=name
            )["ETag"]
        except ClientError:
            return ""


class StaticStorage(S3Boto3Storage2Step):
    location = settings.AWS_STATIC_LOCATION


class PublicMediaStorage(S3Boto3Storage2Step):
    location = settings.AWS_PUBLIC_MEDIA_LOCATION
    file_overwrite = False


class PrivateMediaStorage(S3Boto3Storage2Step):
    location = settings.AWS_PRIVATE_MEDIA_LOCATION
    default_acl = "private"
    file_overwrite = False
    custom_domain = False
