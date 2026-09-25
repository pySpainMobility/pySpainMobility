import gzip
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

import pyspainmobility.mobility.mobility as mobility_module
from pyspainmobility.mobility.mobility import Mobility
from pyspainmobility.network import aggregate_network, build_network
from pyspainmobility.utils import utils
from pyspainmobility.zones.zones import Zones


def _build_mobility(
    monkeypatch,
    tmp_path,
    backend="arrow",
    version=2,
    zones="municipalities",
    start_date=None,
    end_date=None,
    use_dask=False,
):
    if start_date is None:
        start_date = "2022-01-01" if version == 2 else "2020-03-11"
    if end_date is None:
        end_date = start_date

    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        utils,
        "get_dates_between",
        lambda s, e: pd.date_range(start=s, end=e, freq="D").strftime("%Y-%m-%d").tolist(),
    )
    if version == 2:
        monkeypatch.setattr(utils, "get_valid_dates", lambda *_: ["2022-01-01", "2022-12-31"])
    else:
        monkeypatch.setattr(utils, "get_valid_dates", lambda *_: ["2020-01-01", "2021-12-31"])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    mobility = Mobility(
        version=version,
        zones=zones,
        start_date=start_date,
        end_date=end_date,
        output_directory=str(tmp_path / "custom_out"),
        backend=backend,
        use_dask=use_dask,
    )
    monkeypatch.setattr(mobility, "_saving_parquet", lambda *_: None)
    return mobility


class _FakeDaskCompute:
    @staticmethod
    def compute(*_args, **_kwargs):
        raise RuntimeError("injected dask failure")


def _build_mobility_dask(
    monkeypatch,
    tmp_path,
    version=2,
    zones="municipalities",
    start_date=None,
    end_date=None,
):
    monkeypatch.setattr(mobility_module, "dd", _FakeDaskCompute())

    def _fake_delayed(func):
        def _wrapper(*args, **kwargs):
            return (func, args, kwargs)
        return _wrapper

    monkeypatch.setattr(mobility_module, "delayed", _fake_delayed)
    return _build_mobility(
        monkeypatch,
        tmp_path,
        backend="pandas",
        version=version,
        zones=zones,
        start_date=start_date,
        end_date=end_date,
        use_dask=True,
    )


def _write_gzip(path, content):
    with gzip.open(path, "wt", encoding="utf-8") as gz_file:
        gz_file.write(content)


def test_mobility_init_defaults_end_date_to_start_date(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "get_dates_between", lambda *_: ["2022-01-01"])
    monkeypatch.setattr(utils, "get_valid_dates", lambda *_: ["2022-01-01", "2022-12-31"])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    mobility = Mobility(
        version=2,
        zones="municipalities",
        start_date="2022-01-01",
        end_date=None,
        output_directory=str(tmp_path / "custom_out"),
        backend="pandas",
    )

    assert mobility.end_date == "2022-01-01"


def test_mobility_init_raises_clear_error_when_valid_dates_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "get_dates_between", lambda *_: ["2022-01-01"])
    monkeypatch.setattr(utils, "get_valid_dates", lambda *_: [])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    with pytest.raises(RuntimeError, match="Could not resolve valid dates"):
        Mobility(
            version=2,
            zones="municipalities",
            start_date="2022-01-01",
            end_date="2022-01-01",
            output_directory=str(tmp_path / "custom_out"),
            backend="pandas",
        )


def test_mobility_init_raises_friendly_runtime_error_on_network_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "get_dates_between", lambda *_: ["2022-01-01"])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    def _raise_network(*_args, **_kwargs):
        raise RuntimeError("HTTP Error 500: Internal Server Error")

    monkeypatch.setattr(utils, "get_valid_dates", _raise_network)

    with pytest.raises(RuntimeError, match="Could not reach the MITMA open-data server"):
        Mobility(
            version=2,
            zones="municipalities",
            start_date="2022-01-01",
            end_date="2022-01-01",
            output_directory=str(tmp_path / "custom_out"),
            backend="pandas",
        )


def test_mobility_keeps_absolute_output_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "get_dates_between", lambda *_: ["2022-01-01"])
    monkeypatch.setattr(utils, "get_valid_dates", lambda *_: ["2022-01-01", "2022-12-31"])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    absolute_out = str(tmp_path / "nested" / "abs_mobility_output")
    mobility = Mobility(
        version=2,
        zones="municipalities",
        start_date="2022-01-01",
        end_date="2022-01-01",
        output_directory=absolute_out,
        backend="pandas",
    )

    assert mobility.output_path == absolute_out


def test_zones_keeps_absolute_output_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    absolute_out = str(tmp_path / "nested" / "abs_zones_output")
    zones = Zones(zones="municipalities", version=2, output_directory=absolute_out)

    assert zones.output_path == absolute_out


def test_zones_version2_reads_supporting_files_from_output_directory(monkeypatch, tmp_path):
    output_dir = tmp_path / "custom_data"
    output_dir.mkdir()
    default_dir = tmp_path / "default_data"
    default_dir.mkdir()

    (output_dir / "nombres_municipios.csv").write_text("ID|name\n01001|Town A\n", encoding="utf-8")
    (output_dir / "poblacion_municipios.csv").write_text("ID|population\n01001|1234\n", encoding="utf-8")

    required_files = [
        "nombres_municipios.csv",
        "poblacion_municipios.csv",
        "zonificacion_municipios.shp",
    ]
    calls = {"available": 0, "download": 0}

    def fake_available(*_):
        calls["available"] += 1
        return pd.DataFrame({"link": [f"https://example.org/{f}" for f in required_files]})

    monkeypatch.setattr(utils, "available_zoning_data", fake_available)
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(default_dir))

    def fake_download(*_):
        calls["download"] += 1

    monkeypatch.setattr(utils, "download_file_if_not_existing", fake_download)

    read_paths = []

    def fake_read_file(path, *args, **kwargs):
        read_paths.append(str(path))
        path_str = str(path)
        if path_str.endswith("zonificacion_municipios.shp"):
            return gpd.GeoDataFrame({"ID": ["01001"], "geometry": [Point(0, 0)]}, crs="EPSG:4326")
        raise FileNotFoundError(path)

    monkeypatch.setattr(gpd, "read_file", fake_read_file)
    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", lambda *_args, **_kwargs: None)

    zones = Zones(zones="municipalities", version=2, output_directory=str(output_dir))
    assert calls["available"] == 0
    assert calls["download"] == 0

    assert zones.get_zone_geodataframe() is not None
    assert calls["available"] == 1
    assert str(output_dir / "zonificacion_municipios.shp") in read_paths
    assert not any(path.startswith(str(default_dir)) for path in read_paths)


