import gzip

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

import pyspainmobility.mobility.mobility as mobility_module
from pyspainmobility.mobility.mobility import Mobility
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
    )
    monkeypatch.setattr(mobility, "_saving_parquet", lambda *_: None)
    return mobility


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
    assert {"census_sections", "municipalities", "municipalities_mitma"}.issubset(df.columns)
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


def test_get_overnight_stays_data_normalizes_headers_and_ids(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path)

    file_path = tmp_path / "overnight_sample.csv.gz"
    content = (
        "\ufefffecha|zona_residencia|zona_pernoctacion|personas\n"
        "20220101|01001.0|01009.0|42\n"
    )
    _write_gzip(file_path, content)

    monkeypatch.setattr(mobility, "_donwload_helper", lambda *_: [str(file_path)])

    df = mobility.get_overnight_stays_data(return_df=True)

    assert list(df.columns) == ["date", "residence_area", "overnight_stay_area", "people"]
    assert df.loc[0, "residence_area"] == "01001"
    assert df.loc[0, "overnight_stay_area"] == "01009"


def test_get_number_of_trips_data_normalizes_headers_ids_and_gender(monkeypatch, tmp_path):
    mobility = _build_mobility(monkeypatch, tmp_path)

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


def test_numeric_parser_removes_unambiguous_dot_grouping_separators():
    converted = Mobility._to_numeric(pd.Series(["1.234.567", "2.000"]), strip_thousands=True)
    assert converted.tolist() == [1234567, 2000]

    unchanged_decimal = Mobility._to_numeric(pd.Series(["128.457"]), strip_thousands=True)
    assert unchanged_decimal.tolist() == [128.457]


def test_backend_validation_rejects_unknown_backend(monkeypatch, tmp_path):
    monkeypatch.setattr(utils, "zone_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "version_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "date_format_assert", lambda *args, **kwargs: None)
    monkeypatch.setattr(utils, "get_dates_between", lambda *_: ["2022-01-01"])
    monkeypatch.setattr(utils, "get_valid_dates", lambda *_: ["2022-01-01", "2022-01-02"])
    monkeypatch.setattr(utils, "get_data_directory", lambda: str(tmp_path / "default_data"))

    with pytest.raises(ValueError, match="backend must be either 'arrow' or 'pandas'"):
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


def test_get_number_of_trips_data_version1_adds_demographic_columns(monkeypatch, tmp_path):
    mobility = _build_mobility(
        monkeypatch,
        tmp_path,
        backend="pandas",
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
    assert df.loc[0, "date"] == "2020-03-11"
    assert df.loc[0, "overnight_stay_area"] == "01001"
    assert df.loc[0, "number_of_trips"] == "2"
    assert pd.isna(df.loc[0, "age"])
    assert pd.isna(df.loc[0, "gender"])


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
