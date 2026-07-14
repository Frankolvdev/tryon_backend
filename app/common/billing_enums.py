from enum import Enum


class BillingProvider(str, Enum):
    STRIPE = "stripe"
    MANUAL = "manual"


class BillingInterval(str, Enum):
    MONTH = "month"
    YEAR = "year"


class BillingPaymentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"


class BillingPaymentType(str, Enum):
    TOKEN_PURCHASE = "token_purchase"
    SUBSCRIPTION = "subscription"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    MANUAL = "manual"


class SubscriptionStatus(str, Enum):
    INCOMPLETE = "incomplete"
    INCOMPLETE_EXPIRED = "incomplete_expired"
    TRIALING = "trialing"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    UNPAID = "unpaid"
    PAUSED = "paused"
    CANCELED = "canceled"


class TokenPurchaseStatus(str, Enum):
    PENDING = "pending"
    PAID = "paid"
    CREDITED = "credited"
    FAILED = "failed"
    CANCELED = "canceled"
    REFUNDED = "refunded"


class BillingInvoiceStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    PAID = "paid"
    VOID = "void"
    UNCOLLECTIBLE = "uncollectible"


class BillingEventStatus(str, Enum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"
    IGNORED = "ignored"


class CouponDiscountType(str, Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class CouponDuration(str, Enum):
    ONCE = "once"
    FOREVER = "forever"
    REPEATING = "repeating"