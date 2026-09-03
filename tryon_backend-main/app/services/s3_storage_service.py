from pathlib import Path
from urllib.parse import urlparse
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
        configured_endpoint = parsed.get("endpoint_url")
        if provider_value == StorageProvider.CLOUDFLARE_R2.value:
            # base_url can be a public/custom delivery domain. It must never be
            # used as the private S3 API endpoint unless it is explicitly an R2
            # S3 endpoint. Prefer endpoint_url, then derive it from account_id.
            endpoint_url = configured_endpoint
            if not endpoint_url and config.base_url and "r2.cloudflarestorage.com" in config.base_url:
                endpoint_url = config.base_url
            if not endpoint_url:
                account_id = str(parsed.get("account_id") or "").strip()
                jurisdiction = str(parsed.get("jurisdiction") or "default").strip().lower()
                if account_id:
                    suffix = (
                        ".eu.r2.cloudflarestorage.com"
                        if jurisdiction == "eu"
                        else ".fedramp.r2.cloudflarestorage.com"
                        if jurisdiction == "fedramp"
                        else ".r2.cloudflarestorage.com"
                    )
                    endpoint_url = f"https://{account_id}{suffix}"
        else:
            endpoint_url = configured_endpoint or config.base_url or None

        if endpoint_url:
            endpoint_url = str(endpoint_url).strip().rstrip("/")

        if provider_value == StorageProvider.CLOUDFLARE_R2.value:
            if not endpoint_url:
                raise ConflictException(
                    "Cloudflare R2 requiere el Account ID o el endpoint S3 "
                    "https://<ACCOUNT_ID>.r2.cloudflarestorage.com."
                )
            parsed_endpoint = urlparse(endpoint_url)
            if (
                parsed_endpoint.scheme != "https"
                or not parsed_endpoint.netloc.endswith("r2.cloudflarestorage.com")
                or parsed_endpoint.path not in ("", "/")
            ):
                raise ConflictException(
                    "El endpoint de Cloudflare R2 no es válido. Usa el endpoint "
                    "S3 de la cuenta, no el dominio público ni una URL que incluya "
                    "el nombre del bucket."
                )
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
        _config, _parsed, bucket, region, endpoint_url, provider_value = self._get_config(db, provider=provider)
        try:
            client = self._client(db, provider=provider_value)
            if provider_value == StorageProvider.CLOUDFLARE_R2.value:
                # This validates the bucket and the object permissions actually
                # required by the platform. It also works for an empty bucket.
                client.list_objects_v2(Bucket=bucket, MaxKeys=1)
                message = f"Cloudflare R2 conectado correctamente al bucket {bucket}."
            else:
                client.head_bucket(Bucket=bucket)
                message = f"Almacenamiento conectado correctamente al bucket {bucket}."
            return {
                "healthy": True,
                "provider": provider_value,
                "bucket": bucket,
                "region": region,
                "endpoint_url": endpoint_url,
                "message": message,
            }
        except ClientError as error:
            response = error.response or {}
            error_data = response.get("Error") or {}
            code = str(error_data.get("Code") or "")
            status = (response.get("ResponseMetadata") or {}).get("HTTPStatusCode")
            if provider_value == StorageProvider.CLOUDFLARE_R2.value and (status == 404 or code in {"404", "NoSuchBucket"}):
                detail = (
                    f"Cloudflare R2 no encontró el bucket '{bucket}'. Verifica el nombre exacto, "
                    "el Account ID y, si el bucket usa jurisdicción EU o FedRAMP, configura "
                    "el endpoint correspondiente."
                )
            elif status in {401, 403} or code in {"AccessDenied", "Unauthorized", "InvalidAccessKeyId", "SignatureDoesNotMatch"}:
                detail = (
                    f"{provider_value} rechazó las credenciales o sus permisos. "
                    "Verifica Access Key ID, Secret Access Key y acceso de lectura/escritura al bucket."
                )
            else:
                detail = f"{provider_value} no superó la prueba de conexión ({code or status or 'error desconocido'})."
            raise ConflictException(detail) from error
        except BotoCoreError as error:
            raise ConflictException(
                f"{provider_value} no pudo conectarse al endpoint configurado: {error}"
            ) from error

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
