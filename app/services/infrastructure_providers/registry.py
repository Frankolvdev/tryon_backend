class InfrastructureProviderRegistry:
    def __init__(self): self._items = {}
    def register(self, adapter): self._items[adapter.key] = adapter; return adapter
    def get(self, key): return self._items[key]
    def keys(self): return tuple(self._items)

infrastructure_provider_registry = InfrastructureProviderRegistry()
