"""Derived province products: real parsers, routing, flow accounting and limits."""

import gzip
import json
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import polars as pl
import pytest
from shapely.geometry import Polygon, box

from pyspainmobility import Mobility, Zones, build_network, build_temporal_network
from pyspainmobility.utils import utils
import pyspainmobility.mobility.mobility as mobility_module


def _mobility(monkeypatch, tmp_path, backend, version, contents, *, end_date=None):
    day = "2024-01-01" if version == 2 else "2020-03-11"
    monkeypatch.setattr(utils, "get_valid_dates", lambda _: [day, end_date or day])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path))
    if backend == "arrow":
        pytest.importorskip("pyarrow")
    mobility = Mobility(version=version, zones="provinces", start_date=day,
                        end_date=end_date, output_directory=str(tmp_path), backend=backend)
    if version == 2:
        (tmp_path / "relacion_ine_zonificacionMitma.csv").write_text(
            "municipio_ine|distrito_mitma|municipio_mitma|gau_mitma\n"
            "28079|D1|M1|G1\n28079|D1|M1|G1\n28080|D2|M2|G1\n08001|D3|M3|G2\n"
        )
    else:
        (tmp_path / "relaciones_municipio_mitma.csv").write_text(
            "municipio|municipio_mitma\n28079|M1\n28080|M2\n08001|M3\n"
        )
        (tmp_path / "relaciones_distrito_mitma.csv").write_text(
            "distrito|distrito_mitma|municipio_mitma\n"
            "2807901|D1|M1\n2808001|D2|M2\n0800101|D3|M3\n"
        )
    calls = []

    def download(url, path):
        calls.append(url)
        assert "provinces" not in url and "distritos" in url
        product = next(name for name in contents if name.lower() in url.lower())
        source_day = Path(path).name[:8]
        content = contents[product].format(day=source_day)
        with gzip.open(path, "wt") as stream:
            stream.write(content)

    monkeypatch.setattr(utils, "download_file_if_not_existing", download)
    return mobility, calls


@pytest.mark.parametrize("backend", ["pandas", "polars", "arrow"])
@pytest.mark.parametrize("version", [1, 2])
def test_province_od_preserves_dimensions_loops_and_audits_exclusions(
    monkeypatch, tmp_path, backend, version
):
    product = "Viajes" if version == 2 else "maestra1"
    source = (
        "fecha|periodo|origen|destino|actividad_origen|actividad_destino|viajes|viajes_km\n"
        "{day}|0|D1|D2| NA |casa|2|10\n"
        "{day}|0|D2|D1| NA |casa|3|20\n"
        "{day}|1|D1|D3|trabajo|casa|4|40\n"
        "{day}|2|D2|D3|trabajo|casa|5|50\n"
        "{day}|0|X|D3|trabajo|casa|7|70\n"
        "{day}|0|X|X|trabajo|casa|11|110\n"
    )
    mobility, calls = _mobility(monkeypatch, tmp_path, backend, version, {product: source})
    with pytest.warns(RuntimeWarning, match="excluded 2 processed rows"):
        result = mobility.get_od_data(return_df=True, dimensions=["activity_origin", "activity_destination"])
    assert mobility.zones == "provinces" and mobility.source_zones == "distritos"
    assert len(calls) == 1 and len(result) == 3
    assert result["n_trips"].sum() == 14
    assert result["trips_total_length_km"].sum() == 120
    internal = result.loc[result.id_origin == result.id_destination].iloc[0]
    assert internal.n_trips == 5 and pd.isna(internal.activity_origin)
    assert set(result.hour) == {0, 1, 2}
    audit = result.attrs["spatial"]
    assert audit["input_n_trips"] == 32
    assert audit["excluded_n_trips"] == 18
    assert audit["excluded_trips_total_length_km"] == 180
    assert audit["unmapped_source_ids"] == ["X"]
    saved = next(tmp_path.glob("*provinces*.parquet"))
    pd.testing.assert_frame_equal(Mobility._polars_to_pandas(pl.read_parquet(saved)), result, check_dtype=False)
    provenance = json.loads(Path(str(saved) + ".provenance.json").read_text())
    assert provenance["derived"] and provenance["source_zones"] == "distritos"
    assert provenance["spatial"] == audit
    manifest = mobility.get_acquisition_manifest(product)
    assert manifest.loc[0, "excluded_n_trips"] == 18
    assert manifest.loc[0, "parse_status"] == "valid"
    assert build_network(result).total_weight == 14
    temporal = build_temporal_network(result, acquisition_manifest=manifest)
    assert temporal.sum_network().total_weight == 14
    result.attrs["spatial"]["by_date"][0]["excluded_n_trips"] = 999
    assert mobility.get_acquisition_manifest(product).loc[0, "excluded_n_trips"] == 18


