from enum import Enum


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class TryOnJobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TryOnItemType(str, Enum):
    CLOTHING = "clothing"
    FOOTWEAR = "footwear"


class QualityMode(str, Enum):
    STANDARD = "standard"
    HIGH = "high"


class StorageProvider(str, Enum):
    LOCAL = "local"
    S3 = "s3"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELED = "canceled"


class TokenTransactionType(str, Enum):
    CREDIT = "credit"
    DEBIT = "debit"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


class PricingOperationType(str, Enum):
    TRYON = "tryon"


class RunPodMode(str, Enum):
    SERVERLESS = "serverless"


class NotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class NotificationCategory(str, Enum):
    SYSTEM = "system"
    BILLING = "billing"
    AI = "ai"
    RUNPOD = "runpod"
    USER = "user"
    SECURITY = "security"
    STORAGE = "storage"
    EMAIL = "email"


class SupportTicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SupportTicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ScheduledJobStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


class ScheduledJobRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class SettingCategory(str, Enum):
    GENERAL = "general"
    AUTH = "auth"
    JWT = "jwt"
    SOCIAL_LOGIN = "social_login"
    EMAIL = "email"
    STORAGE = "storage"
    RUNPOD = "runpod"
    AI = "ai"
    TOKENS = "tokens"
    BILLING = "billing"
    SUBSCRIPTIONS = "subscriptions"
    PRICING = "pricing"
    SCHEDULER = "scheduler"
    FEATURE_FLAGS = "feature_flags"
    MAINTENANCE = "maintenance"
    ANALYTICS = "analytics"
    LOGGING = "logging"
    BACKUPS = "backups"
    SECURITY = "security"
    FRONTEND = "frontend"
    SYSTEM = "system"


class SettingValueType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    PASSWORD = "password"


class RbacModule(str, Enum):
    USERS = "users"
    AUTH = "auth"
    TOKENS = "tokens"
    BILLING = "billing"
    SUBSCRIPTIONS = "subscriptions"
    TRYON = "tryon"
    STORAGE = "storage"
    PRICING = "pricing"
    RUNPOD = "runpod"
    AI = "ai"
    ANALYTICS = "analytics"
    REPORTS = "reports"
    SETTINGS = "settings"
    FEATURE_FLAGS = "feature_flags"
    SYSTEM = "system"
    MONITORING = "monitoring"
    NOTIFICATIONS = "notifications"
    SUPPORT = "support"
    AUDIT = "audit"
    ACTIVITY = "activity"
    SCHEDULER = "scheduler"
    SEARCH = "search"
    API_KEYS = "api_keys"
    WEBHOOKS = "webhooks"
    ADMIN = "admin"


class RbacAction(str, Enum):
    READ = "read"
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    MANAGE = "manage"
    EXECUTE = "execute"
    EXPORT = "export"
    IMPORT = "import"
    REFUND = "refund"
    IMPERSONATE = "impersonate"


class FeaturePermissionKey(str, Enum):
    ADMIN_PANEL = "admin_panel"
    ANALYTICS = "analytics"
    REPORTS = "reports"
    BILLING = "billing"
    SUBSCRIPTIONS = "subscriptions"
    AI_TRYON = "ai_tryon"
    FOOTWEAR_TRYON = "footwear_tryon"
    HIGH_QUALITY = "high_quality"
    RUNPOD = "runpod"
    STORAGE = "storage"
    SUPPORT = "support"
    NOTIFICATIONS = "notifications"
    API_KEYS = "api_keys"
    WEBHOOKS = "webhooks"


class ApiKeyStatus(str, Enum):
    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"


class ApiKeyType(str, Enum):
    INTERNAL = "internal"
    USER = "user"
    ADMIN = "admin"
    INTEGRATION = "integration"
    WEBHOOK = "webhook"


class WebhookEndpointStatus(str, Enum):
    ACTIVE = "active"
    DISABLED = "disabled"


class WebhookEventStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELED = "canceled"


class WebhookDeliveryStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class IntegrationProvider(str, Enum):
    STRIPE = "stripe"
    RUNPOD = "runpod"
    COMFYUI = "comfyui"
    S3 = "s3"
    SMTP = "smtp"
    GOOGLE_OAUTH = "google_oauth"
    GITHUB_OAUTH = "github_oauth"
    APPLE_OAUTH = "apple_oauth"
    FACEBOOK_OAUTH = "facebook_oauth"


class IntegrationStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class IntegrationHealthStatus(str, Enum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"