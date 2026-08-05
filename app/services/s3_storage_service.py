from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy.orm import Session

from app.common.enums import IntegrationProvider, StorageProvider
from app.common.exceptions import ConflictException, NotFoundException
from app.services.integration_service import integration_service


class S3StorageService:
    """S3-compatible object storage client bound to a specific provider config."""

    PROVIDER_CONFIG = {
        StorageProvider.S3.value: IntegrationProvider.S3,
        StorageProvider.AMAZON_S3.value: IntegrationProvider.AMAZON_S3,
        StorageProvider.CLOUDFLARE_R2.value: IntegrationProvider.CLOUDFLARE_R2,
    }

    def normalize_provider(self, provider: str | StorageProvider | None) -> str:
        value = provider.value if isinstance(provider, StorageProvider) else str(provider or StorageProvider.S3.value)
        return value if value in self.PROVIDER_CONFIG else StorageProvider.S3.value

    def _get_config(self, db: Session, *, provider: str | StorageProvider = StorageProvider.S3.value):
        provider_value = self.normalize_provider(provider)
        integration_provider = self.PROVIDER_CONFIG[provider_value]
        try:
            config = integration_service.get_config(db, integration_provider)
        except NotFoundException:
            # Amazon's new provider transparently falls back to the historical S3 config.
            if provider_value == StorageProvider.AMAZON_S3.value:
                config = integration_service.get_config(db, IntegrationProvider.S3)
                integration_provider = IntegrationProvider.S3
            else:
                raise
        if not config.is_enabled:
            raise ConflictException(f"{integration_provider.value} integration is disabled.")
        parsed = integration_service._parse_json(config.config_json)
        bucket = parsed.get("bucket")
        region = parsed.get("region") or ("auto" if provider_value == StorageProvider.CLOUDFLARE_R2.value else None)
        endpoint_url = parsed.get("endpoint_url") or config.base_url or None
        if provider_value == StorageProvider.CLOUDFLARE_R2.value and not endpoint_url:
            account_id = parsed.get("account_id")
            if account_id:
                endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
        if not bucket:
            raise ConflictException(f"{provider_value} bucket is not configured.")
        if not config.api_key or not config.api_secret:
            raise ConflictException(f"{provider_value} credentials are not configured.")
        return config, parsed, bucket, region, endpoint_url, provider_value

    def _client(self, db: Session, *, provider: str | StorageProvider = StorageProvider.S3.value):
        config, parsed, bucket, region, endpoint_url, provider_value = self._get_config(db, provider=provider)
        addressing_style = parsed.get("addressing_style") or ("path" if endpoint_url else "virtual")
        return boto3.client(
            "s3", aws_access_key_id=config.api_key, aws_secret_access_key=config.api_secret,
            region_name=region or None, endpoint_url=endpoint_url,
            config=Config(signature_version="s3v4", s3={"addressing_style": addressing_style}),
        )

    def health_check(self, db: Session, *, provider: str | StorageProvider = StorageProvider.S3.value) -> dict[str, Any]:
        config, parsed, bucket, region, endpoint_url, provider_value = self._get_config(db, provider=provider)
        try:
            self._client(db, provider=provider_value).head_bucket(Bucket=bucket)
            return {"healthy": True, "provider": provider_value, "bucket": bucket, "region": region, "endpoint_url": endpoint_url}
        except (BotoCoreError, ClientError) as error:
            raise ConflictException(f"{provider_value} health check failed: {error}") from error

    def upload_bytes(self, db: Session, *, content: bytes, object_key: str, content_type: str | None = None,
                     provider: str | StorageProvider = StorageProvider.S3.value) -> dict[str, Any]:
        _, _, bucket, _, _, provider_value = self._get_config(db, provider=provider)
        kwargs = {"ContentType": content_type} if content_type else {}
        self._client(db, provider=provider_value).put_object(Bucket=bucket, Key=object_key, Body=content, **kwargs)
        return {"provider": provider_value, "bucket": bucket, "object_key": object_key,
                "public_url": self.build_public_url(db, object_key=object_key, provider=provider_value), "size_bytes": len(content)}

    def upload_file(self, db: Session, *, local_path: str, object_key: str, content_type: str | None = None,
                    provider: str | StorageProvider = StorageProvider.S3.value) -> dict[str, Any]:
        path=Path(local_path)
        if not path.is_file(): raise ConflictException("Local file does not exist.")
        return self.upload_bytes(db, content=path.read_bytes(), object_key=object_key, content_type=content_type, provider=provider)

    def read_bytes(self, db: Session, *, object_key: str, bucket: str | None = None,
                   provider: str | StorageProvider = StorageProvider.S3.value) -> bytes:
        _, _, configured_bucket, _, _, provider_value = self._get_config(db, provider=provider)
        response=self._client(db, provider=provider_value).get_object(Bucket=bucket or configured_bucket, Key=object_key)
        return response["Body"].read()

    def delete_file(self, db: Session, *, object_key: str, bucket: str | None = None,
                    provider: str | StorageProvider = StorageProvider.S3.value) -> None:
        _, _, configured_bucket, _, _, provider_value = self._get_config(db, provider=provider)
        self._client(db, provider=provider_value).delete_object(Bucket=bucket or configured_bucket, Key=object_key)

    def create_presigned_url(self, db: Session, *, object_key: str, bucket: str | None = None,
                             expires_in_seconds: int = 3600,
                             provider: str | StorageProvider = StorageProvider.S3.value) -> str:
        _, _, configured_bucket, _, _, provider_value = self._get_config(db, provider=provider)
        return self._client(db, provider=provider_value).generate_presigned_url(
            "get_object", Params={"Bucket": bucket or configured_bucket, "Key": object_key}, ExpiresIn=expires_in_seconds)

    def build_public_url(self, db: Session, *, object_key: str,
                         provider: str | StorageProvider = StorageProvider.S3.value) -> str:
        _, parsed, bucket, region, endpoint_url, provider_value = self._get_config(db, provider=provider)
        public_base = parsed.get("public_base_url") or parsed.get("cdn_base_url")
        if public_base: return f"{public_base.rstrip('/')}/{object_key}"
        if provider_value == StorageProvider.AMAZON_S3.value or (provider_value == StorageProvider.S3.value and not endpoint_url):
            return f"https://{bucket}.s3.{region}.amazonaws.com/{object_key}" if region else f"https://{bucket}.s3.amazonaws.com/{object_key}"
        # Private R2 buckets should normally be consumed through signed URLs.
        return f"{endpoint_url.rstrip('/')}/{bucket}/{object_key}" if endpoint_url else ""

    def generate_object_key(self, *, folder: str, original_filename: str) -> str:
        return f"{folder}/{uuid4().hex}{Path(original_filename).suffix}".replace("\\", "/")

s3_storage_service=S3StorageService()