@pytest.mark.parametrize("backend", ["pandas", "polars", "arrow"])
@pytest.mark.parametrize("version,product,method,source,expected", [
    (2, "Pernoctaciones", "get_overnight_stays_data",
     "fecha|zona_residencia|zona_pernoctacion|personas\n{day}|D1|D2|2\n{day}|D2|D1|3\n{day}|D3|D1|4\n{day}|X|D1|7\n", 9),
    (2, "Personas", "get_number_of_trips_data",
     "fecha|zona_pernoctacion|numero_viajes|personas|edad|sexo\n{day}|D1|2+|2| NA | NA \n{day}|D2|2+|3| NA | NA \n{day}|D3|1|4|25-44|hombre\n{day}|X|1|7|25-44|hombre\n", 9),
    (1, "maestra2", "get_number_of_trips_data",
     "fecha|distrito|numero_viajes|personas\n{day}|D1|2+|2\n{day}|D2|2+|3\n{day}|D3|1|4\n{day}|X|1|7\n", 9),
])
def test_province_person_products_preserve_counts_categories_and_missing_values(
    monkeypatch, tmp_path, backend, version, product, method, source, expected
):
    mobility, _ = _mobility(monkeypatch, tmp_path, backend, version, {product: source})
    with pytest.warns(RuntimeWarning, match="excluded 1 processed rows"):
        result = getattr(mobility, method)(return_df=True)
    assert result.people.sum() == expected and len(result) == 2
    if "number_of_trips" in result:
        row = result.loc[result.number_of_trips == "2+"].iloc[0]
        assert row.people == 5 and pd.isna(row.age) and pd.isna(row.gender)
    manifest = mobility.get_acquisition_manifest(product)
    assert manifest.loc[0, "excluded_people"] == 7
    assert result.attrs["spatial"]["input_people"] == expected + 7


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_province_entirely_unmapped_day_stays_observed_and_has_empty_output(
    monkeypatch, tmp_path, backend
):
    source = "fecha|periodo|origen|destino|viajes|viajes_km\n{day}|0|X|X|3|9\n"
    mobility, _ = _mobility(monkeypatch, tmp_path, backend, 2, {"Viajes": source})
    with pytest.warns(RuntimeWarning, match="excluded 1 processed rows"):
        result = mobility.get_od_data(return_df=True)
    assert result.empty and len(result.columns) == 6
    assert mobility.get_acquisition_manifest().loc[0, "parse_status"] == "valid"
    assert result.attrs["spatial"]["excluded_n_trips"] == 3
    assert next(tmp_path.glob("*.parquet")).exists()
    temporal = build_temporal_network(result, node_ids=["28"], acquisition_manifest=mobility.get_acquisition_manifest())
    assert temporal.sum_network().total_weight == 0
    assert temporal.mean_per_observed_day().audit()["provenance"]["temporal"]["observed_day_count"] == 1


def test_province_mapping_exclusion_never_uses_only_part_of_a_zone(monkeypatch, tmp_path):
    zones = Zones("districts", 2, str(tmp_path))
    relations = pd.DataFrame({
        "districts_mitma": ["A", "A", "B", "B", "C", "C"],
        "municipalities": ["28079", "08001", "28079", None, "51001", "51001"],
    })
    monkeypatch.setattr(zones, "get_zone_relations", lambda: relations)
    mapping = zones.get_province_mapping(source_ids=["A", "B", "C", "X"], unmapped="exclude")
    assert mapping.to_dict("records") == [{"source_id": "C", "target_id": "51"}]
    assert mapping.attrs["unmapped_source_ids"] == ["A", "B", "X"]
    with pytest.raises(ValueError):
        zones.get_province_mapping(source_ids=["A"])


