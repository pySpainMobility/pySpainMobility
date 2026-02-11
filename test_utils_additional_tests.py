import io
from pathlib import Path

import pytest

from pyspainmobility.utils import utils


class _BytesContext(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class _HTTPBytesResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self.payload = payload
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.payload


def test_zone_assert_accepts_documented_municipal_alias():
    utils.zone_assert("municipal", version=2)


def test_zone_normalization_is_case_insensitive_for_aliases():
    assert utils.zone_normalization("MUNICIPAL") == "municipios"


def test_available_mobility_data_marks_existing_file_as_downloaded(monkeypatch, tmp_path):
    filename = "20230101_Viajes_municipios.csv.gz"
    existing_file = tmp_path / filename
    existing_file.write_bytes(b"already downloaded")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss>
  <channel>
    <item>
      <title>{filename}</title>
      <link>https://example.org/{filename}</link>
      <pubDate>Tue, 10 Feb 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".encode("utf-8")

    def fake_urlopen(_url):
        return _BytesContext(rss_xml)

    monkeypatch.setattr(utils, "urlopen", fake_urlopen)
    monkeypatch.setattr(utils, "data_directory", str(tmp_path))

    df = utils.available_mobility_data(version=2)

    assert len(df) == 1
    assert bool(df.iloc[0]["downloaded"]) is True
    assert Path(df.iloc[0]["local_path"]) == existing_file


def test_available_zoning_data_rejects_luas_for_version1():
    with pytest.raises(Exception, match="not a valid zone for version 1"):
        utils.available_zoning_data(version=1, zone="gaus")


def test_available_zoning_data_zone_none_returns_all_zoning_entries(monkeypatch):
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss>
  <channel>
    <item>
      <title>zoning municipios</title>
      <link>https://example.org/zonificacion_municipios.shp</link>
      <pubDate>Tue, 10 Feb 2026 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>relation</title>
      <link>https://example.org/relacion_ine_zonificacionMitma.csv</link>
      <pubDate>Tue, 10 Feb 2026 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>irrelevant</title>
      <link>https://example.org/unrelated_file.csv</link>
      <pubDate>Tue, 10 Feb 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".encode("utf-8")

    monkeypatch.setattr(utils, "urlopen", lambda *_: _BytesContext(rss_xml))
    df = utils.available_zoning_data(version=2, zone=None)

    assert set(df["filename"]) == {
        "zonificacion_municipios.shp",
        "relacion_ine_zonificacionMitma.csv",
    }


def test_mobility_type_normalization_handles_aliases():
    assert utils.mobility_type_normalization("od", version=2) == "Viajes"
    assert utils.mobility_type_normalization("origin-destination", version=2) == "Viajes"
    assert utils.mobility_type_normalization("os", version=2) == "Pernoctaciones"
    assert utils.mobility_type_normalization("nt", version=2) == "Personas"


def test_mobility_type_normalization_rejects_overnight_for_v1():
    with pytest.raises(Exception, match="not a valid mobility type for version 1"):
        utils.mobility_type_normalization("os", version=1)


def test_get_dates_between_is_inclusive():
    dates = utils.get_dates_between("2022-01-01", "2022-01-03")
    assert dates == ["2022-01-01", "2022-01-02", "2022-01-03"]


def test_date_format_assert_rejects_invalid_format():
    with pytest.raises(AssertionError, match="YYYY-MM-DD"):
        utils.date_format_assert("2022/01/01")


def test_download_file_if_not_existing_writes_file(monkeypatch, tmp_path):
    output_file = tmp_path / "payload.bin"
    payload = b"downloaded-content"

    monkeypatch.setattr(utils, "urlopen", lambda *_: _HTTPBytesResponse(payload, status=200))

    utils.download_file_if_not_existing("https://example.org/payload.bin", str(output_file))

    assert output_file.read_bytes() == payload


def test_download_file_if_not_existing_skips_existing_non_empty(monkeypatch, tmp_path):
    output_file = tmp_path / "already.bin"
    output_file.write_bytes(b"existing")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("urlopen should not be called for an existing non-empty file")

    monkeypatch.setattr(utils, "urlopen", fail_if_called)

    utils.download_file_if_not_existing("https://example.org/already.bin", str(output_file))
    assert output_file.read_bytes() == b"existing"


def test_download_file_if_not_existing_replaces_empty_file(monkeypatch, tmp_path):
    output_file = tmp_path / "empty.bin"
    output_file.write_bytes(b"")
    payload = b"fresh"

    monkeypatch.setattr(utils, "urlopen", lambda *_: _HTTPBytesResponse(payload, status=200))

    utils.download_file_if_not_existing("https://example.org/empty.bin", str(output_file))
    assert output_file.read_bytes() == payload