def test_zones_default_version_is_2(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))
    zones = Zones(zones="municipalities", output_directory=str(tmp_path / "custom_data"))
    assert zones.version == 2


def test_zones_init_without_explicit_zone_uses_default_municipalities(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))
    zones = Zones(output_directory=str(tmp_path / "custom_data"))
    assert zones.zones == "municipios"
    assert zones.version == 2


def test_get_zone_relations_uses_output_path_for_version2(monkeypatch, tmp_path):
    out_dir = tmp_path / "custom_data"
    out_dir.mkdir()
    default_dir = tmp_path / "default_data"
    default_dir.mkdir()

    (out_dir / "relacion_ine_zonificacionMitma.csv").write_text(
        "seccion_ine|distrito_ine|municipio_ine|municipio_mitma|distrito_mitma|gau_mitma\n"
        "2807901|28079|28079|28079|2807901|28079_GAU\n",
        encoding="utf-8",
    )

    calls = {"available": 0, "download": 0}

    def fake_available(*_):
        calls["available"] += 1
        return pd.DataFrame(
            {
                "link": [
                    "https://example.org/relacion_ine_zonificacionMitma.csv",
                ]
            }
        )

    def fake_download(*_):
        calls["download"] += 1

    monkeypatch.setattr(utils, "available_zoning_data", fake_available)
    monkeypatch.setattr(utils, "download_file_if_not_existing", fake_download)
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(default_dir))

    zones = Zones(zones="municipalities", version=2, output_directory=str(out_dir))
    assert calls["available"] == 0
    assert calls["download"] == 0

    df = zones.get_zone_relations()

    assert len(df) == 1
    assert df.loc[0, "census_sections"] == "2807901"
    expected_cols = {
        "census_sections",
        "census_districts",
        "municipalities",
        "municipalities_mitma",
        "districts_mitma",
        "luas_mitma",
    }
    assert set(df.columns) == expected_cols
    assert {"seccion_ine", "distrito_ine", "municipio_ine", "municipio_mitma", "distrito_mitma", "gau_mitma"}.isdisjoint(
        df.columns
    )
    assert calls["available"] == 1
    assert calls["download"] == 0


def test_process_single_od_file_normalizes_bom_headers_and_float_like_ids(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path)

    file_path = tmp_path / "od_sample.csv.gz"
    content = (
        "\ufefffecha|periodo|origen|destino|actividad_origen|actividad_destino|residencia|renta|edad|sexo|viajes|viajes_km\n"
        "20220101|00|01001.0|01009.0|casa|frecuente|01.0|10-15|NA|hombre|1|2.5\n"
    )
    _write_gzip(file_path, content)

    df = mobility._process_single_od_file(str(file_path), keep_activity=False, social_agg=False)

    assert list(df.columns) == ["date", "hour", "id_origin", "id_destination", "n_trips", "trips_total_length_km"]
    assert df.loc[0, "date"] == "2022-01-01"
    assert df.loc[0, "id_origin"] == "01001"
    assert df.loc[0, "id_destination"] == "01009"


@pytest.mark.parametrize("backend", ["arrow", "polars"])
def test_get_overnight_stays_data_normalizes_headers_and_ids(
    monkeypatch,
    tmp_path,
    backend,
):
    mobility = _build_mobility(monkeypatch, tmp_path, backend=backend)

    file_path = tmp_path / "overnight_sample.csv.gz"
    content = (
        "\ufefffecha|zona_residencia|zona_pernoctacion|personas\n"
        "20220101|01001.0|01009.0|2214.577\n"
    )
    _write_gzip(file_path, content)

    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_overnight_stays_data(return_df=True)

    assert list(df.columns) == ["date", "residence_area", "overnight_stay_area", "people"]
    assert df.loc[0, "residence_area"] == "01001"
    assert df.loc[0, "overnight_stay_area"] == "01009"
    assert df.loc[0, "people"] == pytest.approx(2214.577)


@pytest.mark.parametrize("backend", ["arrow", "polars"])
def test_get_number_of_trips_data_normalizes_headers_ids_and_gender(
    monkeypatch,
    tmp_path,
    backend,
):
    mobility = _build_mobility(monkeypatch, tmp_path, backend=backend)

    file_path = tmp_path / "trips_sample.csv.gz"
    content = (
        "\ufefffecha|zona_pernoctacion|edad|sexo|numero_viajes|personas\n"
        "20220101|01001.0|25-45|mujer|2+|128.457\n"
    )
    _write_gzip(file_path, content)

    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_number_of_trips_data(return_df=True)

    assert list(df.columns) == ["date", "overnight_stay_area", "age", "gender", "number_of_trips", "people"]
    assert df.loc[0, "overnight_stay_area"] == "01001"
    assert df.loc[0, "gender"] == "female"
    assert df.loc[0, "people"] == pytest.approx(128.457)


def test_numeric_parser_is_row_local_and_matches_polars():
    converted = Mobility._to_numeric(pd.Series(["1.234.567", "2.000"]), strip_thousands=True)
    assert converted.tolist() == [1234567, 2.0]

    unchanged_decimal = Mobility._to_numeric(pd.Series(["128.457"]), strip_thousands=True)
    assert unchanged_decimal.tolist() == [128.457]

    polars_converted = (
        mobility_module.pl.DataFrame({"value": ["1.234.567", "2.000"]})
        .select(Mobility._polars_numeric("value", strip_thousands=True).alias("value"))
        .get_column("value")
        .to_list()
    )
    assert polars_converted == [1234567.0, 2.0]


