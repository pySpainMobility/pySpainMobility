import json
import pickle
import numpy as np
import pandas as pd
import polars as pl
import pytest
from dataclasses import replace
from scipy.sparse import csr_array

from pyspainmobility import (
    CommunityPartition,
    Mobility,
    NetworkSpec,
    NodeIndex,
    aggregate_network,
    aggregate_od_network,
    build_network,
    build_temporal_network,
    compare_networks,
    destination_similarity,
    edge_changes,
    node_strengths,
    symmetrize_network,
)
from pyspainmobility.network.integrations import (
    run_infomap,
    to_infomap,
    to_networkx,
)
from pyspainmobility.network.integrations.infomap import _network_fingerprint
from pyspainmobility.network.model import SparseMobilityNetwork


def test_build_network_aggregates_social_and_temporal_rows_with_stable_nodes():
    od = pl.DataFrame(
        {
            "id_origin": ["01002", "01001", "01001", "01003"],
            "id_destination": ["01001", "01002", "01002", "01002"],
            "n_trips": [4.0, 1.25, 2.75, 3.0],
            "age": ["25-44", "18-24", "45-64", None],
        }
    )

    network = build_network(od)

    assert network.node_ids.tolist() == ["01001", "01002", "01003"]
    assert network.number_of_nodes == 3
    assert network.number_of_edges == 3
    assert network.total_weight == pytest.approx(11.0)
    assert network.adjacency.toarray().tolist() == [
        [0.0, 4.0, 0.0],
        [4.0, 0.0, 0.0],
        [0.0, 3.0, 0.0],
    ]
    audit = network.audit()
    assert {key: audit[key] for key in (
        "weight", "directed", "aggregation", "self_loops", "node_universe",
        "input_edge_count", "represented_edge_count", "input_weight",
        "represented_weight", "dropped_self_loop_weight", "number_of_nodes",
        "number_of_edges", "matrix_weight",
    )} == {
        "weight": "n_trips", "directed": True, "aggregation": "sum",
        "self_loops": "keep", "node_universe": "observed",
        "input_edge_count": 3, "represented_edge_count": 3,
        "input_weight": 11.0, "represented_weight": 11.0,
        "dropped_self_loop_weight": 0.0, "number_of_nodes": 3,
        "number_of_edges": 3, "matrix_weight": 11.0,
    }
    assert audit["provenance"]["construction"]["represented_weight"] == 11.0
    assert network.to_edge_table().to_dicts() == [
        {"id_origin": "01001", "id_destination": "01002", "weight": 4.0},
        {"id_origin": "01002", "id_destination": "01001", "weight": 4.0},
        {"id_origin": "01003", "id_destination": "01002", "weight": 3.0},
    ]


def test_build_network_keeps_provided_node_order_and_isolates(tmp_path):
    od = pl.DataFrame(
        {
            "id_origin": ["B", "A"],
            "id_destination": ["A", "B"],
            "n_trips": [2.0, 5.0],
        }
    )
    path = tmp_path / "od.parquet"
    od.write_parquet(path)

    network = build_network(path, node_ids=["C", "B", "A", "D"])

    assert network.node_ids.tolist() == ["C", "B", "A", "D"]
    assert network.node_positions() == {"C": 0, "B": 1, "A": 2, "D": 3}
    assert network.adjacency.toarray().tolist() == [
        [0.0, 0.0, 0.0, 0.0],
        [0.0, 0.0, 2.0, 0.0],
        [0.0, 5.0, 0.0, 0.0],
        [0.0, 0.0, 0.0, 0.0],
    ]
    assert network.metadata.node_universe == "provided"


def test_build_network_accounts_for_dropped_self_loops_without_dropping_nodes():
    od = pl.DataFrame(
        {
            "id_origin": ["A", "A", "B"],
            "id_destination": ["A", "B", "B"],
            "n_trips": [7.0, 5.0, 3.0],
        }
    )

    network = build_network(od, spec=NetworkSpec(self_loops="drop"))

    assert network.node_ids.tolist() == ["A", "B"]
    assert network.number_of_edges == 1
    assert network.total_weight == pytest.approx(5.0)
    assert network.metadata.input_weight == pytest.approx(15.0)
    assert network.metadata.represented_weight == pytest.approx(5.0)
    assert network.metadata.dropped_self_loop_weight == pytest.approx(10.0)


def test_dropping_only_self_loops_retains_observed_nodes():
    network = build_network(
        pl.DataFrame(
            {
                "id_origin": ["B", "A"],
                "id_destination": ["B", "A"],
                "n_trips": [2, 3],
            }
        ),
        spec=NetworkSpec(self_loops="drop"),
    )

    assert network.node_ids.tolist() == ["A", "B"]
    assert network.number_of_edges == 0
    assert network.total_weight == 0.0


@pytest.mark.parametrize(
    "od",
    [
        pl.DataFrame({"id_origin": ["A"], "id_destination": ["B"], "n_trips": [-1]}),
        pl.DataFrame({"id_origin": ["A"], "id_destination": ["B"], "n_trips": [None]}),
        pl.DataFrame({"id_origin": [""], "id_destination": ["B"], "n_trips": [1]}),
    ],
)
def test_build_network_rejects_invalid_flow_rows(od):
    with pytest.raises(ValueError, match="OD rows"):
        build_network(od)


def test_build_network_rejects_incomplete_node_universe():
    od = pl.DataFrame(
        {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [1.0]}
    )
    with pytest.raises(ValueError, match="does not cover"):
        build_network(od, node_ids=["A"])


def test_networkx_adapter_uses_zone_ids_and_preserves_weights():
    pytest.importorskip("networkx")
    network = build_network(
        pl.DataFrame(
            {"id_origin": ["B"], "id_destination": ["A"], "n_trips": [2.5]}
        ),
        node_ids=["A", "B", "C"],
    )

    graph = to_networkx(network)

    assert set(graph.nodes) == {"A", "B", "C"}
    assert graph["B"]["A"]["weight"] == pytest.approx(2.5)
    assert graph.graph["pyspainmobility_audit"]["number_of_nodes"] == 3
    assert np.isclose(sum(data["weight"] for _, _, data in graph.edges(data=True)), 2.5)


