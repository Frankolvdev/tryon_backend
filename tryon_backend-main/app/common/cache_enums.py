from enum import Enum


class CacheNamespace(str, Enum):
    SYSTEM = "system"
    SETTINGS = "settings"
    FEATURE_FLAGS = "feature-flags"
    PRICING = "pricing"
    TOKEN_PACKAGES = "token-packages"
    SUBSCRIPTION_PLANS = "subscription-plans"
    WORKFLOWS = "workflows"
    USERS = "users"
    BILLING = "billing"
    TRYON = "tryon"
    INTEGRATIONS = "integrations"
    RUNPOD = "runpod"
    STORAGE = "storage"
    ANALYTICS = "analytics"
    SECURITY = "security"
    API = "api"


class CacheOperation(str, Enum):
    HIT = "hit"
    MISS = "miss"
    SET = "set"
    DELETE = "delete"
    INVALIDATE_TAG = "invalidate_tag"
    ERROR = "error"


class CacheSerializationFormat(str, Enum):
    JSON = "json"
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    BYTES = "bytes"