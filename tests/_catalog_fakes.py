"""Shared in-memory fake repos for catalog tests."""

from __future__ import annotations

from gclaw.models.catalog import ModelProvider, ModelRecord


class FakeProviderRepo:
    def __init__(self):
        self.store: dict[str, ModelProvider] = {}

    def create(self, p):
        self.store[p.id] = p
        return p

    def get(self, pid):
        return self.store.get(pid)

    def update(self, p):
        self.store[p.id] = p
        return p

    def delete(self, pid):
        self.store.pop(pid, None)

    def list_all(self):
        return list(self.store.values())


class FakeModelRepo:
    def __init__(self):
        self.store: dict[str, ModelRecord] = {}

    def create(self, m):
        self.store[m.id] = m
        return m

    def get(self, mid):
        return self.store.get(mid)

    def update(self, m):
        self.store[m.id] = m
        return m

    def delete(self, mid):
        self.store.pop(mid, None)

    def list_all(self):
        return list(self.store.values())

    def list_by_provider(self, pid):
        return [m for m in self.store.values() if m.provider_id == pid]
