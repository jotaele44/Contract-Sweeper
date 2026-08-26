{
  "extension_id": "capital_control_sec13f_v0_2",
  "sources": [
    {
      "source_id": "sec_13f_bulk_freeze",
      "family": "capital_control",
      "required": false,
      "authentication": "none",
      "source_url": "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets",
      "producer_script": "scripts/download_sec_13f_bulk.py",
      "expected_outputs": [
        "data/manifests/capital_control/sec13f_freeze_manifest.json"
      ],
      "update_cadence": "quarterly",
      "validation_threshold": {
        "min_rows": 1
      },
      "notes": "Authoritative SEC Form 13F bulk archive discovery and byte freeze. Existing immutable snapshots are reused unless the operator explicitly requests refresh."
    },
    {
      "source_id": "sec_13f_capital_control",
      "family": "capital_control",
      "required": false,
      "authentication": "none",
      "source_url": "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets",
      "producer_script": "scripts/build_sec_13f_capital_control.py",
      "expected_outputs": [
        "data/staging/processed/capital_control/sec13f_holdings.csv",
        "data/staging/processed/capital_control/sec13f_investors.csv",
        "data/manifests/capital_control/sec13f_build_receipt.json",
        "data/manifests/capital_control/sec13f_bpop_certification.json"
      ],
      "update_cadence": "quarterly",
      "validation_threshold": {
        "min_rows": 1
      },
      "notes": "Strict CUSIP-bounded SEC 13F canonicalization with amendment adjudication, supersession preservation, BPOP golden-case certification, and materialized exact-CUSIP entity querying."
    }
  ]
}