def test_mitma_integer_parser_matches_blog_style_conversion():
    converted = Mobility._to_mitma_integer(
        pd.Series(["1.0", "2214.577", "56.400", "128.457", "1.234.567", "2.000"])
    )
    assert converted.tolist() == [1, 2214577, 56400, 128457, 1234567, 2]


def test_process_single_od_file_preserves_decimal_flow_sizes(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path)

    file_path = tmp_path / "od_dot_grouped.csv.gz"
    content = (
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20220101|00|01001|01009|10.098|39.969\n"
    )
    _write_gzip(file_path, content)

    df = mobility._process_single_od_file(str(file_path), keep_activity=False, social_agg=False)
    assert df.loc[0, "n_trips"] == pytest.approx(10.098)
    assert df.loc[0, "trips_total_length_km"] == pytest.approx(39.969)


def test_backend_validation_rejects_unknown_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "get_dates_between", lambda *_: ["2022-01-01"])
    monkeypatch.setattr(utils, "get_valid_dates", lambda *_: ["2022-01-01", "2022-01-02"])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    with pytest.raises(ValueError, match="backend must be one of"):
        Mobility(
            version=2,
            zones="municipalities",
            start_date="2022-01-01",
            end_date="2022-01-01",
            output_directory=str(tmp_path / "custom_out"),
            backend="invalid",
        )


def test_arrow_backend_falls_back_to_pandas_when_pyarrow_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "get_dates_between", lambda *_: ["2022-01-01"])
    monkeypatch.setattr(utils, "get_valid_dates", lambda *_: ["2022-01-01", "2022-01-02"])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))
    monkeypatch.setattr(mobility_module, "pa", None)
    monkeypatch.setattr(mobility_module, "pacsv", None)

    with pytest.warns(RuntimeWarning, match="Falling back to backend='pandas'"):
        mobility = Mobility(
            version=2,
            zones="municipalities",
            start_date="2022-01-01",
            end_date="2022-01-01",
            output_directory=str(tmp_path / "custom_out"),
            backend="arrow",
        )

    assert mobility.backend == "pandas"


def test_polars_backend_explains_missing_base_dependency(monkeypatch, tmp_path):
    monkeypatch.setattr(mobility_module, "pl", None)

    with pytest.raises(ImportError, match="base dependencies"):
        _build_mobility(monkeypatch, tmp_path, backend="polars")


def test_auto_backend_prefers_polars(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="auto")

    assert mobility.requested_backend == "auto"
    assert mobility.backend == "polars"


def test_auto_backend_falls_back_to_arrow_then_pandas(monkeypatch, tmp_path):
    monkeypatch.setattr(mobility_module, "pl", None)
    mobility = _build_mobility(monkeypatch, tmp_path, backend="auto")
    assert mobility.backend == "arrow"

    monkeypatch.setattr(mobility_module, "pa", None)
    monkeypatch.setattr(mobility_module, "pacsv", None)
    mobility = _build_mobility(monkeypatch, tmp_path, backend="auto")
    assert mobility.backend == "pandas"


def test_polars_ignores_dask_without_requiring_it(monkeypatch, tmp_path):
    monkeypatch.setattr(mobility_module, "dd", None)
    monkeypatch.setattr(mobility_module, "delayed", None)

    with pytest.warns(RuntimeWarning, match="use_dask=True is ignored"):
        mobility = _build_mobility(
            monkeypatch,
            tmp_path,
            backend="polars",
            use_dask=True,
        )

    assert mobility.backend == "polars"


def test_arrow_parser_falls_back_to_pandas_when_pyarrow_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(mobility_module, "pa", None)
    monkeypatch.setattr(mobility_module, "pacsv", None)

    file_path = tmp_path / "backend_arrow_missing_pyarrow.csv.gz"
    content = (
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20220101|00|01001|01009|1|2.5\n"
    )
    _write_gzip(file_path, content)

    with pytest.warns(RuntimeWarning, match="Falling back to pandas parser"):
        df = Mobility._read_pipe_file_arrow(
            str(file_path),
            dtype={"origen": "string", "destino": "string"},
        )

    assert all("[pyarrow]" not in str(dtype) for dtype in df.dtypes)


def test_arrow_backend_reads_arrow_dtypes(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="arrow")

    file_path = tmp_path / "backend_arrow.csv.gz"
    content = (
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20220101|00|01001|01009|1|2.5\n"
    )
    _write_gzip(file_path, content)

    df = mobility._read_pipe_file(
        str(file_path),
        dtype={"origen": "string", "destino": "string"},
    )

    assert any("[pyarrow]" in str(dtype) for dtype in df.dtypes)


def test_pandas_backend_keeps_classic_pandas_dtypes(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="pandas")

    file_path = tmp_path / "backend_pandas.csv.gz"
    content = (
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20220101|00|01001|01009|1|2.5\n"
    )
    _write_gzip(file_path, content)

    df = mobility._read_pipe_file(
        str(file_path),
        dtype={"origen": "string", "destino": "string"},
    )

    assert all("[pyarrow]" not in str(dtype) for dtype in df.dtypes)


@pytest.mark.skipif(mobility_module.pl is None, reason="Polars is not installed")
def test_polars_backend_reads_arrow_backed_pandas(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="polars")

    file_path = tmp_path / "backend_polars.csv.gz"
    content = (
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20220101|00|01001|01009|1|2.5\n"
    )
    _write_gzip(file_path, content)

    df = mobility._read_pipe_file(str(file_path))

    assert isinstance(df, pd.DataFrame)
    assert any("[pyarrow]" in str(dtype) for dtype in df.dtypes)


