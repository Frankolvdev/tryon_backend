from enum import Enum


class RateLimitScope(str, Enum):
    GLOBAL = "global"
    IP = "ip"
    USER = "user"
    API_KEY = "api_key"
    ENDPOINT = "endpoint"


class RateLimitAlgorithm(str, Enum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW = "sliding_window"
    TOKEN_BUCKET = "token_bucket"


class RateLimitAction(str, Enum):
    ALLOW = "allow"
    THROTTLE = "throttle"
    BLOCK = "block"


class AbuseEventType(str, Enum):
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    LOGIN_BRUTE_FORCE = "login_brute_force"
    REGISTRATION_ABUSE = "registration_abuse"
    PASSWORD_RESET_ABUSE = "password_reset_abuse"
    TOKEN_REFRESH_ABUSE = "token_refresh_abuse"
    API_KEY_ABUSE = "api_key_abuse"
    TRYON_GENERATION_ABUSE = "tryon_generation_abuse"
    PAYMENT_ABUSE = "payment_abuse"
    WEBHOOK_ABUSE = "webhook_abuse"
    SUSPICIOUS_REQUEST = "suspicious_request"


class AbuseSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AbuseEventStatus(str, Enum):
    OPEN = "open"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class BlockTargetType(str, Enum):
    IP = "ip"
    USER = "user"
    API_KEY = "api_key"
    EMAIL = "email"
    DEVICE = "device"