def test_infomap_adapter_runs_from_csr_and_preserves_node_contract():
    pytest.importorskip("infomap")
    network = build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "B", "A", "C", "D", "E", "D", "F"],
                "id_destination": ["B", "A", "C", "A", "E", "D", "F", "D"],
                "n_trips": [8.0, 8.0, 0.1, 0.1, 8.0, 8.0, 0.1, 0.1],
            }
        ),
        node_index=NodeIndex(
            ["A", "B", "C", "D", "E", "F"], "municipality", "2026"
        ),
    )

    infomap_network = to_infomap(network)
    partition = run_infomap(network, seed=123, num_trials=3, two_level=True)

    assert infomap_network.num_nodes == network.number_of_nodes
    assert isinstance(partition, CommunityPartition)
    assert set(partition.assignments) == set(network.node_ids)
    assert set(partition.hierarchy) == set(network.node_ids)
    assert partition.module_of("A") == partition.module_of("B")
    assert partition.module_of("D") == partition.module_of("E")
    assert partition.module_of("A") != partition.module_of("D")
    assert partition.parameters["seed"] == 123
    assert partition.parameters["two_level"] is True
    assert partition.algorithm == "infomap"
    assert len(partition.network_fingerprint) == 64
    assert partition.codelength is not None
    assert partition.num_top_modules == 2
    restored = pickle.loads(pickle.dumps(partition))
    assert restored.assignments == partition.assignments
    assert restored.algorithm_metrics == partition.algorithm_metrics


def test_infomap_adapter_rejects_a_direction_override():
    network = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [1.0]}
        )
    )

    with pytest.raises(ValueError, match="directed cannot be overridden"):
        run_infomap(network, directed=False)


def test_symmetrize_network_makes_undirected_rules_and_accounting_explicit():
    directed = build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "B", "A", "C"],
                "id_destination": ["B", "A", "C", "C"],
                "n_trips": [2.0, 3.0, 5.0, 4.0],
            }
        ),
        node_ids=["A", "B", "C"],
    )

    summed = symmetrize_network(directed, method="sum")
    mean = symmetrize_network(directed, method="mean")
    maximum = symmetrize_network(directed, method="max")
    mutual = symmetrize_network(directed, method="mutual")

    assert summed.metadata.directed is False
    assert summed.adjacency.toarray().tolist() == [
        [0.0, 5.0, 5.0],
        [5.0, 0.0, 0.0],
        [5.0, 0.0, 4.0],
    ]
    assert summed.number_of_edges == 3
    assert summed.total_weight == pytest.approx(14.0)
    assert summed.audit()["stored_symmetric_matrix_weight"] == pytest.approx(24.0)
    assert summed.to_edge_table().to_dicts() == [
        {"id_origin": "A", "id_destination": "B", "weight": 5.0},
        {"id_origin": "A", "id_destination": "C", "weight": 5.0},
        {"id_origin": "C", "id_destination": "C", "weight": 4.0},
    ]
    assert mean.total_weight == pytest.approx(9.0)
    assert maximum.total_weight == pytest.approx(12.0)
    assert mutual.total_weight == pytest.approx(6.0)
    assert mutual.to_edge_table().to_dicts() == [
        {"id_origin": "A", "id_destination": "B", "weight": 2.0},
        {"id_origin": "C", "id_destination": "C", "weight": 4.0},
    ]
    assert node_strengths(summed).get_column("total_strength").to_list() == [
        10.0,
        5.0,
        9.0,
    ]
    with pytest.raises(ValueError, match="requires a directed"):
        symmetrize_network(summed)
    with pytest.raises(ValueError, match="directed and undirected"):
        compare_networks(directed, summed)


def test_networkx_adapter_preserves_an_undirected_network_contract():
    pytest.importorskip("networkx")
    directed = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [2.0]}
        )
    )

    graph = to_networkx(symmetrize_network(directed))

    assert graph.is_directed() is False
    assert graph["A"]["B"]["weight"] == pytest.approx(2.0)


def test_sparse_network_metrics_align_node_indexes_and_report_edge_changes():
    left = build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "A", "B"],
                "id_destination": ["B", "C", "A"],
                "n_trips": [2.0, 1.0, 3.0],
            }
        ),
        node_index=NodeIndex(["A", "B", "C"], "municipality", "2026"),
    )
    right = build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "B", "C"],
                "id_destination": ["B", "A", "A"],
                "n_trips": [1.0, 3.0, 2.0],
            }
        ),
        node_index=NodeIndex(["C", "B", "A"], "municipality", "2026"),
    )

    strengths = node_strengths(left)
    comparison = compare_networks(left, right, left_label="before", right_label="after")
    similarity = destination_similarity(left, right)
    changes = edge_changes(left, right)

    assert strengths.to_dicts() == [
        {"node_id": "A", "out_strength": 3.0, "in_strength": 3.0, "total_strength": 6.0},
        {"node_id": "B", "out_strength": 3.0, "in_strength": 2.0, "total_strength": 5.0},
        {"node_id": "C", "out_strength": 0.0, "in_strength": 1.0, "total_strength": 1.0},
    ]
    assert comparison.left_label == "before"
    assert comparison.right_label == "after"
    assert comparison.shared_edge_count == 2
    assert comparison.added_edge_count == 1
    assert comparison.removed_edge_count == 1
    assert comparison.edge_jaccard == pytest.approx(0.5)
    assert comparison.weighted_jaccard == pytest.approx(0.5)
    assert comparison.cosine_similarity == pytest.approx(11.0 / 14.0)
    assert comparison.flow_increase == pytest.approx(2.0)
    assert comparison.flow_decrease == pytest.approx(2.0)
    assert comparison.edge_turnover == pytest.approx(0.5)
    assert comparison.audit()["node_index"] == {
        "node_count": 3,
        "zoning_id": "municipality",
        "zoning_version": "2026",
    }
    assert similarity.to_dicts() == [
        {"node_id": "A", "destination_cosine_similarity": pytest.approx(2 / np.sqrt(5))},
        {"node_id": "B", "destination_cosine_similarity": 1.0},
        {"node_id": "C", "destination_cosine_similarity": 0.0},
    ]
    assert changes.to_dicts() == [
        {
            "id_origin": "A",
            "id_destination": "B",
            "left_weight": 2.0,
            "right_weight": 1.0,
            "delta_weight": -1.0,
            "change": "decreased",
        },
        {
            "id_origin": "A",
            "id_destination": "C",
            "left_weight": 1.0,
            "right_weight": 0.0,
            "delta_weight": -1.0,
            "change": "removed",
        },
        {
            "id_origin": "B",
            "id_destination": "A",
            "left_weight": 3.0,
            "right_weight": 3.0,
            "delta_weight": 0.0,
            "change": "unchanged",
        },
        {
            "id_origin": "C",
            "id_destination": "A",
            "left_weight": 0.0,
            "right_weight": 2.0,
            "delta_weight": 2.0,
            "change": "added",
        },
    ]