def test_get_od_data_aggregates_when_activity_and_social_not_requested(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="pandas")

    file_path = tmp_path / "od_agg.csv.gz"
    content = (
        "fecha|periodo|origen|destino|actividad_origen|actividad_destino|residencia|renta|edad|sexo|viajes|viajes_km\n"
        "20220101|00|01001|01009|casa|frecuente|01|10-15|25-44|hombre|1|2\n"
        "20220101|00|01001|01009|trabajo_estudio|no_frecuente|01|>15|25-44|mujer|2|3\n"
    )
    _write_gzip(file_path, content)

    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_od_data(keep_activity=False, social_agg=False, return_df=True)

    assert list(df.columns) == [
        "date",
        "hour",
        "id_origin",
        "id_destination",
        "n_trips",
        "trips_total_length_km",
    ]
    assert len(df) == 1
    assert df.loc[0, "n_trips"] == 3
    assert df.loc[0, "trips_total_length_km"] == 5


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_get_od_data_version1_translates_headers_and_schema(
    monkeypatch,
    tmp_path,
    backend,
):
    mobility = _build_mobility(
        monkeypatch,
        tmp_path,
        backend=backend,
        version=1,
        start_date="2020-03-11",
        end_date="2020-03-11",
    )

    file_path = tmp_path / "od_v1_sample.txt.gz"
    content = (
        "\ufeffFECHA|PERIODO|ORIGEN|DESTINO|VIAJES|VIAJES_KM\n"
        "20200311|00|01001.0|01009.0|1.0|2.5\n"
    )
    _write_gzip(file_path, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_od_data(return_df=True)

    assert list(df.columns) == [
        "date",
        "hour",
        "id_origin",
        "id_destination",
        "n_trips",
        "trips_total_length_km",
    ]
    assert {"fecha", "periodo", "origen", "destino", "viajes", "viajes_km"}.isdisjoint(df.columns)
    assert df.loc[0, "date"] == "2020-03-11"
    assert df.loc[0, "id_origin"] == "01001"
    assert df.loc[0, "id_destination"] == "01009"


@pytest.mark.parametrize("backend", ["pandas", "arrow", "polars", "dask_fallback"])
def test_get_od_data_version1_keeps_and_translates_activity(
    monkeypatch,
    tmp_path,
    backend,
):
    if backend == "dask_fallback":
        mobility = _build_mobility_dask(
            monkeypatch, tmp_path, version=1, zones="districts"
        )
    else:
        mobility = _build_mobility(
            monkeypatch, tmp_path, backend=backend, version=1, zones="districts"
        )

    file_path = tmp_path / "od_v1_activity.txt.gz"
    content = (
        "fecha|origen|destino|actividad_origen|actividad_destino|residencia|edad|periodo|distancia|viajes|viajes_km\n"
        "20200311|01001|01009|trabajo|otros|01|25-44|00|1|2|3\n"
        "20200311|01001|01009|trabajo|otros|01|25-44|00|1|4|5\n"
        "20200311|01001|01009|casa|otros|01|25-44|00|1|1|2\n"
    )
    _write_gzip(file_path, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_od_data(keep_activity=True, social_agg=True, return_df=True)

    assert list(df.columns) == [
        "date",
        "hour",
        "id_origin",
        "id_destination",
        "activity_origin",
        "activity_destination",
        "n_trips",
        "trips_total_length_km",
    ]
    rows = {
        (row.activity_origin, row.activity_destination):
        (row.n_trips, row.trips_total_length_km)
        for row in df.itertuples(index=False)
    }
    assert rows == {
        ("work_or_study", "other"): (6, 8),
        ("home", "other"): (1, 2),
    }


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_get_od_data_version1_rejects_unavailable_municipality_activity(
    monkeypatch, tmp_path, backend
):
    mobility = _build_mobility(
        monkeypatch, tmp_path, backend=backend, version=1, zones="municipalities"
    )
    monkeypatch.setattr(
        mobility, "_donwload_helper", lambda *_: pytest.fail("download was attempted")
    )

    with pytest.raises(ValueError, match="municipality OD files do not contain activity"):
        mobility.get_od_data(keep_activity=True, return_df=True)


def test_get_od_data_keeps_activity_and_social_dimensions(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="pandas")

    file_path = tmp_path / "od_keep_dims.csv.gz"
    content = (
        "fecha|periodo|origen|destino|actividad_origen|actividad_destino|residencia|renta|edad|sexo|viajes|viajes_km\n"
        "20220101|00|01001|01009|casa|frecuente|01|10-15|25-44|hombre|1|2\n"
        "20220101|00|01001|01009|trabajo_estudio|no_frecuente|01|>15|25-44|mujer|2|3\n"
    )
    _write_gzip(file_path, content)

    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_od_data(keep_activity=True, social_agg=True, return_df=True)

    assert list(df.columns) == [
        "date",
        "hour",
        "id_origin",
        "id_destination",
        "activity_origin",
        "activity_destination",
        "income",
        "age",
        "gender",
        "n_trips",
        "trips_total_length_km",
    ]
    assert len(df) == 2
    assert set(df["activity_origin"]) == {"home", "work_or_study"}
    assert set(df["activity_destination"]) == {"other_frequent", "other_non_frequent"}
    assert set(df["gender"]) == {"male", "female"}


def test_polars_processes_multiple_od_files_in_one_result(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="polars")
    files = []
    for date, trips in (("20220101", "1.5"), ("20220102", "2.5")):
        file_path = tmp_path / f"od_{date}.csv.gz"
        _write_gzip(
            file_path,
            "fecha|periodo|origen|destino|viajes|viajes_km\n"
            f"{date}|00|01001|01009|{trips}|10\n",
        )
        files.append(str(file_path))

    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: files)
    saved = {}

    def fake_save(frame, _m_type):
        saved["is_polars"] = isinstance(frame, mobility_module.pl.DataFrame)

    monkeypatch.setattr(mobility, "_saving_parquet", fake_save)
    df = mobility.get_od_data(return_df=True)

    assert saved == {"is_polars": True}
    assert isinstance(df, pd.DataFrame)
    assert df["date"].tolist() == ["2022-01-01", "2022-01-02"]
    assert df["n_trips"].sum() == pytest.approx(4.0)


def test_polars_return_false_does_not_materialize_pandas(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="polars")
    file_path = tmp_path / "od_native_save.csv.gz"
    _write_gzip(
        file_path,
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20220101|00|01001|01009|1|2\n",
    )
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])
    monkeypatch.setattr(
        mobility,
        "_polars_to_pandas",
        lambda *_: pytest.fail("pandas materialization should not occur"),
    )

    saved = {}
    monkeypatch.setattr(
        mobility,
        "_saving_parquet",
        lambda frame, _m_type: saved.setdefault(
            "is_polars", isinstance(frame, mobility_module.pl.DataFrame)
        ),
    )

    assert mobility.get_od_data(return_df=False) is None
    assert saved == {"is_polars": True}


