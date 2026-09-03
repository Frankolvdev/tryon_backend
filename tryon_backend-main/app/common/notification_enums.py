from enum import Enum


class AdminNotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AdminNotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class AdminNotificationSource(str, Enum):
    SYSTEM = "system"
    OBSERVABILITY = "observability"
    SECURITY = "security"
    BILLING = "billing"
    TRYON = "tryon"
    RUNPOD = "runpod"
    COMFYUI = "comfyui"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    STORAGE = "storage"
    USER = "user"
    AUDIT = "audit"
    INTEGRATION = "integration"
    WEBHOOK = "webhook"


class AdminNotificationDeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"