def test_temporal_network_uses_source_manifest_for_missing_and_empty_days():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-03", "2024-01-03"],
            "id_origin": ["A", "B", "A"],
            "id_destination": ["B", "A", "B"],
            "n_trips": [1.0, 2.0, 3.0],
        }
    )
    temporal = build_temporal_network(
        od,
        requested_dates=["2024-01-01", "2024-01-02", "2024-01-03"],
        observed_dates=["2024-01-01", "2024-01-02", "2024-01-03"],
    )

    assert temporal.node_ids.tolist() == ["A", "B"]
    assert temporal.coverage.missing_source_dates == ()
    assert temporal.coverage.empty_observed_dates == ("2024-01-02",)
    assert temporal.audit()["cached_snapshot_count"] == 0

    first = temporal.snapshot("2024-01-01")
    assert first is temporal.snapshot("2024-01-01")
    assert first.total_weight == pytest.approx(1.0)
    empty_snapshot = temporal.snapshot("2024-01-02")
    assert empty_snapshot.total_weight == 0.0
    assert empty_snapshot.audit()["provenance"]["temporal"]["date"] == "2024-01-02"
    assert temporal.snapshot("2024-01-03").total_weight == pytest.approx(5.0)
    assert [label for label, _ in temporal.snapshots()] == ["2024-01-01", "2024-01-03"]
    assert [label for label, _ in temporal.snapshots(include_empty=True)] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]
    comparison = temporal.compare_snapshots("2024-01-01", "2024-01-03")
    assert comparison.left_label == "2024-01-01"
    assert comparison.right_label == "2024-01-03"
    assert comparison.edge_jaccard == pytest.approx(0.5)
    assert temporal.snapshot_strengths("2024-01-01").get_column(
        "out_strength"
    ).to_list() == [1.0, 0.0]
    assert temporal.destination_stability(
        "2024-01-01", "2024-01-03"
    ).get_column("destination_cosine_similarity").to_list() == [1.0, 0.0]
    assert temporal.snapshot_edge_changes(
        "2024-01-01", "2024-01-03"
    ).get_column("change").to_list() == ["increased", "added"]


def test_temporal_network_uses_a_bounded_lru_snapshot_cache():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "id_origin": ["A", "A", "A"],
            "id_destination": ["B", "B", "B"],
            "n_trips": [1.0, 2.0, 3.0],
        }
    )
    temporal = build_temporal_network(od, max_cached_snapshots=2)

    first = temporal.snapshot("2024-01-01")
    second = temporal.snapshot("2024-01-02")
    assert first is temporal.snapshot("2024-01-01")
    temporal.snapshot("2024-01-03")

    assert temporal.audit()["cached_snapshot_dates"] == [
        "2024-01-01",
        "2024-01-03",
    ]
    assert second is not temporal.snapshot("2024-01-02")
    assert temporal.audit()["cached_snapshot_count"] == 2
    restored = pickle.loads(pickle.dumps(temporal))
    assert restored.audit()["cached_snapshot_count"] == 2
    assert restored.snapshot("2024-01-02").total_weight == 2.0
    temporal.clear_cache()
    assert temporal.audit()["cached_snapshot_count"] == 0


def test_temporal_network_scans_hive_partitioned_parquet_by_date(tmp_path):
    rows_by_date = {
        "2024-01-01": ("A", "B", 1.0),
        "2024-01-02": ("B", "A", 2.0),
    }
    for day, (origin, destination, weight) in rows_by_date.items():
        partition = tmp_path / ("date=" + day)
        partition.mkdir()
        pl.DataFrame(
            {
                "id_origin": [origin],
                "id_destination": [destination],
                "n_trips": [weight],
            }
        ).write_parquet(partition / "part-0.parquet")

    temporal = build_temporal_network(
        tmp_path,
        requested_dates=["2024-01-01", "2024-01-02"],
        max_cached_snapshots=1,
    )

    assert temporal.coverage.data_dates == ("2024-01-01", "2024-01-02")
    assert temporal.snapshot("2024-01-01").total_weight == pytest.approx(1.0)
    assert temporal.snapshot("2024-01-02").total_weight == pytest.approx(2.0)
    assert temporal.audit()["cached_snapshot_dates"] == ["2024-01-02"]


@pytest.mark.parametrize("cache_size", [-1, True, 1.5])
def test_temporal_network_rejects_invalid_cache_capacity(cache_size):
    od = pl.DataFrame(
        {"date": ["2024-01-01"], "id_origin": ["A"], "id_destination": ["B"], "n_trips": [1.0]}
    )

    with pytest.raises(ValueError, match="max_cached_snapshots"):
        build_temporal_network(od, max_cached_snapshots=cache_size)