def test_saving_parquet_accepts_native_polars_frame(tmp_path):
    mobility = Mobility.__new__(Mobility)
    mobility.output_path = str(tmp_path)
    mobility.zones = "municipalities"
    mobility.start_date = "2022-01-01"
    mobility.end_date = "2022-01-01"
    mobility.version = 2
    frame = mobility_module.pl.DataFrame({"value": [1, 2]})

    mobility._saving_parquet(frame, "Viajes")

    output = tmp_path / "Viajes_municipalities_2022-01-01_2022-01-01_v2.parquet"
    assert pd.read_parquet(output)["value"].tolist() == [1, 2]


@pytest.mark.parametrize("backend", ["pandas", "arrow", "polars"])
def test_social_aggregation_preserves_flows_with_missing_demographics(
    monkeypatch,
    tmp_path,
    backend,
):
    mobility = _build_mobility(monkeypatch, tmp_path, backend=backend)

    file_path = tmp_path / f"od_social_missing_{backend}.csv.gz"
    content = (
        "fecha|periodo|origen|destino|actividad_origen|actividad_destino|residencia|renta|edad|sexo|viajes|viajes_km\n"
        "20220101|00|01001|01009|casa|frecuente|01|>15|NA|NA|10.5|100.25\n"
        "20220101|00|01001|01009|casa|frecuente|01|>15|25-44|hombre|20.5|200.75\n"
    )
    _write_gzip(file_path, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_od_data(social_agg=True, return_df=True)

    assert len(df) == 2
    assert df["n_trips"].sum() == pytest.approx(31.0)
    assert df["trips_total_length_km"].sum() == pytest.approx(301.0)

    unknown_demographics = df[df["age"].isna() & df["gender"].isna()]
    assert len(unknown_demographics) == 1
    assert unknown_demographics.iloc[0]["n_trips"] == pytest.approx(10.5)


def test_get_od_data_return_df_false_still_saves_file(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="pandas")

    file_path = tmp_path / "od_save.csv.gz"
    content = (
        "fecha|periodo|origen|destino|actividad_origen|actividad_destino|residencia|renta|edad|sexo|viajes|viajes_km\n"
        "20220101|00|01001|01009|casa|frecuente|01|10-15|25-44|hombre|1|2\n"
    )
    _write_gzip(file_path, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    saved = {}

    def fake_save(df, m_type):
        saved["rows"] = len(df)
        saved["m_type"] = m_type

    monkeypatch.setattr(mobility, "_saving_parquet", fake_save)

    result = mobility.get_od_data(keep_activity=False, social_agg=False, return_df=False)

    assert result is None
    assert saved == {"rows": 1, "m_type": "Viajes"}


def test_get_overnight_stays_data_raises_for_version1(monkeypatch, tmp_path):
    mobility = _build_mobility(
        monkeypatch,
        tmp_path,
        backend="pandas",
        version=1,
        start_date="2020-03-11",
        end_date="2020-03-11",
    )

    with pytest.raises(Exception, match="not available for version 1"):
        mobility.get_overnight_stays_data()


@pytest.mark.parametrize("backend", ["pandas", "polars"])
def test_get_number_of_trips_data_version1_adds_demographic_columns(
    monkeypatch,
    tmp_path,
    backend,
):
    mobility = _build_mobility(
        monkeypatch,
        tmp_path,
        backend=backend,
        version=1,
        start_date="2020-03-11",
        end_date="2020-03-11",
    )

    file_path = tmp_path / "trips_v1_sample.txt.gz"
    content = (
        "fecha|distrito|numero_viajes|personas\n"
        "20200311|01001.0|2.0|1.234\n"
    )
    _write_gzip(file_path, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_number_of_trips_data(return_df=True)

    assert {"date", "overnight_stay_area", "number_of_trips", "people", "age", "gender"}.issubset(df.columns)
    assert {"fecha", "distrito", "numero_viajes", "personas"}.isdisjoint(df.columns)
    assert df.loc[0, "date"] == "2020-03-11"
    assert df.loc[0, "overnight_stay_area"] == "01001"
    assert df.loc[0, "number_of_trips"] == "2"
    assert df.loc[0, "people"] == pytest.approx(1.234)
    assert pd.isna(df.loc[0, "age"])
    assert pd.isna(df.loc[0, "gender"])


def test_dask_fallback_overnight_stays_returns_correct_data(monkeypatch, tmp_path):
    mobility = _build_mobility_dask(monkeypatch, tmp_path, version=2)

    f1 = tmp_path / "overnight_dask_1.csv.gz"
    f2 = tmp_path / "overnight_dask_2.csv.gz"
    content = (
        "fecha|zona_residencia|zona_pernoctacion|personas\n"
        "20220101|01001|01009|56.789\n"
    )
    _write_gzip(f1, content)
    _write_gzip(f2, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(f1), str(f2)])

    df = mobility.get_overnight_stays_data(return_df=True)

    assert len(df) == 2
    assert set(df.columns) == {"date", "residence_area", "overnight_stay_area", "people"}
    assert all(val == pytest.approx(56.789) for val in df["people"].tolist())


def test_dask_fallback_number_of_trips_v2_returns_correct_data(monkeypatch, tmp_path):
    mobility = _build_mobility_dask(monkeypatch, tmp_path, version=2)

    f1 = tmp_path / "trips_v2_dask_1.csv.gz"
    f2 = tmp_path / "trips_v2_dask_2.csv.gz"
    content = (
        "fecha|zona_pernoctacion|edad|sexo|numero_viajes|personas\n"
        "20220101|01001|25-45|hombre|2+|128.457\n"
    )
    _write_gzip(f1, content)
    _write_gzip(f2, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(f1), str(f2)])

    df = mobility.get_number_of_trips_data(return_df=True)

    assert len(df) == 2
    assert set(df.columns) == {"date", "overnight_stay_area", "age", "gender", "number_of_trips", "people"}
    assert set(df["gender"]) == {"male"}
    assert all(val == pytest.approx(128.457) for val in df["people"].tolist())


def test_dask_fallback_number_of_trips_v1_returns_correct_data(monkeypatch, tmp_path):
    mobility = _build_mobility_dask(
        monkeypatch,
        tmp_path,
        version=1,
        start_date="2020-03-11",
        end_date="2020-03-11",
    )

    f1 = tmp_path / "trips_v1_dask_1.txt.gz"
    f2 = tmp_path / "trips_v1_dask_2.txt.gz"
    content = (
        "fecha|distrito|numero_viajes|personas\n"
        "20200311|01001|2|1.234\n"
    )
    _write_gzip(f1, content)
    _write_gzip(f2, content)
    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(f1), str(f2)])

    df = mobility.get_number_of_trips_data(return_df=True)

    assert len(df) == 2
    assert set(df.columns) == {"date", "overnight_stay_area", "number_of_trips", "people", "age", "gender"}
    assert all(val == pytest.approx(1.234) for val in df["people"].tolist())


