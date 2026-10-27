"""Session invalidation tests with mocked Streamlit state, not a browser check."""

import pytest

st = pytest.importorskip("streamlit", reason="UI tests require Streamlit")

import app
from campuspulse.multi_source import SourceEntry
from campuspulse.models import Dataset


class FakeState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def test_remove_file_resets_history(monkeypatch, dataset):
    fake = FakeState(sources=[SourceEntry("one", "a.csv", "A", dataset)],
                     history=[{"result": "stale"}], generation=5,
                     active_cost_mode="From uploaded report")
    monkeypatch.setattr(app.st, "session_state", fake)
    app.rebuild_combined()
    assert fake.history == []
    assert fake.generation == 6
    assert len(fake.dataset.frame) == len(dataset.frame)
    fake.sources = []
    fake.history = [{"result": "old"}]
    app.rebuild_combined()
    assert fake.history == []
    assert "dataset" not in fake