def test_temporal_network_does_not_call_unobserved_dates_zero_without_manifest():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01"],
            "id_origin": ["A"],
            "id_destination": ["B"],
            "n_trips": [1.0],
        }
    )
    temporal = build_temporal_network(
        od,
        requested_dates=["2024-01-01", "2024-01-02"],
    )

    assert temporal.coverage.missing_source_dates == ()
    assert temporal.coverage.empty_observed_dates == ()
    assert temporal.coverage.unresolved_requested_dates == ("2024-01-02",)
    with pytest.raises(ValueError, match="not an observed date"):
        temporal.snapshot("2024-01-02")


def test_temporal_network_reports_missing_source_and_validates_node_universe():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01"],
            "id_origin": ["A"],
            "id_destination": ["B"],
            "n_trips": [1.0],
        }
    )
    temporal = build_temporal_network(
        od,
        requested_dates=["2024-01-01", "2024-01-02"],
        observed_dates=["2024-01-01"],
        node_ids=["A", "B", "C"],
    )

    assert temporal.coverage.missing_source_dates == ("2024-01-02",)
    with pytest.raises(ValueError, match="missing from the observed source manifest"):
        temporal.snapshot("2024-01-02")
    with pytest.raises(ValueError, match="does not cover"):
        build_temporal_network(od, node_ids=["A"])


def test_temporal_network_rejects_data_outside_an_explicit_source_manifest():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "id_origin": ["A", "A"],
            "id_destination": ["B", "B"],
            "n_trips": [1.0, 1.0],
        }
    )

    with pytest.raises(ValueError, match="rows for dates not observed"):
        build_temporal_network(od, observed_dates=["2024-01-01"])


def test_temporal_network_consumes_acquisition_manifest_before_od_filtering():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01"],
            "id_origin": ["A"],
            "id_destination": ["B"],
            "n_trips": [1.0],
        }
    )
    manifest = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "status": ["available", "failed", "available"],
            "coverage": ["unverified", "unknown", "unverified"],
        }
    )

    temporal = build_temporal_network(od, acquisition_manifest=manifest)

    assert temporal.coverage.missing_source_dates == ("2024-01-02",)
    assert temporal.coverage.empty_observed_dates == ("2024-01-03",)
    assert temporal.snapshot("2024-01-03").total_weight == 0.0
    with pytest.raises(ValueError, match="missing from the observed source manifest"):
        temporal.snapshot("2024-01-02")


def test_temporal_sum_and_mean_use_all_observed_days_as_denominator():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-03"],
            "id_origin": ["A", "B"],
            "id_destination": ["B", "A"],
            "n_trips": [4.0, 2.0],
        }
    )
    manifest = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "status": ["available", "available", "available"],
        }
    )
    temporal = build_temporal_network(od, acquisition_manifest=manifest)

    summed = temporal.sum_network()
    mean = temporal.mean_per_observed_day()

    assert summed.total_weight == pytest.approx(6.0)
    assert summed.adjacency.toarray().tolist() == [[0.0, 4.0], [2.0, 0.0]]
    assert mean.total_weight == pytest.approx(2.0)
    assert mean.adjacency.toarray().tolist() == [
        [0.0, pytest.approx(4.0 / 3.0)],
        [pytest.approx(2.0 / 3.0), 0.0],
    ]
    assert mean.audit()["provenance"]["temporal"] == {
        "aggregation": "mean_per_observed_day",
        "observed_dates": ["2024-01-01", "2024-01-02", "2024-01-03"],
        "observed_day_count": 3,
        "source_manifest_provided": True,
    }


def test_temporal_mean_can_select_observed_days_but_rejects_missing_dates():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-03"],
            "id_origin": ["A", "B"],
            "id_destination": ["B", "A"],
            "n_trips": [4.0, 2.0],
        }
    )
    manifest = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "status": ["available", "failed", "available"],
        }
    )
    temporal = build_temporal_network(od, acquisition_manifest=manifest)

    mean = temporal.mean_per_observed_day(["2024-01-01", "2024-01-03"])

    assert mean.total_weight == pytest.approx(3.0)
    assert mean.adjacency.toarray().tolist() == [[0.0, 2.0], [1.0, 0.0]]
    with pytest.raises(ValueError, match="requires observed source dates"):
        temporal.mean_per_observed_day(["2024-01-02"])


def _fine_network_for_spatial_aggregation():
    return build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "B", "A", "C", "C"],
                "id_destination": ["B", "A", "C", "D", "C"],
                "n_trips": [2.0, 3.0, 4.0, 5.0, 7.0],
            }
        )
    )


def test_sparse_spatial_aggregation_preserves_flow_and_reports_internalized_flow():
    aggregated = aggregate_network(
        _fine_network_for_spatial_aggregation(),
        {"A": "X", "B": "X", "C": "Y", "D": "Y"},
    )

    assert aggregated.node_ids.tolist() == ["X", "Y"]
    assert aggregated.adjacency.toarray().tolist() == [[5.0, 4.0], [0.0, 12.0]]
    assert aggregated.total_weight == pytest.approx(21.0)
    spatial = aggregated.audit()["provenance"]["spatial"]
    assert spatial["method"] == "sparse_projection"
    assert spatial["source_self_loop_weight"] == pytest.approx(7.0)
    target_loop_key = "target_self_loop_weight_before_target_loop_policy"
    assert spatial[target_loop_key] == pytest.approx(17.0)
    assert spatial["internalized_weight"] == pytest.approx(10.0)
    assert spatial["dropped_target_self_loop_weight"] == 0.0


def test_sparse_spatial_aggregation_can_drop_reported_target_self_loops():
    aggregated = aggregate_network(
        _fine_network_for_spatial_aggregation(),
        {"A": "X", "B": "X", "C": "Y", "D": "Y"},
        target_node_ids=["Y", "X", "Z"],
        self_loops="drop",
    )

    assert aggregated.node_ids.tolist() == ["Y", "X", "Z"]
    assert aggregated.adjacency.toarray().tolist() == [
        [0.0, 0.0, 0.0],
        [4.0, 0.0, 0.0],
        [0.0, 0.0, 0.0],
    ]
    assert aggregated.total_weight == pytest.approx(4.0)
    assert aggregated.metadata.dropped_self_loop_weight == pytest.approx(17.0)
    assert aggregated.audit()["provenance"]["spatial"][
        "dropped_target_self_loop_weight"
    ] == pytest.approx(17.0)