def test_download_helper_logs_warnings_on_failed_download(monkeypatch, tmp_path, capsys):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="pandas")

    def fail_download(*_args, **_kwargs):
        raise RuntimeError("network failure")

    monkeypatch.setattr(utils, "download_file_if_not_existing", fail_download)

    files = mobility._donwload_helper("Viajes")
    captured = capsys.readouterr()

    assert files == []
    assert "[warn] Failed to download" in captured.out


def test_download_helper_records_pre_filter_acquisition_manifest(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path, backend="pandas")
    mobility.dates = ["2022-01-01", "2022-01-02"]

    def fake_download(_url, local_path):
        if "20220102" in local_path:
            raise RuntimeError("upstream unavailable")
        Path(local_path).write_bytes(b"source content")

    monkeypatch.setattr(utils, "download_file_if_not_existing", fake_download)

    files = mobility._donwload_helper("Viajes")
    manifest = mobility.get_acquisition_manifest("Viajes")

    assert len(files) == 1
    assert manifest["date"].tolist() == ["2022-01-01", "2022-01-02"]
    assert manifest["status"].tolist() == ["available", "failed"]
    assert manifest["coverage"].tolist() == ["unverified", "unknown"]
    assert manifest.loc[0, "local_path"] == files[0]
    assert "upstream unavailable" in manifest.loc[1, "error"]


def test_zone_geodataframe_is_cached_after_first_load(monkeypatch, tmp_path):
    output_dir = tmp_path / "zones_cache"
    output_dir.mkdir()
    (output_dir / "nombres_municipios.csv").write_text("ID|name\n01001|Town A\n", encoding="utf-8")
    (output_dir / "poblacion_municipios.csv").write_text("ID|population\n01001|1234\n", encoding="utf-8")
    (output_dir / "zonificacion_municipios.shp").write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(
        utils,
        "available_zoning_data",
        lambda *_: pd.DataFrame(
            {"link": [f"https://example.org/{name}" for name in [
                "nombres_municipios.csv",
                "poblacion_municipios.csv",
                "zonificacion_municipios.shp",
            ]]}
        ),
    )
    monkeypatch.setattr(utils, "download_file_if_not_existing", lambda *_: None)

    reads = {"count": 0}

    def fake_read_file(path, *args, **kwargs):
        reads["count"] += 1
        if str(path).endswith("zonificacion_municipios.shp"):
            return gpd.GeoDataFrame({"ID": ["01001"], "geometry": [Point(0, 0)]}, crs="EPSG:4326")
        raise FileNotFoundError(path)

    monkeypatch.setattr(gpd, "read_file", fake_read_file)
    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", lambda *_args, **_kwargs: None)

    zones = Zones(zones="municipalities", version=2, output_directory=str(output_dir))

    first = zones.get_zone_geodataframe()
    second = zones.get_zone_geodataframe()

    assert reads["count"] == 1
    assert first is second


def test_get_zone_relations_version1_returns_sets(monkeypatch, tmp_path):
    out_dir = tmp_path / "z1_relations"
    out_dir.mkdir()

    (out_dir / "relaciones_municipio_mitma.csv").write_text(
        "municipio|municipio_mitma\n"
        "28079|28079_M1\n"
        "28080|28079_M1\n",
        encoding="utf-8",
    )
    (out_dir / "relaciones_distrito_mitma.csv").write_text(
        "distrito|distrito_mitma|municipio_mitma\n"
        "2807901|D1|28079_M1\n"
        "2807902|D2|28079_M1\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        utils,
        "available_zoning_data",
        lambda *_: pd.DataFrame(
            {
                "link": [
                    "https://example.org/relaciones_municipio_mitma.csv",
                    "https://example.org/relaciones_distrito_mitma.csv",
                ]
            }
        ),
    )
    monkeypatch.setattr(utils, "download_file_if_not_existing", lambda *_: None)

    zones = Zones(zones="municipalities", version=1, output_directory=str(out_dir))
    df = zones.get_zone_relations()

    assert "28079_M1" in df.index
    assert df.loc["28079_M1", "municipalities"] == {"28079", "28080"}
    assert df.loc["28079_M1", "census_districts"] == {"2807901", "2807902"}
    assert df.loc["28079_M1", "districts_mitma"] == {"D1", "D2"}


