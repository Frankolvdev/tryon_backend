from typing import Any

from redis.exceptions import RedisError

from app.common.time import utc_now
from app.core.redis_client import redis_client
from app.schemas.cache_health import (
    CacheCommandMetrics,
    CacheConnectionMetrics,
    CacheKeyspaceDatabaseMetrics,
    CacheMemoryMetrics,
    CacheServerMetrics,
)


class CacheServerMetricsService:
    RECOMMENDED_MAXMEMORY_POLICY = (
        "allkeys-lru"
    )

    def _int(
        self,
        value: Any,
        default: int = 0,
    ) -> int:
        try:
            return int(value)
        except (
            TypeError,
            ValueError,
        ):
            return default

    def _float(
        self,
        value: Any,
    ) -> float | None:
        try:
            return float(value)
        except (
            TypeError,
            ValueError,
        ):
            return None

    def _decode_value(
        self,
        value: Any,
    ) -> Any:
        if isinstance(value, bytes):
            return value.decode(
                "utf-8",
                errors="replace",
            )

        return value

    def _config_value(
        self,
        config: dict,
        key: str,
    ) -> str | None:
        value = config.get(key)

        if value is None:
            encoded_key = key.encode(
                "utf-8"
            )

            value = config.get(encoded_key)

        value = self._decode_value(value)

        return (
            str(value)
            if value is not None
            else None
        )

    def get_metrics(
        self,
    ) -> CacheServerMetrics:
        client = redis_client.get_client()

        server_info = client.info(
            section="server"
        )

        memory_info = client.info(
            section="memory"
        )

        clients_info = client.info(
            section="clients"
        )

        stats_info = client.info(
            section="stats"
        )

        replication_info = client.info(
            section="replication"
        )

        keyspace_info = client.info(
            section="keyspace"
        )

        maxmemory_config = client.config_get(
            "maxmemory"
        )

        policy_config = client.config_get(
            "maxmemory-policy"
        )

        hits = self._int(
            stats_info.get(
                "keyspace_hits"
            )
        )

        misses = self._int(
            stats_info.get(
                "keyspace_misses"
            )
        )

        total_reads = hits + misses

        hit_rate = (
            hits / total_reads
            if total_reads > 0
            else 0.0
        )

        databases: list[
            CacheKeyspaceDatabaseMetrics
        ] = []

        for database, raw_metrics in (
            keyspace_info.items()
        ):
            if not isinstance(
                raw_metrics,
                dict,
            ):
                continue

            databases.append(
                CacheKeyspaceDatabaseMetrics(
                    database=str(database),
                    keys=self._int(
                        raw_metrics.get(
                            "keys"
                        )
                    ),
                    expires=self._int(
                        raw_metrics.get(
                            "expires"
                        )
                    ),
                    average_ttl_ms=(
                        self._int(
                            raw_metrics.get(
                                "avg_ttl"
                            )
                        )
                        if raw_metrics.get(
                            "avg_ttl"
                        )
                        is not None
                        else None
                    ),
                )
            )

        maxmemory_bytes = self._int(
            self._config_value(
                maxmemory_config,
                "maxmemory",
            )
        )

        configured_policy = (
            self._config_value(
                policy_config,
                "maxmemory-policy",
            )
        )

        return CacheServerMetrics(
            redis_version=(
                server_info.get(
                    "redis_version"
                )
            ),
            redis_mode=(
                server_info.get(
                    "redis_mode"
                )
            ),
            uptime_seconds=self._int(
                server_info.get(
                    "uptime_in_seconds"
                )
            ),
            role=replication_info.get(
                "role"
            ),
            maxmemory_policy=(
                configured_policy
            ),
            recommended_maxmemory_policy=(
                self.RECOMMENDED_MAXMEMORY_POLICY
            ),
            memory=CacheMemoryMetrics(
                used_memory_bytes=self._int(
                    memory_info.get(
                        "used_memory"
                    )
                ),
                used_memory_human=(
                    memory_info.get(
                        "used_memory_human"
                    )
                ),
                used_memory_peak_bytes=(
                    self._int(
                        memory_info.get(
                            "used_memory_peak"
                        )
                    )
                ),
                used_memory_peak_human=(
                    memory_info.get(
                        "used_memory_peak_human"
                    )
                ),
                maxmemory_bytes=(
                    maxmemory_bytes
                ),
                maxmemory_human=(
                    memory_info.get(
                        "maxmemory_human"
                    )
                ),
                memory_fragmentation_ratio=(
                    self._float(
                        memory_info.get(
                            "mem_fragmentation_ratio"
                        )
                    )
                ),
            ),
            connections=CacheConnectionMetrics(
                connected_clients=self._int(
                    clients_info.get(
                        "connected_clients"
                    )
                ),
                blocked_clients=self._int(
                    clients_info.get(
                        "blocked_clients"
                    )
                ),
                total_connections_received=(
                    self._int(
                        stats_info.get(
                            "total_connections_received"
                        )
                    )
                ),
                rejected_connections=self._int(
                    stats_info.get(
                        "rejected_connections"
                    )
                ),
            ),
            commands=CacheCommandMetrics(
                total_commands_processed=(
                    self._int(
                        stats_info.get(
                            "total_commands_processed"
                        )
                    )
                ),
                instantaneous_ops_per_second=(
                    self._int(
                        stats_info.get(
                            "instantaneous_ops_per_sec"
                        )
                    )
                ),
                keyspace_hits=hits,
                keyspace_misses=misses,
                hit_rate=round(
                    hit_rate,
                    4,
                ),
            ),
            databases=databases,
            generated_at=utc_now(),
        )


cache_server_metrics_service = (
    CacheServerMetricsService()
)