def test_od_spatial_aggregation_uses_polars_before_csr_and_matches_projection():
    od = pl.DataFrame(
        {
            "id_origin": ["A", "A", "B", "A", "C", "C"],
            "id_destination": ["B", "B", "A", "C", "D", "C"],
            "n_trips": [1.0, 1.0, 3.0, 4.0, 5.0, 7.0],
            "age": ["18-24", "25-44", "18-24", None, "65+", "65+"],
        }
    )
    mapping = pl.DataFrame(
        {"source_id": ["A", "B", "C", "D"], "target_id": ["X", "X", "Y", "Y"]}
    )

    aggregated = aggregate_od_network(od, mapping)

    assert aggregated.node_ids.tolist() == ["X", "Y"]
    assert aggregated.adjacency.toarray().tolist() == [[5.0, 4.0], [0.0, 12.0]]
    spatial = aggregated.audit()["provenance"]["spatial"]
    assert spatial["method"] == "od_polars"
    assert spatial["internalized_weight"] == pytest.approx(10.0)


def test_spatial_aggregation_rejects_incomplete_or_nonfunctional_mappings():
    network = _fine_network_for_spatial_aggregation()
    with pytest.raises(ValueError, match="does not cover"):
        aggregate_network(network, {"A": "X"})
    with pytest.raises(ValueError, match="map each source node once"):
        aggregate_network(
            network,
            pl.DataFrame(
                {
                    "source_id": ["A", "A", "B", "C", "D"],
                    "target_id": ["X", "X", "X", "Y", "Y"],
                }
            ),
        )


def test_node_index_aligns_matrix_order_and_checks_zoning_identity():
    municipal_v2 = NodeIndex(
        ["A", "B"], zoning_id="mitma_municipalities", zoning_version="v2"
    )
    reversed_municipal_v2 = NodeIndex(
        ["B", "A"], zoning_id="mitma_municipalities", zoning_version="v2"
    )
    network = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [2.0]}
        ),
        node_index=municipal_v2,
    )

    aligned = network.align_to(reversed_municipal_v2)

    assert aligned.node_index is reversed_municipal_v2
    assert aligned.node_ids.tolist() == ["B", "A"]
    assert aligned.adjacency.toarray().tolist() == [[0.0, 0.0], [2.0, 0.0]]
    assert aligned.audit()["node_index"] == {
        "node_count": 2,
        "zoning_id": "mitma_municipalities",
        "zoning_version": "v2",
    }
    with pytest.raises(ValueError, match="different zoning metadata"):
        network.align_to(NodeIndex(["B", "A"], zoning_id="mitma_districts"))


def test_node_index_is_propagated_to_temporal_and_spatial_networks():
    source_index = NodeIndex(["A", "B"], zoning_id="fine", zoning_version="1")
    target_index = NodeIndex(["X", "Y"], zoning_id="coarse", zoning_version="1")
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "id_origin": ["A", "B"],
            "id_destination": ["B", "A"],
            "n_trips": [1.0, 2.0],
        }
    )

    temporal = build_temporal_network(od, node_index=source_index)
    spatial = aggregate_network(
        temporal.snapshot("2024-01-01"),
        {"A": "X", "B": "Y"},
        target_node_index=target_index,
    )

    assert temporal.snapshot("2024-01-02").node_index is source_index
    assert spatial.node_index is target_index
    assert spatial.audit()["node_index"]["zoning_id"] == "coarse"


def test_node_index_rejects_conflicting_legacy_node_ids():
    index = NodeIndex(["A", "B"], zoning_id="mitma_municipalities")
    od = pl.DataFrame(
        {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [1.0]}
    )

    with pytest.raises(ValueError, match="either node_ids or node_index"):
        build_network(od, node_ids=["A", "B"], node_index=index)


@pytest.mark.parametrize(
    "date_values",
    [
        pd.to_datetime(["2024-01-01", "2024-01-02"]),
        pl.Series("date", ["2024-01-01", "2024-01-02"]).str.strptime(pl.Date),
        pl.Series("date", ["2024-01-01", "2024-01-02"]).str.strptime(pl.Datetime),
        pl.Series("date", ["2024-01-01 12:30:00", "2024-01-02T08:15:00Z"]),
    ],
)
def test_temporal_calendar_dates_keep_datetime_flows(date_values):
    rows = {
        "date": date_values,
        "id_origin": ["A", "A"],
        "id_destination": ["B", "B"],
        "n_trips": [10.0, 20.0],
    }
    od = pd.DataFrame(rows) if isinstance(date_values, pd.DatetimeIndex) else pl.DataFrame(rows)
    temporal = build_temporal_network(
        od,
        requested_dates=["2024-01-01", "2024-01-02"],
        observed_dates=["2024-01-01", "2024-01-02"],
        node_ids=["A", "B"],
    )

    assert temporal.coverage.data_dates == ("2024-01-01", "2024-01-02")
    assert temporal.snapshot(pd.Timestamp("2024-01-01")).total_weight == 10.0
    temporal.clear_cache()
    assert temporal.sum_network().total_weight == 30.0
    assert temporal.mean_per_observed_day().total_weight == 15.0
    assert temporal.audit()["cached_snapshot_count"] == 0


def test_temporal_rejects_malformed_date_instead_of_making_a_false_empty_day():
    od = pl.DataFrame(
        {
            "date": ["not-a-date"],
            "id_origin": ["A"],
            "id_destination": ["B"],
            "n_trips": [10.0],
        }
    )
    with pytest.raises(ValueError, match="invalid endpoint, weight, or date"):
        build_temporal_network(
            od,
            requested_dates=["2024-01-01"],
            observed_dates=["2024-01-01"],
            node_ids=["A", "B"],
        )


