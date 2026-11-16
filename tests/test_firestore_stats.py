from types import SimpleNamespace

from backend.firestore_repository import FirestoreRepository


class FakeAggregate:
    def __init__(self, value):
        self.value = value

    def get(self):
        return [[SimpleNamespace(value=self.value)]]


class FakeReference:
    def __init__(self, counts, filters=()):
        self.counts = counts
        self.filters = filters

    def where(self, field, operator, value):
        assert operator == "=="
        return FakeReference(self.counts, self.filters + ((field, value),))

    def count(self):
        if self.filters and self.filters[0][0] == "sent_on":
            return FakeAggregate(self.counts["sent_today"])
        return FakeAggregate(self.counts[self.filters])


def test_stats_keep_qualified_sent_and_archived_totals_separate():
    repository = object.__new__(FirestoreRepository)
    repository.collection = FakeReference({
        (): 1015,
        (("archived", False), ("sent", False)): 135,
        (("archived", False), ("sent", True)): 880,
        (("archived", True),): 0,
        (("sent", True),): 880,
        "sent_today": 0,
    })
    repository.blocklist = FakeReference({(): 1085})

    result = repository.stats()

    assert result["total"] == 2100
    assert result["qualified"] == 135
    assert result["active"] == 135
    assert result["archived"] == 1085
    assert result["sent"] == 880