def test_zone_geodataframe_cache_preserves_id_index_contract(monkeypatch, tmp_path):
    output_dir = tmp_path / "zones_cache_contract"
    output_dir.mkdir()
    cache_path = output_dir / "municipios_2.geojson"
    cache_path.write_text("placeholder", encoding="utf-8")

    monkeypatch.setattr(utils, "available_zoning_data", lambda *_: pd.DataFrame({"link": []}))
    cached = gpd.GeoDataFrame(
        {"id": ["01001", "01002"], "name": ["A", "B"], "geometry": [Point(0, 0), Point(1, 1)]},
        crs="EPSG:4326",
    )
    monkeypatch.setattr(gpd, "read_file", lambda *_args, **_kwargs: cached)

    zones = Zones(zones="municipalities", version=2, output_directory=str(output_dir))
    gdf = zones.get_zone_geodataframe()

    assert gdf.index.name == "id"
    assert gdf.index.tolist() == ["01001", "01002"]
    assert "id" not in gdf.columns


def test_get_network_mapping_deduplicates_identical_relations_and_filters_nodes(
    monkeypatch, tmp_path
):
    zones = Zones(zones="districts", version=2, output_directory=str(tmp_path))
    monkeypatch.setattr(
        zones,
        "get_zone_relations",
        lambda: pd.DataFrame(
            {
                "districts_mitma": ["D2", "D1", "D1", "D3"],
                "municipalities": ["28080", "28079", "28079", "28081"],
            }
        ),
    )

    mapping = zones.get_network_mapping(
        "districts_mitma", "municipalities", source_ids=["D2", "D1"]
    )

    assert mapping.to_dict("records") == [
        {"source_id": "D1", "target_id": "28079"},
        {"source_id": "D2", "target_id": "28080"},
    ]


def test_get_network_mapping_rejects_ambiguous_or_incomplete_relations(monkeypatch, tmp_path):
    zones = Zones(zones="districts", version=2, output_directory=str(tmp_path))
    monkeypatch.setattr(
        zones,
        "get_zone_relations",
        lambda: pd.DataFrame(
            {
                "districts_mitma": ["D1", "D1", "D2"],
                "municipalities": ["28079", "28080", None],
            }
        ),
    )

    with pytest.raises(ValueError, match="without a target"):
        zones.get_network_mapping("districts_mitma", "municipalities")

    monkeypatch.setattr(
        zones,
        "get_zone_relations",
        lambda: pd.DataFrame(
            {
                "districts_mitma": ["D1", "D1"],
                "municipalities": ["28079", "28080"],
            }
        ),
    )
    with pytest.raises(ValueError, match="not one-to-one"):
        zones.get_network_mapping("districts_mitma", "municipalities")


def test_get_province_mapping_derives_ine_province_and_validates_codes(monkeypatch, tmp_path):
    zones = Zones(zones="districts", version=2, output_directory=str(tmp_path))
    monkeypatch.setattr(
        zones,
        "get_zone_relations",
        lambda: pd.DataFrame(
            {
                "districts_mitma": ["D1", "D2"],
                "municipalities": ["28079", "08001"],
            }
        ),
    )
    mapping = zones.get_province_mapping(source_ids=["D1", "D2"])
    assert mapping.to_dict("records") == [
        {"source_id": "D1", "target_id": "28"},
        {"source_id": "D2", "target_id": "08"},
    ]

    monkeypatch.setattr(
        zones,
        "get_zone_relations",
        lambda: pd.DataFrame(
            {"districts_mitma": ["D1"], "municipalities": ["not-an-ine-code"]}
        ),
    )
    with pytest.raises(ValueError, match="five-digit INE"):
        zones.get_province_mapping()


def test_province_mapping_integrates_with_network_and_drops_internalized_flows(
    monkeypatch, tmp_path
):
    zones = Zones(zones="districts", version=2, output_directory=str(tmp_path))
    monkeypatch.setattr(
        zones,
        "get_zone_relations",
        lambda: pd.DataFrame(
            {
                "districts_mitma": ["D1", "D2", "D3"],
                "municipalities": ["28079", "28080", "08001"],
            }
        ),
    )
    district_network = build_network(
        pd.DataFrame(
            {
                "id_origin": ["D1", "D2"],
                "id_destination": ["D2", "D3"],
                "n_trips": [4.0, 7.0],
            }
        )
    )

    province_network = aggregate_network(
        district_network,
        zones.get_province_mapping(source_ids=district_network.node_ids),
        self_loops="drop",
    )

    assert province_network.node_ids.tolist() == ["08", "28"]
    assert province_network.total_weight == pytest.approx(7.0)
    assert province_network.to_edge_table().to_dicts() == [
        {"id_origin": "28", "id_destination": "08", "weight": 7.0}
    ]
    assert province_network.audit()["provenance"]["spatial"]["dropped_target_self_loop_weight"] == pytest.approx(4.0)


def test_polars_daily_scans_align_reordered_measure_columns_and_manifest(tmp_path):
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text(
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20240101|0|A|B|1|2\n"
    )
    second.write_text(
        "fecha|periodo|origen|destino|viajes_km|viajes\n"
        "20240102|0|A|B|400|3\n"
    )
    mobility = object.__new__(Mobility)
    mobility.backend = "polars"
    result = mobility._process_od_files_polars(
        [str(first), str(second)], False, False
    )
    assert result["n_trips"].tolist() == [1.0, 3.0]
    assert result["trips_total_length_km"].tolist() == [2.0, 400.0]

    mobility._acquisition_manifests = {}
    mobility._set_acquisition_manifest(
        "Viajes",
        [
            [day, "Viajes", "available", "unverified", str(path), None]
            for day, path in [("2024-01-01", first), ("2024-01-02", second)]
        ],
    )
    mobility._finalize_od_manifest(
        "Viajes", [str(first), str(second)], processed_success=True
    )
    assert mobility.get_acquisition_manifest("Viajes")["parse_status"].tolist() == [
        "valid", "valid"
    ]


