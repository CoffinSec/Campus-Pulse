"""Session-only file registry and source-aware combination; never stores uploaded bytes."""

import re
from dataclasses import dataclass
from difflib import get_close_matches

import pandas as pd

from campuspulse.ingestion import safe_filename
from campuspulse.models import Caveat, ColumnDefinition, DataError, Dataset


@dataclass
class SourceEntry:
    source_id: str
    filename: str
    label: str
    dataset: Dataset


def source_id_for(name: str, taken: set[str]) -> str:
    clean = safe_filename(name)
    stem = re.sub(r"[^a-z0-9]+", "-", clean.rsplit('.', 1)[0].lower()).strip('-')[:55] or "report"
    candidate = stem
    index = 2
    while candidate in taken:
        candidate = f"{stem}-{index}"
        index += 1
    return candidate


def bind_source(dataset: Dataset, source_id: str, label: str) -> Dataset:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,65}", source_id):
        raise DataError("Invalid source identifier")
    if not label.strip() or len(label) > 100:
        raise DataError("Choose a nonempty source label up to 100 characters")
    frame = dataset.frame.copy()
    frame["source_id"] = source_id
    frame["source_label"] = label.strip()
    # IDs from different PDFs/CSVs may reuse row numbers; combine with source identity.
    frame["row_id"] = frame["row_id"].astype(str).map(lambda v: f"{source_id}:{v}")
    return Dataset(frame, dataset.columns, dataset.classification, list(dataset.warnings),
                   dataset.custom_tariff_inr_per_kwh)


def combine_sources(entries: list[SourceEntry]) -> Dataset:
    if not entries:
        raise DataError("Confirm at least one source")
    ids = [e.source_id for e in entries]
    if len(set(ids)) != len(ids):
        raise DataError("Source IDs must be unique")
    # Each source must have been independently validated before combination.
    frames = [bind_source(e.dataset, e.source_id, e.label).frame for e in entries]
    combined = pd.concat(frames, ignore_index=True, sort=False)
    if combined.duplicated(["source_id", "building_name", "month"]).any():
        raise DataError("Duplicate building/month within a source")
    definitions = {c.name: c for e in entries for c in e.dataset.columns}
    for name in ("source_id", "source_label"):
        definitions[name] = ColumnDefinition(name=name, dtype="category")
    warnings = [w for e in entries for w in e.dataset.warnings]
    if len(entries) > 1:
        warnings.append(Caveat(severity="info", code="multi_source", message=(
            "Multiple reports stay separate by source. Overlapping readings are not deduplicated or assumed independent.")))
        labels = [set(e.dataset.frame.building_name.unique()) for e in entries]
        if any(s != labels[0] for s in labels[1:]):
            suggestions = []
            for a in labels[0]:
                for other in labels[1:]:
                    suggestions += [f"{a} ≈ {v}" for v in get_close_matches(a, list(other - labels[0]), n=1, cutoff=.7)]
            note = "; possible matches (not merged): " + "; ".join(suggestions[:6]) if suggestions else ""
            warnings.append(Caveat(severity="warning", code="different_buildings", message=(
                "Building labels differ between reports. Names are NEVER merged automatically" + note)))
        periods = [set(e.dataset.months) for e in entries]
        if not set.intersection(*periods):
            warnings.append(Caveat(severity="warning", code="nonoverlapping_periods", message=(
                "The selected reports share no common months; a same-period source comparison is unavailable.")))
        observed_columns = [set(e.dataset.frame) for e in entries]
        optional = {"occupancy", "electricity_cost_inr", "tariff_inr_per_kwh"}
        for name in sorted(optional):
            if any(name in cols for cols in observed_columns) and not all(name in cols for cols in observed_columns):
                warnings.append(Caveat(severity="warning", code="partial_column", message=(
                    f"{name} exists in only some sources; missing measurements stay missing.")))
        tariffs = {e.dataset.custom_tariff_inr_per_kwh for e in entries}
        if len(tariffs) > 1:
            warnings.append(Caveat(severity="warning", code="different_rates", message=(
                "Source rate settings differ. Apply a single global custom INR/kWh rate for comparable estimated cost.")))
        if any("electricity_kwh" not in e.dataset.units or e.dataset.units.get("electricity_kwh") != "kWh" for e in entries):
            warnings.append(Caveat(severity="warning", code="different_units", message=(
                "Report electricity units differ. Fix each mapping before comparing; no conversion is assumed.")))
        duplicates = combined.duplicated(["building_name", "month"], keep=False)
        if duplicates.any():
            warnings.append(Caveat(severity="warning", code="overlapping_sources", message=(
                "Some building/month readings occur in more than one file. Combined sums count each source independently and may double-count the same electricity. Use Compare reports for like-for-like results.")))
    classes = {e.dataset.classification for e in entries}
    rates = {e.dataset.custom_tariff_inr_per_kwh for e in entries}
    return Dataset(combined, list(definitions.values()),
                   next(iter(classes)) if len(classes) == 1 else "Mixed · unverified",
                   warnings, next(iter(rates)) if len(rates) == 1 else None)


def replace_source(entries: list[SourceEntry], entry: SourceEntry) -> list[SourceEntry]:
    """Keep original source ordering stable (important for reference vs new)."""
    if any(x.source_id == entry.source_id for x in entries):
        return [entry if x.source_id == entry.source_id else x for x in entries]
    return [*entries, entry]


def remove_source(entries: list[SourceEntry], source_id: str) -> list[SourceEntry]:
    return [e for e in entries if e.source_id != source_id]


def reviewed_building_match(entry: SourceEntry, original: str, canonical: str) -> SourceEntry:
    """Apply ONLY an explicit, user-reviewed cross-source building alias.

    Keep raw_building_name, raw_cells, and original provenance intact. If the
    mapping would create duplicate observations inside this report, reject it.
    """
    if original not in set(entry.dataset.frame.building_name):
        raise DataError("The selected source building does not exist.")
    if not canonical.strip() or len(canonical) > 200:
        raise DataError("Select a valid canonical building label.")
    frame = entry.dataset.frame.copy()
    frame.loc[frame.building_name.eq(original), "building_name"] = canonical
    if frame.duplicated(["building_name", "month"]).any():
        raise DataError("This match would create duplicate building/month readings in one file.")
    revised = Dataset(frame, entry.dataset.columns, entry.dataset.classification,
                      list(entry.dataset.warnings), entry.dataset.custom_tariff_inr_per_kwh)
    return SourceEntry(entry.source_id, entry.filename, entry.label, revised)
