"""Run a small end-to-end temporal mobility-network pipeline and plot it.

The example creates a temporary Hive-partitioned OD dataset, then exercises
the production APIs used with a real processed MITMA dataset: source manifest,
lazy daily snapshots, bounded cache, temporal comparison, sparse edge changes,
and explicit undirected conversion.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory, gettempdir

_MATPLOTLIB_CACHE = Path(gettempdir()) / "pyspainmobility-matplotlib"
_MATPLOTLIB_CACHE.mkdir(exist_ok=True)
os.environ["MPLCONFIGDIR"] = str(_MATPLOTLIB_CACHE)
os.environ["MPLBACKEND"] = "Agg"

import matplotlib.pyplot as plt  # noqa: E402
import polars as pl  # noqa: E402

from pyspainmobility import (  # noqa: E402
    NodeIndex,
    build_temporal_network,
    node_strengths,
    symmetrize_network,
)
from pyspainmobility.network.integrations import run_infomap  # noqa: E402


NODE_INDEX = NodeIndex(
    ["Centro", "Este", "Oeste", "Norte", "Sur", "Puerto"],
    zoning_id="demo_municipalities",
    zoning_version="v1",
)


def _daily_rows(day: date) -> dict[str, list[object]]:
    """Create a realistic weekday/weekend change in destination patterns."""
    if day.weekday() < 5:
        origins = [
            "Centro", "Este", "Centro", "Oeste", "Este", "Oeste",
            "Norte", "Sur", "Norte", "Puerto", "Sur", "Puerto",
            "Centro", "Norte",
        ]
        destinations = [
            "Este", "Centro", "Oeste", "Centro", "Oeste", "Este",
            "Sur", "Norte", "Puerto", "Norte", "Puerto", "Sur",
            "Norte", "Centro",
        ]
        flows = [
            90.0, 80.0, 80.0, 75.0, 45.0, 35.0,
            85.0, 75.0, 65.0, 60.0, 55.0, 50.0, 18.0, 15.0,
        ]
    else:
        origins = [
            "Centro", "Este", "Centro", "Oeste", "Este", "Oeste",
            "Norte", "Sur", "Norte", "Puerto", "Sur", "Puerto",
            "Centro", "Sur",
        ]
        destinations = [
            "Este", "Centro", "Oeste", "Centro", "Oeste", "Este",
            "Sur", "Norte", "Puerto", "Norte", "Puerto", "Sur",
            "Sur", "Centro",
        ]
        flows = [
            25.0, 20.0, 20.0, 20.0, 20.0, 20.0,
            25.0, 25.0, 20.0, 20.0, 15.0, 15.0, 100.0, 90.0,
        ]
    return {
        "id_origin": origins,
        "id_destination": destinations,
        "n_trips": flows,
    }


def _write_partitioned_od(root: Path, dates: list[date]) -> None:
    """Write one Hive partition per date, matching a production OD layout."""
    for day in dates:
        partition = root / ("date=" + day.isoformat())
        partition.mkdir(parents=True)
        pl.DataFrame(_daily_rows(day)).write_parquet(
            partition / "part-0.parquet"
        )


POSITIONS = {
    "Centro": (-1.0, 0.0),
    "Este": (-2.0, 1.0),
    "Oeste": (-2.0, -1.0),
    "Norte": (1.0, 1.0),
    "Sur": (1.0, -1.0),
    "Puerto": (2.0, 0.0),
}


def _draw_network(
    ax, network, *, title: str, changes=None, communities=None, stability=None
) -> None:
    """Draw directed flow, signed change, or an undirected community graph."""
    directed = network.metadata.directed
    edges = (
        network.to_edge_table().to_dicts()
        if changes is None
        else changes.to_dicts()
    )
    strengths = {
        row["node_id"]: row["total_strength"]
        for row in node_strengths(network).to_dicts()
    }
    maximum_weight = max(
        (
            abs(row.get("weight", row.get("delta_weight", 0.0)))
            for row in edges
        ),
        default=1.0,
    )
    maximum_strength = max(strengths.values(), default=1.0)
    for edge in edges:
        origin = edge["id_origin"]
        destination = edge["id_destination"]
        if origin == destination:
            continue
        weight = edge["weight"] if "weight" in edge else edge["delta_weight"]
        color = "#377eb8"
        if changes is not None:
            color = "#4daf4a" if weight > 0 else "#e41a1c"
        start = POSITIONS[origin]
        end = POSITIONS[destination]
        width = 1.0 + 7.0 * abs(weight) / maximum_weight
        if directed or changes is not None:
            curvature = 0.12 if origin < destination else -0.12
            ax.annotate(
                "",
                xy=end,
                xytext=start,
                arrowprops={
                    "arrowstyle": "->",
                    "color": color,
                    "alpha": 0.72,
                    "linewidth": width,
                    "connectionstyle": "arc3,rad=" + str(curvature),
                },
            )
        else:
            ax.plot(
                [start[0], end[0]],
                [start[1], end[1]],
                color=color,
                alpha=0.72,
                linewidth=width,
                zorder=1,
            )

    palette = ["#4daf4a", "#984ea3", "#ff7f00", "#a65628"]
    stability_by_node = {} if stability is None else dict(
        zip(
            stability["node_id"].to_list(),
            stability["destination_cosine_similarity"].to_list(),
        )
    )
    for node_id in network.node_ids:
        x, y = POSITIONS[node_id]
        module = 0 if communities is None else communities.module_of(node_id)
        color = (
            palette[(module - 1) % len(palette)]
            if communities
            else "#4daf4a"
        )
        size = 350.0 + 1450.0 * strengths[node_id] / maximum_strength
        ax.scatter(x, y, s=size, color=color, edgecolor="#222222", zorder=3)
        label = node_id
        if stability is not None:
            label += "\ncos=" + format(stability_by_node[node_id], ".2f")
        ax.text(x, y, label, ha="center", va="center", fontsize=8, zorder=4)
    ax.set_title(title)
    ax.set_aspect("equal")
    ax.set_xlim(-2.7, 2.7)
    ax.set_ylim(-1.7, 1.7)
    ax.axis("off")


def run(output: Path) -> dict[str, object]:
    """Execute the pipeline and save a compact diagnostic plot."""
    dates = [date(2024, 1, 1) + timedelta(days=offset) for offset in range(7)]
    labels = [day.isoformat() for day in dates]
    with TemporaryDirectory(prefix="pyspainmobility-demo-") as temporary:
        dataset = Path(temporary) / "od"
        _write_partitioned_od(dataset, dates)
        manifest = pl.DataFrame({"date": labels, "status": ["available"] * 7})
        temporal = build_temporal_network(
            dataset,
            acquisition_manifest=manifest,
            node_index=NODE_INDEX,
            max_cached_snapshots=2,
        )

        daily_weight = [
            temporal.snapshot(label).total_weight for label in labels
        ]
        weekday = temporal.snapshot("2024-01-01")
        weekend = temporal.snapshot("2024-01-06")
        comparison = temporal.compare_snapshots("2024-01-01", "2024-01-06")
        stability = temporal.destination_stability("2024-01-01", "2024-01-06")
        changes = temporal.snapshot_edge_changes(
            "2024-01-01", "2024-01-06"
        ).filter(pl.col("delta_weight") != 0)
        weekly_undirected = symmetrize_network(
            temporal.sum_network(), method="sum"
        )
        try:
            communities = run_infomap(
                weekly_undirected, seed=123, num_trials=10, two_level=True
            )
        except ImportError:
            communities = None

    figure, axes = plt.subplots(
        2, 2, figsize=(13, 10), constrained_layout=True
    )
    _draw_network(
        axes[0, 0],
        weekday,
        title="Weekday OD network · directed flow",
    )
    _draw_network(
        axes[0, 1],
        weekend,
        title="Weekend OD network · directed flow",
    )
    _draw_network(
        axes[1, 0],
        weekend,
        title="Weekend − weekday · green increase / red decrease",
        changes=changes,
        stability=stability,
    )
    community_title = "Weekly bilateral network · Infomap modules"
    if communities is None:
        community_title = "Weekly bilateral network · Infomap not installed"
    _draw_network(
        axes[1, 1],
        weekly_undirected,
        title=community_title,
        communities=communities,
    )
    figure.suptitle(
        "Temporal mobility-network analysis: node area = weighted strength; "
        "edge width = trip flow",
        fontsize=14,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=160)
    plt.close(figure)
    return {
        "output": str(output),
        "daily_flow": daily_weight,
        "mon_to_sat": comparison.audit(),
        "cache": temporal.audit(),
        "weekly_undirected": weekly_undirected.audit(),
        "communities": (
            None if communities is None else communities.communities()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("network_pipeline_demo.png"),
        help="PNG path for the result plot.",
    )
    arguments = parser.parse_args()
    print(json.dumps(run(arguments.output), indent=2, default=str))


if __name__ == "__main__":
    main()