@pytest.mark.parametrize("method", ["sum", "mean", "max", "mutual"])
@pytest.mark.parametrize("target_loops", ["keep", "drop"])
def test_undirected_spatial_aggregation_counts_internalized_edges_once(
    method, target_loops
):
    od = pl.DataFrame(
        {
            "id_origin": ["A", "B", "A"],
            "id_destination": ["B", "A", "A"],
            "n_trips": [2.0, 3.0, 7.0],
        }
    )
    source = symmetrize_network(build_network(od), method=method)
    unchanged = aggregate_network(source, {"A": "X", "B": "Y"})
    merged = aggregate_network(
        source, {"A": "X", "B": "X"}, self_loops=target_loops
    )

    assert unchanged.total_weight == pytest.approx(source.total_weight)
    assert merged.total_weight == pytest.approx(
        source.total_weight if target_loops == "keep" else 0.0
    )
    assert merged.audit()["stored_symmetric_matrix_weight"] == pytest.approx(
        merged.total_weight
    )
    assert merged.number_of_edges == (1 if target_loops == "keep" else 0)


def test_spatial_pipelines_agree_after_source_loop_policy_and_keep_weight_name():
    od = pl.DataFrame(
        {
            "id_origin": ["A", "A", "B"],
            "id_destination": ["A", "B", "A"],
            "distance": [7.0, 3.0, 2.0],
        }
    )
    mapping = {"A": "X", "B": "Y"}
    spec = NetworkSpec(weight="distance", self_loops="drop")
    from_csr = aggregate_network(build_network(od, spec=spec), mapping)
    from_od = aggregate_od_network(od, mapping, spec=spec)

    assert from_csr.adjacency.toarray().tolist() == from_od.adjacency.toarray().tolist()
    assert from_od.total_weight == 5.0
    assert from_od.metadata.weight == "distance"
    assert from_od.audit()["provenance"]["spatial"]["dropped_source_self_loop_weight"] == 7.0


def test_spatial_od_and_csr_pipelines_agree_on_random_sparse_flows():
    rng = np.random.default_rng(29)
    nodes = [str(index) for index in range(6)]
    mapping = {node: "XYZ"[index % 3] for index, node in enumerate(nodes)}
    for _ in range(5):
        origin = rng.choice(nodes, size=35).tolist()
        destination = rng.choice(nodes, size=35).tolist()
        od = pl.DataFrame(
            {
                "id_origin": origin,
                "id_destination": destination,
                "n_trips": rng.integers(0, 12, size=35).astype(float),
            }
        )
        for source_loops in ("keep", "drop"):
            source = build_network(
                od, spec=NetworkSpec(self_loops=source_loops), node_ids=nodes
            )
            for target_loops in ("keep", "drop"):
                from_csr = aggregate_network(
                    source, mapping, self_loops=target_loops
                )
                from_od = aggregate_od_network(
                    od,
                    mapping,
                    spec=NetworkSpec(self_loops=source_loops),
                    target_node_ids=from_csr.node_ids,
                    self_loops=target_loops,
                )
                np.testing.assert_allclose(
                    from_csr.adjacency.toarray(), from_od.adjacency.toarray()
                )
                assert from_csr.total_weight == pytest.approx(from_od.total_weight)


def test_spatial_paths_keep_node_universe_when_every_source_loop_is_dropped():
    od = pl.DataFrame(
        {"id_origin": ["A"], "id_destination": ["A"], "n_trips": [7.0]}
    )
    spec = NetworkSpec(self_loops="drop")
    from_csr = aggregate_network(build_network(od, spec=spec), {"A": "X"})
    from_od = aggregate_od_network(od, {"A": "X"}, spec=spec)
    assert from_csr.node_ids.tolist() == from_od.node_ids.tolist() == ["X"]
    assert from_csr.total_weight == from_od.total_weight == 0.0


def test_spatial_aggregation_preserves_temporal_mean_and_history():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "id_origin": ["A", "B"],
            "id_destination": ["B", "A"],
            "n_trips": [4.0, 2.0],
        }
    )
    temporal = build_temporal_network(od)
    assert temporal.snapshot("2024-01-01").audit()["provenance"]["temporal"]["date"] == "2024-01-01"
    mean = temporal.mean_per_observed_day()
    coarse = aggregate_network(mean, {"A": "X", "B": "X"})
    repeated = aggregate_network(coarse, {"X": "Z"})

    assert repeated.metadata.aggregation == "mean_per_observed_day"
    assert repeated.metadata.weight_normalization == "per_observed_day"
    assert repeated.total_weight == 3.0
    assert repeated.audit()["provenance"]["temporal"]["observed_day_count"] == 2
    assert [step["kind"] for step in repeated.audit()["provenance"]["history"]] == [
        "construction", "temporal", "spatial", "spatial"
    ]
    with pytest.raises(TypeError):
        repeated.provenance["temporal"]["observed_day_count"] = 99
    assert symmetrize_network(mean).metadata.weight_normalization == "per_observed_day"
    with pytest.raises(ValueError, match="different weight normalization"):
        compare_networks(mean, temporal.sum_network())


def test_global_cosine_distinguishes_one_empty_network_from_two_empty_networks():
    od = pl.DataFrame(
        {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [2.0]}
    )
    active = build_network(od)
    empty = build_network(od.with_columns(pl.lit(0.0).alias("n_trips")), node_index=active.node_index)

    assert compare_networks(active, empty).cosine_similarity == 0.0
    assert compare_networks(empty, active).cosine_similarity == 0.0
    assert compare_networks(empty, empty).cosine_similarity == 1.0


def test_network_comparison_rejects_different_weight_units():
    od = pl.DataFrame(
        {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [2.0]}
    )
    trips = build_network(od)
    distance = build_network(
        od.rename({"n_trips": "distance"}), spec=NetworkSpec(weight="distance")
    )
    with pytest.raises(ValueError, match="different weight fields"):
        compare_networks(trips, distance)