@pytest.mark.parametrize("invalid_geometry", [False, True])
@pytest.mark.parametrize("version", [1, 2])
def test_province_geometries_dissolve_once_and_preserve_crs_population(monkeypatch, tmp_path, invalid_geometry, version):
    frame = gpd.GeoDataFrame({"population": [10, 20, 5, None], "geometry": [
        box(0, 0, 1, 1), box(1, 0, 2, 1), box(3, 0, 4, 1), box(5, 0, 6, 1),
    ]}, index=pd.Index(["D1", "D2", "D3", "X"], name="id"), crs="EPSG:4326")
    if invalid_geometry:
        frame.loc["D3", "geometry"] = Polygon([(3, 0), (4, 1), (3, 1), (4, 0), (3, 0)])
    reads = []
    def load_source(self):
        reads.append(self.zones)
        self.complete_df = frame
    original = Zones._load_zone_geodataframe
    monkeypatch.setattr(Zones, "_load_zone_geodataframe", lambda self: original(self) if self.zones == "provinces" else load_source(self))
    relations = pd.DataFrame({
        "districts_mitma": ["D1", "D2", "D3"], "municipalities": ["28079", "28080", "08001"],
    }) if version == 2 else pd.DataFrame(
        {"municipalities": [{"28079"}, {"28080"}, {"08001"}]},
        index=pd.Index(["D1", "D2", "D3"], name="id"),
    )
    monkeypatch.setattr(Zones, "get_zone_relations", lambda self: relations)
    zones = Zones("provinces", version, str(tmp_path))
    with pytest.warns(RuntimeWarning, match="exclude 1 unmapped"):
        result = zones.get_zone_geodataframe()
    assert result.index.tolist() == ["08", "28"] and result.crs == frame.crs
    assert result.loc["28", "population"] == 30
    assert result.loc["28", "geometry"].area == 2
    assert result.attrs["unmapped_source_ids"] == ["X"]
    assert result.geometry.is_valid.all()
    assert result.attrs["repaired_source_geometries"] == int(invalid_geometry)
    assert zones.get_zone_geodataframe() is result and reads == ["distritos"]


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_province_partial_output_audits_only_valid_source_days(monkeypatch, tmp_path, backend):
    source = "fecha|periodo|origen|destino|viajes|viajes_km\n{day}|0|D1|D2|3|9\n{day}|0|X|D1|2|8\n"
    mobility, _ = _mobility(monkeypatch, tmp_path, backend, 2, {"Viajes": source}, end_date="2024-01-02")
    download = utils.download_file_if_not_existing
    def invalid_second_day(url, path):
        download(url, path)
        if "20240102" in path:
            with gzip.open(path, "at") as stream:
                stream.write("20240102|0|D1|D2|-1|4\n")
    monkeypatch.setattr(utils, "download_file_if_not_existing", invalid_second_day)
    with pytest.warns(RuntimeWarning, match="OD source parsing failed"):
        with pytest.raises(RuntimeError, match="2024-01-02"):
            mobility.get_od_data(return_df=True)
    assert not list(tmp_path.glob("*.parquet"))
    with pytest.warns(RuntimeWarning):
        result = mobility.get_od_data(return_df=True, allow_partial=True)
    assert result.n_trips.sum() == 3
    assert result.attrs["spatial"]["excluded_n_trips"] == 2
    assert next(tmp_path.glob("*.parquet")).name.endswith("_partial.parquet")
    manifest = mobility.get_acquisition_manifest()
    assert manifest.parse_status.tolist() == ["valid", "failed"]
    assert manifest.excluded_n_trips.tolist() == [2, 0]


def test_province_dask_failure_falls_back_without_changing_level(monkeypatch, tmp_path):
    source = "fecha|periodo|origen|destino|viajes|viajes_km\n{day}|0|D1|D2|3|9\n"
    mobility, _ = _mobility(monkeypatch, tmp_path, "pandas", 2, {"Viajes": source})
    class FailingDask:
        @staticmethod
        def compute(*tasks):
            raise RuntimeError("injected Dask failure")
    monkeypatch.setattr(mobility_module, "dd", FailingDask())
    monkeypatch.setattr(mobility_module, "delayed", lambda function: lambda *args: (function, args))
    mobility.use_dask = True
    result = mobility.get_od_data(return_df=True)
    assert result.id_origin.tolist() == ["28"] and result.id_destination.tolist() == ["28"]
    assert result.n_trips.sum() == 3 and result.attrs["derived"]


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_province_overflow_is_rejected_before_publication(monkeypatch, tmp_path, backend):
    source = "fecha|periodo|origen|destino|viajes|viajes_km\n{day}|0|D1|D2|1e308|9\n"
    mobility, _ = _mobility(monkeypatch, tmp_path, backend, 2, {"Viajes": source}, end_date="2024-01-02")
    with np.errstate(over="ignore"):
        with pytest.raises(ValueError, match="non-finite totals"):
            mobility.get_od_data(return_df=True)
    assert not list(tmp_path.glob("*.parquet"))


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_province_large_input_matches_independent_flow_accumulation(monkeypatch, tmp_path, backend):
    mobility, _ = _mobility(monkeypatch, tmp_path, backend, 2, {})
    rng = np.random.default_rng(714)
    origins, destinations = rng.integers(0, 4, size=(2, 100_000))
    trips = rng.integers(1, 100, size=100_000).astype(float)
    province = np.array([1, 1, 0, -1])
    retained = (province[origins] >= 0) & (province[destinations] >= 0)
    expected = np.zeros((2, 2))
    np.add.at(expected, (province[origins[retained]], province[destinations[retained]]), trips[retained])
    data = {
        "date": ["2024-01-01"] * len(trips), "hour": rng.integers(0, 24, size=len(trips)),
        "id_origin": np.array(["D1", "D2", "D3", "X"])[origins],
        "id_destination": np.array(["D1", "D2", "D3", "X"])[destinations],
        "n_trips": trips, "trips_total_length_km": trips * 2,
    }
    frame = pl.DataFrame(data) if backend == "polars" else pd.DataFrame(data)
    with pytest.warns(RuntimeWarning, match="excluded"):
        result = mobility._aggregate_provinces(frame, "Viajes")
    assert len(result) <= 24 * 2 * 2
    network = build_network(result, node_ids=["08", "28"])
    np.testing.assert_allclose(network.adjacency.toarray(), expected)
    assert mobility._province_reports["Viajes"]["excluded_n_trips"] == trips[~retained].sum()


