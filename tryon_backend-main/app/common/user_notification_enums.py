from enum import Enum


class UserNotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"


class UserNotificationPriority(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class UserNotificationSource(str, Enum):
    SYSTEM = "system"
    TRYON = "tryon"
    BILLING = "billing"
    TOKENS = "tokens"
    SUBSCRIPTION = "subscription"
    SUPPORT = "support"
    SECURITY = "security"
    ANNOUNCEMENT = "announcement"


class UserNotificationEventType(str, Enum):
    TRYON_QUEUED = "tryon_queued"
    TRYON_STARTED = "tryon_started"
    TRYON_COMPLETED = "tryon_completed"
    TRYON_FAILED = "tryon_failed"

    TOKEN_PURCHASE_COMPLETED = (
        "token_purchase_completed"
    )
    TOKEN_PURCHASE_FAILED = (
        "token_purchase_failed"
    )
    TOKENS_REFUNDED = "tokens_refunded"
    LOW_TOKEN_BALANCE = "low_token_balance"

    PAYMENT_SUCCEEDED = "payment_succeeded"
    PAYMENT_FAILED = "payment_failed"
    REFUND_COMPLETED = "refund_completed"

    SUBSCRIPTION_ACTIVATED = (
        "subscription_activated"
    )
    SUBSCRIPTION_RENEWED = (
        "subscription_renewed"
    )
    SUBSCRIPTION_EXPIRING = (
        "subscription_expiring"
    )
    SUBSCRIPTION_CANCELLED = (
        "subscription_cancelled"
    )

    SUPPORT_REPLY_RECEIVED = (
        "support_reply_received"
    )
    SUPPORT_TICKET_CLOSED = (
        "support_ticket_closed"
    )

    SECURITY_ALERT = "security_alert"
    PASSWORD_CHANGED = "password_changed"
    NEW_LOGIN_DETECTED = "new_login_detected"

    SYSTEM_ANNOUNCEMENT = (
        "system_announcement"
    )
    MAINTENANCE_SCHEDULED = (
        "maintenance_scheduled"
    )