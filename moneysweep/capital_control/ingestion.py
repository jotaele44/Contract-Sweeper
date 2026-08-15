from __future__ import annotations

from dataclasses import dataclass

from .models import HoldingObservation, SourceManifest
from .source_adapter import SourceAdapter, stable_observation_fingerprint
from .validation import ValidationError, validate_holding_observation, validate_source_manifest


@dataclass(frozen=True)
class IngestionResult:
    manifest: SourceManifest
    observations: tuple[HoldingObservation, ...]
    input_count: int
    retained_count: int
    fingerprints: tuple[str, ...]


def ingest(adapter: SourceAdapter) -> IngestionResult:
    """Strict canonical ingestion with row conservation and source binding."""
    manifest = validate_source_manifest(adapter.source_manifest())
    raw_rows = tuple(adapter.iter_records())

    if manifest.record_count is not None and manifest.record_count != len(raw_rows):
        raise ValidationError(
            f"source record count mismatch: manifest={manifest.record_count} actual={len(raw_rows)}"
        )

    observations: list[HoldingObservation] = []
    fingerprints: list[str] = []
    source_record_ids: set[str] = set()
    observation_ids: set[str] = set()

    for index, raw_row in enumerate(raw_rows):
        observation = validate_holding_observation(raw_row)
        if observation.source_id != manifest.source_id:
            raise ValidationError(
                f"row {index} source_id does not match manifest source_id"
            )
        if observation.identity_status == "SUPERSEDED":
            raise ValidationError("SUPERSEDED identity status is derived, not an ingestion input")
        if observation.amendment_status == "SUPERSEDED":
            raise ValidationError("SUPERSEDED amendment status is derived, not an ingestion input")
        if observation.source_record_id in source_record_ids:
            raise ValidationError("duplicate source_record_id within source manifestation")
        if observation.observation_id in observation_ids:
            raise ValidationError("duplicate observation_id within source manifestation")

        source_record_ids.add(observation.source_record_id)
        observation_ids.add(observation.observation_id)
        observations.append(observation)
        fingerprints.append(stable_observation_fingerprint(raw_row))

    if len(observations) != len(raw_rows):
        raise AssertionError("row conservation invariant violated")

    return IngestionResult(
        manifest=manifest,
        observations=tuple(observations),
        input_count=len(raw_rows),
        retained_count=len(observations),
        fingerprints=tuple(fingerprints),
    )