def test_canonical_network_validates_weights_symmetry_and_read_only_storage():
    network = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [2.0]}
        )
    )
    with pytest.raises(ValueError, match="finite and non-negative"):
        SparseMobilityNetwork(
            csr_array([[0.0, float("nan")], [0.0, 0.0]]),
            network.node_ids,
            network.metadata,
        )
    with pytest.raises(ValueError, match="symmetric"):
        SparseMobilityNetwork(
            network.adjacency,
            network.node_ids,
            replace(network.metadata, directed=False),
        )
    with pytest.raises(ValueError, match="represented weight"):
        SparseMobilityNetwork(
            network.adjacency,
            network.node_ids,
            replace(network.metadata, represented_weight=3.0),
        )
    with pytest.raises(AttributeError, match="read-only"):
        network.adjacency.data = network.adjacency.data * 2
    with pytest.raises(ValueError):
        network.adjacency.data.setflags(write=True)
    with pytest.raises(ValueError):
        network.node_ids.setflags(write=True)
    assert network.total_weight == network.metadata.represented_weight
    restored = pickle.loads(pickle.dumps(network))
    assert restored.total_weight == network.total_weight
    assert restored.adjacency.data.flags.writeable is False
    assert pickle.loads(pickle.dumps(network.adjacency)).data.flags.writeable is False
    with pytest.raises(ValueError, match="finite"):
        build_network(
            pl.DataFrame(
                {
                    "id_origin": ["A", "A"],
                    "id_destination": ["B", "B"],
                    "n_trips": [1e308, 1e308],
                }
            )
        )


def test_undirected_audits_are_json_serialisable_after_spatial_projection():
    directed = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [2.0]}
        )
    )
    undirected = symmetrize_network(directed)
    spatial = aggregate_network(undirected, {"A": "X", "B": "X"})
    for network in (undirected, spatial):
        restored = json.loads(json.dumps(network.audit()))
        assert restored["number_of_edges"] == 1
        assert restored["matrix_weight"] == 2.0
    json.dumps(compare_networks(undirected, undirected).audit())


def test_infomap_fingerprint_includes_direction_and_rejects_flow_override():
    directed = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [2.0]}
        )
    )
    undirected = symmetrize_network(directed)
    same_matrix_directed = SparseMobilityNetwork(
        undirected.adjacency,
        undirected.node_ids,
        replace(
            undirected.metadata,
            directed=True,
            represented_edge_count=undirected.adjacency.nnz,
            represented_weight=float(undirected.adjacency.sum()),
        ),
    )
    assert _network_fingerprint(undirected) != _network_fingerprint(same_matrix_directed)
    with pytest.raises(ValueError, match="flow-model options"):
        run_infomap(directed, flow_model="undirected")


def test_mobility_manifest_excludes_invalid_parsed_day_from_temporal_mean(tmp_path):
    header = "fecha|periodo|origen|destino|viajes|viajes_km\n"
    valid_path = tmp_path / "20240101_Viajes.csv"
    invalid_path = tmp_path / "20240102_Viajes.csv"
    empty_path = tmp_path / "20240103_Viajes.csv"
    valid_path.write_text(header + "20240101|1|A|B|10|20\n")
    invalid_path.write_text(header + "20240102|1|A|B|bad|20\n")
    empty_path.write_text(header)
    files = [str(valid_path), str(invalid_path), str(empty_path)]
    mobility = object.__new__(Mobility)
    mobility._acquisition_manifests = {}
    mobility._set_acquisition_manifest(
        "Viajes",
        [
            [day, "Viajes", "available", "unverified", path, None]
            for day, path in zip(
                ["2024-01-01", "2024-01-02", "2024-01-03"], files
            )
        ],
    )
    with pytest.warns(RuntimeWarning, match="OD source parsing failed"):
        mobility._finalize_od_manifest("Viajes", files, processed_success=True)
    manifest = mobility.get_acquisition_manifest("Viajes")
    assert manifest["parse_status"].tolist() == ["valid", "failed", "empty"]

    od = pl.DataFrame(
        {
            "date": ["2024-01-01"],
            "id_origin": ["A"],
            "id_destination": ["B"],
            "n_trips": [10.0],
        }
    )
    temporal = build_temporal_network(od, acquisition_manifest=manifest)
    assert temporal.coverage.missing_source_dates == ("2024-01-02",)
    assert temporal.coverage.empty_observed_dates == ("2024-01-03",)
    assert temporal.mean_per_observed_day().total_weight == 5.0
    with pytest.raises(ValueError, match="requires observed source dates"):
        temporal.mean_per_observed_day(["2024-01-02"])


def test_mobility_od_pipeline_lazily_validates_manifest_after_processing(
    tmp_path, monkeypatch
):
    header = "fecha|periodo|origen|destino|viajes|viajes_km\n"
    good = tmp_path / "20240101_Viajes.csv"
    bad = tmp_path / "20240102_Viajes.csv"
    good.write_text(header + "20240101|1|A|B|10|20\n")
    bad.write_text(header + "20240102|1|A|B|bad|20\n")
    mobility = object.__new__(Mobility)
    mobility.backend = "polars"
    mobility.version = 2
    mobility.zones = "municipalities"
    mobility.start_date = "2024-01-01"
    mobility.end_date = "2024-01-02"
    mobility.output_path = str(tmp_path)
    mobility._acquisition_manifests = {}
    mobility._od_processing_outcomes = {}

    def fake_download(m_type):
        mobility._set_acquisition_manifest(
            m_type,
            [
                [day, m_type, "available", "unverified", str(path), None]
                for day, path in [
                    ("2024-01-01", good),
                    ("2024-01-02", bad),
                ]
            ],
        )
        return [str(good), str(bad)]

    monkeypatch.setattr(mobility, "_donwload_helper", fake_download)
    od = mobility.get_od_data(return_df=True)
    assert od["n_trips"].sum() == 10.0
    assert mobility._acquisition_manifests["Viajes"]["parse_status"].tolist() == [
        "not_processed", "not_processed"
    ]
    with pytest.warns(RuntimeWarning, match="OD source parsing failed"):
        manifest = mobility.get_acquisition_manifest("Viajes")
    assert manifest["parse_status"].tolist() == ["valid", "failed"]
    temporal = build_temporal_network(od, acquisition_manifest=manifest)
    assert temporal.mean_per_observed_day().total_weight == 10.0


