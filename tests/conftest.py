from pathlib import Path

import pytest

from campuspulse.config import Settings
from campuspulse.csv_parser import parse_csv
from campuspulse.models import AnalysisPlan
from campuspulse.normalization import SYNTHETIC, normalize, suggest_mapping

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings():
    return Settings()


@pytest.fixture
def csv_bytes():
    return (ROOT / "data/campus_electricity_sample.csv").read_bytes()


@pytest.fixture
def pdf_bytes():
    return (ROOT / "data/campus_electricity_sample.pdf").read_bytes()


def dataset_from_csv(data: bytes):
    table = parse_csv(data, "fixture.csv", Settings())[0]
    return normalize(table, suggest_mapping(list(table.frame)), "kWh", SYNTHETIC)


@pytest.fixture
def dataset(csv_bytes):
    return dataset_from_csv(csv_bytes)


def plan(intent="aggregate", **kwargs):
    return AnalysisPlan(intent=intent, metric="electricity_kwh", aggregation="sum", **kwargs)
