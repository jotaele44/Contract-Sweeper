from moneysweep.capital_control.identity import IdentityCandidate, resolve_identity_candidates


def test_name_like_discovery_does_not_become_identity() -> None:
    result = resolve_identity_candidates([
        IdentityCandidate("INV_parent", "HEURISTIC_DISCOVERY_ONLY", "same brand")
    ])
    assert result.status == "CANDIDATE_NOT_IDENTITY"
    assert result.selected_id is None


def test_tied_top_binding_evidence_fails_closed_and_preserves_candidates() -> None:
    candidates = [
        IdentityCandidate("INV_a", "AUTHORITATIVE_BINDING", "registry A"),
        IdentityCandidate("INV_b", "AUTHORITATIVE_BINDING", "registry B"),
    ]
    result = resolve_identity_candidates(candidates)
    assert result.status == "UNRESOLVED"
    assert result.selected_id is None
    assert result.candidates == tuple(candidates)


def test_stable_id_wins_over_lower_evidence() -> None:
    result = resolve_identity_candidates([
        IdentityCandidate("INV_a", "AUTHORITATIVE_BINDING", "filing"),
        IdentityCandidate("INV_b", "STABLE_ID", "stable registry id"),
    ])
    assert result.status == "PASS"
    assert result.selected_id == "INV_b"