def test_polars_daily_scans_align_overnight_and_trip_count_columns(tmp_path):
    mobility = object.__new__(Mobility)
    mobility.backend = "polars"
    mobility.version = 2
    overnight_a = tmp_path / "overnight_a.csv"
    overnight_b = tmp_path / "overnight_b.csv"
    overnight_a.write_text(
        "fecha|zona_residencia|zona_pernoctacion|personas\n"
        "20240101|A|B|2\n"
    )
    overnight_b.write_text(
        "fecha|personas|zona_residencia|zona_pernoctacion\n"
        "20240102|7|C|D\n"
    )
    overnight = mobility._process_overnight_files_polars(
        [str(overnight_a), str(overnight_b)]
    )
    assert overnight["people"].tolist() == [2.0, 7.0]
    assert overnight["residence_area"].tolist() == ["A", "C"]

    trips_a = tmp_path / "trips_a.csv"
    trips_b = tmp_path / "trips_b.csv"
    trips_a.write_text(
        "fecha|zona_pernoctacion|numero_viajes|personas\n"
        "20240101|A|1|2\n"
    )
    trips_b.write_text(
        "fecha|personas|numero_viajes|zona_pernoctacion\n"
        "20240102|9|2|B\n"
    )
    trips = mobility._process_number_of_trips_files_polars(
        [str(trips_a), str(trips_b)]
    )
    assert trips["people"].tolist() == [2.0, 9.0]
    assert trips["overnight_stay_area"].tolist() == ["A", "B"]


def test_polars_missing_id_marker_is_not_a_zone_or_a_valid_source_day(tmp_path):
    source = tmp_path / "missing_id.csv"
    source.write_text(
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20240101|0| NA |B|1|2\n"
    )
    mobility = object.__new__(Mobility)
    mobility.backend = "polars"
    assert mobility._process_od_files_polars([str(source)], False, False) is None
    mobility._acquisition_manifests = {}
    mobility._set_acquisition_manifest(
        "Viajes",
        [["2024-01-01", "Viajes", "available", "unverified", str(source), None]],
    )
    with pytest.warns(RuntimeWarning, match="OD source parsing failed"):
        mobility._finalize_od_manifest("Viajes", [str(source)], processed_success=False)
    assert mobility.get_acquisition_manifest("Viajes")["parse_status"].tolist() == [
        "failed"
    ]


def test_polars_bad_daily_file_keeps_valid_day_and_marks_only_bad_day_failed(tmp_path):
    good = tmp_path / "good.csv"
    bad = tmp_path / "bad.csv"
    header = "fecha|periodo|origen|destino|viajes|viajes_km\n"
    good.write_text(header + "20240101|0|A|B|1|2\n")
    bad.write_text(header + "20240102|0|A|B|3|4|extra\n")
    mobility = object.__new__(Mobility)
    mobility.backend = "polars"
    result = mobility._process_od_files_polars([str(good), str(bad)], False, False)
    assert result["n_trips"].tolist() == [1.0]
    mobility._acquisition_manifests = {}
    mobility._set_acquisition_manifest(
        "Viajes",
        [
            [day, "Viajes", "available", "unverified", str(path), None]
            for day, path in [("2024-01-01", good), ("2024-01-02", bad)]
        ],
    )
    with pytest.warns(RuntimeWarning, match="OD source parsing failed"):
        mobility._finalize_od_manifest(
            "Viajes", [str(good), str(bad)], processed_success=True
        )
    assert mobility.get_acquisition_manifest("Viajes")["parse_status"].tolist() == [
        "valid", "failed"
    ]


def test_zones_rechecks_an_existing_empty_source_file(monkeypatch, tmp_path):
    source = tmp_path / "relacion_ine_zonificacionMitma.csv"
    source.write_bytes(b"")
    monkeypatch.setattr(
        utils,
        "available_zoning_data",
        lambda *_: pd.DataFrame({"link": ["https://example.org/" + source.name]}),
    )
    calls = []

    def refresh(_url, path):
        calls.append(path)
        Path(path).write_bytes(b"restored")

    monkeypatch.setattr(utils, "download_file_if_not_existing", refresh)
    zones = Zones(zones="municipalities", version=2, output_directory=str(tmp_path))
    zones._ensure_zoning_files_downloaded()
    assert calls == [str(source)]
    assert source.read_bytes() == b"restored"


def test_network_mapping_validates_only_requested_source_ids():
    zones = object.__new__(Zones)
    zones.get_zone_relations = lambda: pd.DataFrame(
        {
            "source": ["A", "B", "C", "C"],
            "target": ["X", None, "Y", "Z"],
        }
    )
    assert zones.get_network_mapping(
        "source", "target", source_ids=["A"]
    ).to_dict("records") == [{"source_id": "A", "target_id": "X"}]
    with pytest.raises(ValueError, match="without a target"):
        zones.get_network_mapping("source", "target")
    with pytest.raises(ValueError, match="not one-to-one"):
        zones.get_network_mapping("source", "target", source_ids=["C"])


@pytest.mark.parametrize("backend", ["pandas", "polars"])
@pytest.mark.parametrize(
    "invalid_row",
    [
        "20240230|12|A|B|3|4",
        "20240229|bad|A|B|3|4",
        "20240229|24|A|B|3|4",
    ],
)
def test_od_drops_invalid_calendar_dates_and_hours_and_fails_manifest(
    tmp_path, backend, invalid_row
):
    source = tmp_path / "od.csv"
    source.write_text(
        "fecha|periodo|origen|destino|viajes|viajes_km\n"
        "20240229|12|A|B|2|5\n"
        + invalid_row + "\n"
    )
    mobility = object.__new__(Mobility)
    mobility.backend = backend
    if backend == "polars":
        frame = mobility._process_od_files_polars(
            [str(source)], False, False, as_pandas=False
        )
        rows = frame.to_dicts()
    else:
        frame = mobility._process_single_od_file(str(source), False, False)
        rows = frame.to_dict("records")
    assert len(rows) == 1
    assert rows[0]["date"] == "2024-02-29"
    assert rows[0]["hour"] == 12
    assert rows[0]["n_trips"] == 2.0

    mobility._acquisition_manifests = {}
    mobility._set_acquisition_manifest(
        "Viajes",
        [["2024-02-29", "Viajes", "available", "unverified", str(source), None]],
    )
    with pytest.warns(RuntimeWarning, match="OD source parsing failed"):
        mobility._finalize_od_manifest(
            "Viajes", [str(source)], processed_success=True
        )
    assert mobility.get_acquisition_manifest("Viajes")["parse_status"].tolist() == [
        "failed"
    ]
