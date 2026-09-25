"""Features promised by the base install must work without Arrow or Dask."""

import pandas as pd
import polars as pl

import pyspainmobility.mobility.mobility as mobility_module
from pyspainmobility import (
    Mobility,
    aggregate_network,
    build_network,
    build_temporal_network,
)


def test_polars_can_return_pandas_without_optional_arrow(monkeypatch):
    monkeypatch.setattr(mobility_module, "pa", None)
    result = Mobility._polars_to_pandas(
        pl.DataFrame({"date": ["2024-01-01"], "n_trips": [2.5]})
    )
    assert isinstance(result, pd.DataFrame)
    assert result.to_dict("records") == [{"date": "2024-01-01", "n_trips": 2.5}]


def test_network_accepts_simple_pandas_input_without_optional_arrow():
    network = build_network(
        pd.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [3.0]}
        )
    )
    assert network.total_weight == 3.0
    mapping = pd.DataFrame(
        {"source_id": ["A", "B"], "target_id": ["X", "Y"]}
    )
    assert aggregate_network(network, mapping).total_weight == 3.0

    temporal = build_temporal_network(
        pd.DataFrame(
            {
                "date": ["2024-01-01"],
                "id_origin": ["A"],
                "id_destination": ["B"],
                "n_trips": [3.0],
            }
        ),
        acquisition_manifest=pd.DataFrame(
            {
                "date": ["2024-01-01"],
                "status": ["available"],
                "parse_status": ["valid"],
            }
        ),
    )
    assert temporal.snapshot("2024-01-01").total_weight == 3.0