@pytest.mark.parametrize("backend", ["pandas", "polars"])
@pytest.mark.minimal_install
def test_province_products_work_without_optional_arrow(monkeypatch, tmp_path, backend):
    source = "fecha|periodo|origen|destino|viajes|viajes_km\n{day}|0|D1|D2|3|9\n"
    mobility, _ = _mobility(monkeypatch, tmp_path, backend, 2, {"Viajes": source})
    monkeypatch.setattr(mobility_module, "pa", None)
    def no_arrow(*args, **kwargs):
        raise ImportError("No parquet engine")
    monkeypatch.setattr(pd.DataFrame, "to_parquet", no_arrow)
    result = mobility.get_od_data(return_df=True)
    assert result.n_trips.sum() == 3 and result.attrs["derived"]
    assert pl.read_parquet(next(tmp_path.glob("*.parquet")))["id_origin"].to_list() == ["28"]


@pytest.mark.parametrize("existing_output", [False, True])
@pytest.mark.parametrize("failure_stage", ["serialize", "publish", "rollback"])
def test_province_failed_provenance_write_keeps_previous_output(
    monkeypatch, tmp_path, existing_output, failure_stage
):
    source = "fecha|periodo|origen|destino|viajes|viajes_km\n{day}|0|D1|D2|3|9\n"
    contents = {"Viajes": source}
    mobility, _ = _mobility(monkeypatch, tmp_path, "polars", 2, contents)
    previous = previous_audit = None
    if existing_output:
        mobility.get_od_data()
        saved = next(tmp_path.glob("*.parquet"))
        previous = saved.read_bytes()
        previous_audit = Path(str(saved) + ".provenance.json").read_bytes()
    contents["Viajes"] = source.replace("|3|9", "|7|21")
    def failed_write(*args):
        raise OSError("audit disk failure")
    if failure_stage == "serialize":
        monkeypatch.setattr(utils, "write_json_atomic", failed_write)
    else:
        original_replace = mobility_module.os.replace
        def failed_publish(src, dst):
            if str(dst).endswith(".provenance.json"):
                failed_write()
            if failure_stage == "rollback" and str(src).endswith(".previous"):
                raise OSError("rollback disk failure")
            return original_replace(src, dst)
        monkeypatch.setattr(mobility_module.os, "replace", failed_publish)
    with pytest.raises(OSError, match="disk failure"):
        mobility.get_od_data()
    if existing_output and failure_stage == "rollback":
        backup, = tmp_path.glob(".*.previous")
        assert backup.read_bytes() == previous
        assert Path(str(saved) + ".provenance.json").read_bytes() == previous_audit
        assert not list(tmp_path.glob(".*.json"))
        return
    if existing_output:
        assert saved.read_bytes() == previous
        assert Path(str(saved) + ".provenance.json").read_bytes() == previous_audit
    else:
        assert not list(tmp_path.glob("*.parquet*"))
    assert not list(tmp_path.glob(".*.parquet*"))


@pytest.mark.parametrize("source_id,geometry", [("X", box(0, 0, 1, 1)), ("D1", None), ("D1", Polygon())])
def test_province_geometry_empty_selection_and_missing_geometry(monkeypatch, tmp_path, source_id, geometry):
    frame = gpd.GeoDataFrame({"geometry": [geometry]}, index=pd.Index([source_id], name="id"), crs="EPSG:4326")
    original = Zones.get_zone_geodataframe
    monkeypatch.setattr(Zones, "get_zone_geodataframe", lambda self: original(self) if self.zones == "provinces" else frame)
    monkeypatch.setattr(Zones, "get_zone_relations", lambda self: pd.DataFrame({
        "districts_mitma": ["D1"], "municipalities": ["28079"],
    }))
    zones = Zones("provinces", 2, str(tmp_path))
    if source_id == "X":
        with pytest.warns(RuntimeWarning, match="exclude 1 unmapped"):
            result = zones.get_zone_geodataframe()
        assert result.empty and result.crs == frame.crs and result.index.name == "id"
    else:
        with pytest.raises(ValueError, match="lack geometry.*D1"):
            zones.get_zone_geodataframe()