@pytest.mark.parametrize(
    "timestamp",
    ["2024-01-01T25:00:00", "2024-01-01T12:60:00", "2024-01-01T12:00:99"],
)
def test_temporal_rejects_impossible_clock_values(timestamp):
    od = pl.DataFrame(
        {
            "date": [timestamp],
            "id_origin": ["A"],
            "id_destination": ["B"],
            "n_trips": [1.0],
        }
    )
    with pytest.raises(ValueError, match="invalid endpoint, weight, or date"):
        build_temporal_network(od)


def test_temporal_failed_data_policy_requires_explicit_full_day_exclusion():
    od = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "id_origin": ["A", "A"],
            "id_destination": ["B", "B"],
            "n_trips": [2.0, 100.0],
        }
    )
    manifest = pl.DataFrame(
        {
            "date": ["2024-01-01", "2024-01-02"],
            "status": ["available", "available"],
            "parse_status": ["valid", "failed"],
        }
    )
    with pytest.raises(ValueError, match="partially failed source day"):
        build_temporal_network(od, acquisition_manifest=manifest)

    temporal = build_temporal_network(
        od, acquisition_manifest=manifest, failed_data_policy="exclude"
    )
    assert temporal.coverage.data_dates == ("2024-01-01",)
    assert temporal.audit()["excluded_failed_data_dates"] == ["2024-01-02"]
    assert temporal.audit()["excluded_failed_data_weight"] == 100.0
    assert temporal.sum_network().total_weight == 2.0


def test_temporal_configuration_cannot_diverge_from_its_snapshot_cache():
    temporal = build_temporal_network(
        pl.DataFrame(
            {
                "date": ["2024-01-01"],
                "id_origin": ["A"],
                "id_destination": ["A"],
                "n_trips": [2.0],
            }
        )
    )
    temporal.snapshot("2024-01-01")
    with pytest.raises(AttributeError, match="configuration is immutable"):
        temporal.spec = NetworkSpec(self_loops="drop")
    with pytest.raises(AttributeError, match="configuration is immutable"):
        temporal.max_cached_snapshots = 0


@pytest.mark.parametrize("scale", [1.0, 1e-200, 1e200])
def test_cosine_is_invariant_to_positive_weight_scale(scale):
    network = build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "A"],
                "id_destination": ["B", "C"],
                "n_trips": [scale, 2 * scale],
            }
        ),
        node_ids=["A", "B", "C"],
    )
    assert compare_networks(network, network).cosine_similarity == pytest.approx(1.0)
    assert destination_similarity(network, network).get_column(
        "destination_cosine_similarity"
    ).to_list() == pytest.approx([1.0, 1.0, 1.0])


def test_tiny_disjoint_destination_profiles_are_not_treated_as_empty():
    left = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [1e-200]}
        ),
        node_ids=["A", "B", "C"],
    )
    right = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["C"], "n_trips": [1e-200]}
        ),
        node_ids=["A", "B", "C"],
    )
    assert compare_networks(left, right).cosine_similarity == 0.0
    assert destination_similarity(left, right).row(0)[1] == 0.0


def test_spatial_aggregation_uses_custom_public_column_names_without_collision():
    od = pl.DataFrame(
        {
            "src": ["A", "B"],
            "dst": ["B", "A"],
            "id_origin": [2.0, 3.0],
        }
    )
    network = aggregate_od_network(
        od,
        {"A": "X", "B": "Y"},
        spec=NetworkSpec(origin="src", destination="dst", weight="id_origin"),
    )
    assert network.metadata.weight == "id_origin"
    assert network.total_weight == 5.0
    assert network.to_edge_table().to_dicts() == [
        {"id_origin": "X", "id_destination": "Y", "weight": 2.0},
        {"id_origin": "Y", "id_destination": "X", "weight": 3.0},
    ]


def test_audit_retains_initial_flow_loss_after_spatial_aggregation():
    source = build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "A"],
                "id_destination": ["A", "B"],
                "n_trips": [7.0, 5.0],
            }
        ),
        spec=NetworkSpec(self_loops="drop"),
    )
    aggregated = aggregate_network(source, {"A": "X", "B": "Y"})
    history = aggregated.audit()["provenance"]["history"]
    assert history[0]["kind"] == "construction"
    assert history[0]["dropped_self_loop_weight"] == 7.0
    assert history[-1]["kind"] == "spatial"


def test_provenance_is_deeply_immutable_and_json_compatible():
    original = {
        "array": np.asarray([1, 2]),
        "scalar": np.asarray(3),
        "nested": [{"value": 3}],
    }
    network = build_network(
        pl.DataFrame(
            {"id_origin": ["A"], "id_destination": ["B"], "n_trips": [1.0]}
        ),
        provenance=original,
    )
    original["array"][0] = 99
    assert network.audit()["provenance"]["array"] == [1, 2]
    assert network.audit()["provenance"]["scalar"] == 3
    assert json.loads(json.dumps(network.audit()))["provenance"]["array"] == [1, 2]
    with pytest.raises(TypeError):
        network.provenance["nested"][0]["value"] = 4


def test_undirected_network_canonicalizes_harmless_sparse_roundoff():
    directed = build_network(
        pl.DataFrame(
            {
                "id_origin": ["A", "B"],
                "id_destination": ["B", "A"],
                "n_trips": [0.1, 0.2],
            }
        )
    )
    undirected = symmetrize_network(directed, method="sum")
    noisy = undirected.adjacency.copy()
    noisy[0, 1] += 1e-13
    restored = SparseMobilityNetwork(
        noisy,
        undirected.node_ids,
        undirected.metadata,
        undirected.provenance,
        undirected.node_index,
    )
    assert (restored.adjacency != restored.adjacency.T).nnz == 0
