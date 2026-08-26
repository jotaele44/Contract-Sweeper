{
  "registry_version": "capital_control_golden_cases_v0_2",
  "bpop_eight_quarter_archive_basenames": [
    "01jun2024-31aug2024_form13f.zip",
    "01sep2024-30nov2024_form13f.zip",
    "01dec2024-28feb2025_form13f.zip",
    "01mar2025-31may2025_form13f.zip",
    "01jun2025-31aug2025_form13f.zip",
    "01sep2025-30nov2025_form13f.zip",
    "01dec2025-28feb2026_form13f.zip",
    "01mar2026-31may2026_form13f.zip"
  ],
  "issuers": [
    {
      "ticker": "BPOP",
      "name": "Popular, Inc.",
      "cik": "0000763901",
      "issuer_id": "ISSUER_SEC_CIK_0000763901",
      "cusip": "733174700",
      "binding_basis": "AUTHORITATIVE_SEC_CIK_CUSIP",
      "required_periods": [
        "2024-06-30",
        "2024-09-30",
        "2024-12-31",
        "2025-03-31",
        "2025-06-30",
        "2025-09-30",
        "2025-12-31",
        "2026-03-31"
      ],
      "role": "GOLDEN_HIGH_DENSITY"
    },
    {
      "ticker": "EVTC",
      "name": "EVERTEC, Inc.",
      "cik": "0001559865",
      "issuer_id": "ISSUER_SEC_CIK_0001559865",
      "cusip": "30040P103",
      "binding_basis": "AUTHORITATIVE_SEC_CIK_CUSIP",
      "role": "CROSS_SECTOR_REGRESSION",
      "forbidden_name_only_merge": [
        "EVRI",
        "EVERI HOLDINGS"
      ]
    },
    {
      "ticker": "OFG",
      "name": "OFG Bancorp",
      "cik": "0001030469",
      "issuer_id": "ISSUER_SEC_CIK_0001030469",
      "cusip": "67103X102",
      "binding_basis": "AUTHORITATIVE_SEC_CIK_CUSIP",
      "role": "RAW_NORMALIZED_REGRESSION",
      "raw_address_fixture": "254 MU?OZ RIVERA AVENUE",
      "normalized_address_fixture": "254 Muñoz Rivera Avenue"
    }
  ],
  "identity_regressions": [
    {
      "regression_id": "BPOP_VANGUARD_DISAGGREGATION",
      "rule": "Distinct SEC reporting manager CIKs remain distinct legal-holder identities; investor-family rollup requires independent binding evidence."
    },
    {
      "regression_id": "EVTC_NOT_EVRI",
      "rule": "EVERTEC/EVTC cannot be merged with Everi/EVRI by name similarity, ticker similarity, proximity, or source absence."
    },
    {
      "regression_id": "OFG_RAW_NORMALIZED_SEPARATION",
      "rule": "Preserve raw address manifestation exactly; normalized address is a separate field and never identity proof by itself."
    }
  ]
}
