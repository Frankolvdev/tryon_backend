from sqlalchemy.orm import Session

from app.models.activity_log import ActivityLog
from app.models.audit_log import AuditLog
from app.models.notification import Notification
from app.models.storage_file import StorageFile
from app.models.support_ticket import SupportTicket
from app.models.token_transaction import TokenTransaction
from app.models.tryon_job import TryOnJob
from app.models.user import User
from app.schemas.search import SearchResponse, SearchResultItem


class SearchService:
    def search(
        self,
        db: Session,
        *,
        query: str,
        entities: list[str] | None = None,
        page: int = 1,
        page_size: int = 20,
        filters: dict | None = None,
    ) -> SearchResponse:
        filters = filters or {}
        query_clean = query.strip().lower()

        results: list[SearchResultItem] = []

        enabled_entities = set(entities or [
            "users",
            "tryon_jobs",
            "storage_files",
            "support_tickets",
            "notifications",
            "audit_logs",
            "activity_logs",
            "token_transactions",
        ])

        if "users" in enabled_entities:
            results.extend(self._search_users(db, query_clean))

        if "tryon_jobs" in enabled_entities:
            results.extend(self._search_tryon_jobs(db, query_clean))

        if "storage_files" in enabled_entities:
            results.extend(self._search_storage_files(db, query_clean))

        if "support_tickets" in enabled_entities:
            results.extend(self._search_support_tickets(db, query_clean))

        if "notifications" in enabled_entities:
            results.extend(self._search_notifications(db, query_clean))

        if "audit_logs" in enabled_entities:
            results.extend(self._search_audit_logs(db, query_clean))

        if "activity_logs" in enabled_entities:
            results.extend(self._search_activity_logs(db, query_clean))

        if "token_transactions" in enabled_entities:
            results.extend(self._search_token_transactions(db, query_clean))

        results = self._apply_filters(results, filters)
        results.sort(key=lambda item: item.relevance_score, reverse=True)

        total = len(results)
        start = (page - 1) * page_size
        end = start + page_size

        return SearchResponse(
            query=query,
            page=page,
            page_size=page_size,
            total=total,
            items=results[start:end],
        )

    def _score(self, query: str, values: list[str | None]) -> int:
        score = 0

        for value in values:
            if not value:
                continue

            value_lower = str(value).lower()

            if value_lower == query:
                score += 100
            elif value_lower.startswith(query):
                score += 60
            elif query in value_lower:
                score += 30

        return score

    def _apply_filters(
        self,
        results: list[SearchResultItem],
        filters: dict,
    ) -> list[SearchResultItem]:
        if not filters:
            return results

        filtered = []

        for item in results:
            keep = True

            for key, expected_value in filters.items():
                if item.metadata.get(key) != expected_value:
                    keep = False
                    break

            if keep:
                filtered.append(item)

        return filtered

    def _search_users(self, db: Session, query: str) -> list[SearchResultItem]:
        users = db.query(User).limit(500).all()
        results = []

        for user in users:
            score = self._score(query, [user.email, user.full_name, user.role, user.status])

            if score > 0 or query == str(user.id):
                results.append(
                    SearchResultItem(
                        entity="users",
                        id=str(user.id),
                        title=user.email,
                        description=user.full_name,
                        url=f"/admin/users/{user.id}",
                        relevance_score=score + 10,
                        metadata={
                            "role": user.role,
                            "status": user.status,
                            "is_active": user.is_active,
                        },
                    )
                )

        return results

    def _search_tryon_jobs(self, db: Session, query: str) -> list[SearchResultItem]:
        jobs = db.query(TryOnJob).limit(500).all()
        results = []

        for job in jobs:
            score = self._score(
                query,
                [
                    str(job.id),
                    job.status,
                    job.item_type,
                    job.quality_mode,
                    job.runpod_job_id,
                    job.comfy_workflow_name,
                ],
            )

            if score > 0:
                results.append(
                    SearchResultItem(
                        entity="tryon_jobs",
                        id=str(job.id),
                        title=f"Try-On Job #{job.id}",
                        description=f"{job.item_type} / {job.quality_mode} / {job.status}",
                        url=f"/admin/tryon-jobs/{job.id}",
                        relevance_score=score,
                        metadata={
                            "status": job.status,
                            "item_type": job.item_type,
                            "quality_mode": job.quality_mode,
                            "user_id": job.user_id,
                        },
                    )
                )

        return results

    def _search_storage_files(self, db: Session, query: str) -> list[SearchResultItem]:
        files = db.query(StorageFile).limit(500).all()
        results = []

        for file_obj in files:
            score = self._score(
                query,
                [
                    str(file_obj.id),
                    file_obj.object_key,
                    file_obj.original_filename,
                    file_obj.content_type,
                    file_obj.provider,
                ],
            )

            if score > 0:
                results.append(
                    SearchResultItem(
                        entity="storage_files",
                        id=str(file_obj.id),
                        title=file_obj.original_filename or file_obj.object_key,
                        description=file_obj.content_type,
                        url=f"/admin/storage-files/{file_obj.id}",
                        relevance_score=score,
                        metadata={
                            "provider": file_obj.provider,
                            "user_id": file_obj.user_id,
                            "content_type": file_obj.content_type,
                        },
                    )
                )

        return results

    def _search_support_tickets(self, db: Session, query: str) -> list[SearchResultItem]:
        tickets = db.query(SupportTicket).limit(500).all()
        results = []

        for ticket in tickets:
            score = self._score(
                query,
                [
                    str(ticket.id),
                    ticket.subject,
                    ticket.message,
                    ticket.status,
                    ticket.priority,
                ],
            )

            if score > 0:
                results.append(
                    SearchResultItem(
                        entity="support_tickets",
                        id=str(ticket.id),
                        title=ticket.subject,
                        description=ticket.message[:160],
                        url=f"/admin/support-tickets/{ticket.id}",
                        relevance_score=score,
                        metadata={
                            "status": ticket.status,
                            "priority": ticket.priority,
                            "user_id": ticket.user_id,
                        },
                    )
                )

        return results

    def _search_notifications(self, db: Session, query: str) -> list[SearchResultItem]:
        notifications = db.query(Notification).limit(500).all()
        results = []

        for notification in notifications:
            score = self._score(
                query,
                [
                    str(notification.id),
                    notification.title,
                    notification.message,
                    notification.category,
                    notification.notification_type,
                ],
            )

            if score > 0:
                results.append(
                    SearchResultItem(
                        entity="notifications",
                        id=str(notification.id),
                        title=notification.title,
                        description=notification.message[:160],
                        url=f"/admin/notifications",
                        relevance_score=score,
                        metadata={
                            "category": notification.category,
                            "notification_type": notification.notification_type,
                            "is_read": notification.is_read,
                        },
                    )
                )

        return results

    def _search_audit_logs(self, db: Session, query: str) -> list[SearchResultItem]:
        logs = db.query(AuditLog).limit(500).all()
        results = []

        for log in logs:
            score = self._score(
                query,
                [
                    str(log.id),
                    log.action,
                    log.entity_type,
                    log.entity_id,
                    log.description,
                    log.ip_address,
                ],
            )

            if score > 0:
                results.append(
                    SearchResultItem(
                        entity="audit_logs",
                        id=str(log.id),
                        title=log.action,
                        description=log.description,
                        url=f"/admin/audit-logs",
                        relevance_score=score,
                        metadata={
                            "entity_type": log.entity_type,
                            "entity_id": log.entity_id,
                            "actor_user_id": log.actor_user_id,
                        },
                    )
                )

        return results

    def _search_activity_logs(self, db: Session, query: str) -> list[SearchResultItem]:
        logs = db.query(ActivityLog).limit(500).all()
        results = []

        for log in logs:
            score = self._score(
                query,
                [
                    str(log.id),
                    log.action,
                    log.description,
                    log.ip_address,
                ],
            )

            if score > 0:
                results.append(
                    SearchResultItem(
                        entity="activity_logs",
                        id=str(log.id),
                        title=log.action,
                        description=log.description,
                        url=f"/admin/activity-logs",
                        relevance_score=score,
                        metadata={
                            "user_id": log.user_id,
                        },
                    )
                )

        return results

    def _search_token_transactions(
        self,
        db: Session,
        query: str,
    ) -> list[SearchResultItem]:
        transactions = db.query(TokenTransaction).limit(500).all()
        results = []

        for transaction in transactions:
            score = self._score(
                query,
                [
                    str(transaction.id),
                    str(transaction.user_id),
                    transaction.transaction_type,
                    transaction.source,
                    transaction.reference_id,
                    transaction.description,
                ],
            )

            if score > 0:
                results.append(
                    SearchResultItem(
                        entity="token_transactions",
                        id=str(transaction.id),
                        title=f"Token Transaction #{transaction.id}",
                        description=transaction.description,
                        url=f"/admin/users/{transaction.user_id}/token-transactions",
                        relevance_score=score,
                        metadata={
                            "user_id": transaction.user_id,
                            "transaction_type": transaction.transaction_type,
                            "source": transaction.source,
                        },
                    )
                )

        return results


search_service = SearchService()