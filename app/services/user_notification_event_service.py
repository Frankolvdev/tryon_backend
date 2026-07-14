from sqlalchemy.orm import Session

from app.services.localized_user_notification_service import (
    localized_user_notification_service,
)


class UserNotificationEventService:
    def tryon_completed(
        self,
        db: Session,
        *,
        user_id: int,
        tryon_job_id: int,
        result_url: str | None = None,
        image_url: str | None = None,
    ):
        return (
            localized_user_notification_service
            .create_for_user(
                db,
                user_id=user_id,
                title_key=(
                    "tryon.notification."
                    "completed.title"
                ),
                message_key=(
                    "tryon.notification."
                    "completed.message"
                ),
                title_default=(
                    "Your Try-On is ready"
                ),
                message_default=(
                    "Your virtual Try-On "
                    "completed successfully."
                ),
                notification_type="success",
                priority="normal",
                source="tryon",
                event_type="tryon_completed",
                action_url=(
                    result_url
                    or (
                        "/tryon/jobs/"
                        f"{tryon_job_id}"
                    )
                ),
                action_label_key=(
                    "common.view_result"
                ),
                action_label_default=(
                    "View result"
                ),
                entity_type="tryon_job",
                entity_id=tryon_job_id,
                image_url=image_url,
            )
        )

    def tryon_failed(
        self,
        db: Session,
        *,
        user_id: int,
        tryon_job_id: int,
        tokens_refunded: int = 0,
    ):
        message_key = (
            "tryon.notification."
            "failed.refunded"
            if tokens_refunded > 0
            else (
                "tryon.notification."
                "failed.message"
            )
        )

        return (
            localized_user_notification_service
            .create_for_user(
                db,
                user_id=user_id,
                title_key=(
                    "tryon.notification."
                    "failed.title"
                ),
                message_key=message_key,
                message_variables={
                    "tokens": tokens_refunded,
                },
                title_default=(
                    "Your Try-On could not "
                    "be completed"
                ),
                message_default=(
                    (
                        "The generation failed. "
                        f"{tokens_refunded} tokens "
                        "were returned."
                    )
                    if tokens_refunded > 0
                    else (
                        "The generation failed. "
                        "No tokens will be "
                        "permanently charged."
                    )
                ),
                notification_type="error",
                priority="high",
                source="tryon",
                event_type="tryon_failed",
                action_url=(
                    "/tryon/jobs/"
                    f"{tryon_job_id}"
                ),
                action_label_key=(
                    "common.view_details"
                ),
                action_label_default=(
                    "View details"
                ),
                entity_type="tryon_job",
                entity_id=tryon_job_id,
                metadata={
                    "tokens_refunded": (
                        tokens_refunded
                    ),
                },
            )
        )

    def token_purchase_completed(
        self,
        db: Session,
        *,
        user_id: int,
        purchase_id: int,
        tokens_added: int,
    ):
        return (
            localized_user_notification_service
            .create_for_user(
                db,
                user_id=user_id,
                title_key=(
                    "tokens.notification."
                    "purchase.title"
                ),
                message_key=(
                    "tokens.notification."
                    "purchase.message"
                ),
                message_variables={
                    "tokens": tokens_added,
                },
                title_default=(
                    "Tokens added to your account"
                ),
                message_default=(
                    f"{tokens_added} tokens were "
                    "added to your balance."
                ),
                notification_type="success",
                priority="normal",
                source="tokens",
                event_type=(
                    "token_purchase_completed"
                ),
                action_url="/account/tokens",
                action_label_key=(
                    "common.view_details"
                ),
                action_label_default=(
                    "View details"
                ),
                entity_type="token_purchase",
                entity_id=purchase_id,
                metadata={
                    "tokens_added": tokens_added,
                },
            )
        )

    def payment_failed(
        self,
        db: Session,
        *,
        user_id: int,
        payment_id: int,
    ):
        return (
            localized_user_notification_service
            .create_for_user(
                db,
                user_id=user_id,
                title_key=(
                    "billing.notification."
                    "failed.title"
                ),
                message_key=(
                    "billing.notification."
                    "failed.message"
                ),
                title_default=(
                    "Payment could not "
                    "be completed"
                ),
                message_default=(
                    "Review your payment method "
                    "and try again."
                ),
                notification_type="error",
                priority="high",
                source="billing",
                event_type="payment_failed",
                action_url="/account/billing",
                action_label_key=(
                    "common.view_details"
                ),
                action_label_default=(
                    "Review payment"
                ),
                entity_type="billing_payment",
                entity_id=payment_id,
                requires_action=True,
            )
        )

    def subscription_expiring(
        self,
        db: Session,
        *,
        user_id: int,
        subscription_id: int,
        days_remaining: int,
    ):
        return (
            localized_user_notification_service
            .create_for_user(
                db,
                user_id=user_id,
                title_key=(
                    "subscription.notification."
                    "expiring.title"
                ),
                message_key=(
                    "subscription.notification."
                    "expiring.message"
                ),
                message_variables={
                    "days": days_remaining,
                },
                title_default=(
                    "Your subscription "
                    "is expiring"
                ),
                message_default=(
                    "Your subscription expires "
                    f"in {days_remaining} day(s)."
                ),
                notification_type="warning",
                priority="high",
                source="subscription",
                event_type=(
                    "subscription_expiring"
                ),
                action_url=(
                    "/account/subscription"
                ),
                action_label_key=(
                    "common.manage_subscription"
                ),
                action_label_default=(
                    "Manage subscription"
                ),
                entity_type=(
                    "user_subscription"
                ),
                entity_id=subscription_id,
                requires_action=True,
                metadata={
                    "days_remaining": (
                        days_remaining
                    ),
                },
            )
        )

    def support_reply_received(
        self,
        db: Session,
        *,
        user_id: int,
        ticket_id: int,
    ):
        return (
            localized_user_notification_service
            .create_for_user(
                db,
                user_id=user_id,
                title_key=(
                    "support.notification."
                    "reply.title"
                ),
                message_key=(
                    "support.notification."
                    "reply.message"
                ),
                title_default=(
                    "Support replied to "
                    "your request"
                ),
                message_default=(
                    "A new response is available "
                    "in your ticket."
                ),
                notification_type="info",
                priority="normal",
                source="support",
                event_type=(
                    "support_reply_received"
                ),
                action_url=(
                    "/support/tickets/"
                    f"{ticket_id}"
                ),
                action_label_key=(
                    "common.view_details"
                ),
                action_label_default=(
                    "View response"
                ),
                entity_type="support_ticket",
                entity_id=ticket_id,
            )
        )


user_notification_event_service = (
    UserNotificationEventService()
)