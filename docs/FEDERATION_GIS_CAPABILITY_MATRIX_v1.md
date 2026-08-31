# Federation GIS Capability / Duplication Matrix v1

Frozen baseline: spiderweb-pr `533fdde554e11b486a4ddb7a3fbe8127ed3fa2b2`; moneysweep-pr `ffdc781bc2196fc5e35903573f3948137e18bb1b`; aguayluz-pr `30e83ae11f0d6be0bf71f6cf46d3c8ff8bc035c0`; skywatcher-pr `b7b153fc64988ad62873841a3a61b75eab7721dd`.

Authoritative boundaries: Spiderweb = cross-domain investigation/fusion GIS; MoneySweep = capital/contracts/ownership/project geography; AguaYLuz = water/power/environmental infrastructure; Skywatcher = aviation/airspace/terrain/4D trajectories.

Shared invariants: WGS84/CRS84 interchange; explicit projected CRS for computation; distinct logical/source-manifestation hashes; spatial proximity defaults to `CANDIDATE_NOT_IDENTITY`; repo-owned PostGIS planes; `federation-map-runtime/1.0`; `fedgeopack/1.0`; mandatory `federation-spatial-impact/1.0` reports.

Current deficits under this branch: MoneySweep no-fabrication point/flow materialization; Skywatcher geodesic meters replacing planar degrees as production proximity; AguaYLuz deterministic hydro-network/raster interfaces; Spiderweb typed auditable cross-domain spatial relations.

`FOUR-REPO GIS CERTIFIED` requires schema + geometry + tests + security + performance + federation + desktop + iOS gates; passing code tests alone is not certification.
