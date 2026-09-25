import io
import gzip
import os
from pathlib import Path

import pandas as pd
import pytest

from pyspainmobility.utils import utils


class _BytesContext(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()


class _HTTPBytesResponse:
    def __init__(self, payload: bytes, status: int = 200):
        self.payload = io.BytesIO(payload)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self, size=-1):
        return self.payload.read(size)


def test_zone_assert_accepts_documented_municipal_alias():
    utils.zone_assert("municipal", version=2)


def test_zone_assert_rejects_invalid_value():
    with pytest.raises(ValueError, match="zone must be one of the following"):
        utils.zone_assert("invalid-zone", version=2)


def test_version_assert_rejects_invalid_value():
    with pytest.raises(ValueError, match="version must be 1 or 2"):
        utils.version_assert(3)


@pytest.mark.parametrize("invalid", [True, 1.0, "1"])
def test_version_assert_rejects_values_that_only_compare_equal_to_an_int(invalid):
    with pytest.raises(ValueError, match="version must be 1 or 2"):
        utils.version_assert(invalid)


@pytest.mark.parametrize("invalid", [None, "2024-02-30", "2024-13-01", "2024-1-01"])
def test_date_format_assert_rejects_invalid_calendar_dates(invalid):
    with pytest.raises(ValueError, match="date must"):
        utils.date_format_assert(invalid)


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


def test_available_mobility_data_detects_versioned_v2_downloaded_file(monkeypatch, tmp_path):
    filename = "20230101_Viajes_municipios.csv.gz"
    versioned = tmp_path / "20230101_Viajes_municipios_v2.csv.gz"
    versioned.write_bytes(b"versioned v2")

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

    monkeypatch.setattr(utils, "urlopen", lambda *_: _BytesContext(rss_xml))
    monkeypatch.setattr(utils, "data_directory", str(tmp_path))

    df = utils.available_mobility_data(version=2)

    assert len(df) == 1
    assert bool(df.iloc[0]["downloaded"]) is True
    assert Path(df.iloc[0]["local_path"]) == versioned


def test_available_mobility_data_detects_versioned_v1_downloaded_file(monkeypatch, tmp_path):
    filename = "20200311_maestra_1_mitma_municipio.txt.gz"
    versioned = tmp_path / "20200311_maestra_1_mitma_municipio_v1.txt.gz"
    versioned.write_bytes(b"versioned v1")

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

    monkeypatch.setattr(utils, "urlopen", lambda *_: _BytesContext(rss_xml))
    monkeypatch.setattr(utils, "data_directory", str(tmp_path))

    df = utils.available_mobility_data(version=1)

    assert len(df) == 1
    assert bool(df.iloc[0]["downloaded"]) is True
    assert Path(df.iloc[0]["local_path"]) == versioned


def test_available_mobility_data_prefers_raw_name_over_versioned(monkeypatch, tmp_path):
    filename = "20230101_Viajes_municipios.csv.gz"
    raw = tmp_path / filename
    raw.write_bytes(b"raw")
    versioned = tmp_path / "20230101_Viajes_municipios_v2.csv.gz"
    versioned.write_bytes(b"versioned")

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

    monkeypatch.setattr(utils, "urlopen", lambda *_: _BytesContext(rss_xml))
    monkeypatch.setattr(utils, "data_directory", str(tmp_path))

    df = utils.available_mobility_data(version=2)

    assert len(df) == 1
    assert bool(df.iloc[0]["downloaded"]) is True
    assert Path(df.iloc[0]["local_path"]) == raw


def test_available_mobility_data_reports_false_when_no_file_present(monkeypatch, tmp_path):
    filename = "20230102_Viajes_municipios.csv.gz"
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

    monkeypatch.setattr(utils, "urlopen", lambda *_: _BytesContext(rss_xml))
    monkeypatch.setattr(utils, "data_directory", str(tmp_path))

    df = utils.available_mobility_data(version=2)

    assert len(df) == 1
    assert bool(df.iloc[0]["downloaded"]) is False
    assert df.iloc[0]["local_path"] is None


def test_available_mobility_data_multi_entry_mixed_download_status(monkeypatch, tmp_path):
    f1 = "20230101_Viajes_municipios.csv.gz"
    f2 = "20230102_Viajes_municipios.csv.gz"
    f3 = "20230103_Viajes_municipios.csv.gz"
    (tmp_path / "20230101_Viajes_municipios_v2.csv.gz").write_bytes(b"v2")
    (tmp_path / f3).write_bytes(b"raw")

    rss_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss>
  <channel>
    <item><title>{f1}</title><link>https://example.org/{f1}</link><pubDate>x</pubDate></item>
    <item><title>{f2}</title><link>https://example.org/{f2}</link><pubDate>x</pubDate></item>
    <item><title>{f3}</title><link>https://example.org/{f3}</link><pubDate>x</pubDate></item>
  </channel>
</rss>
""".encode("utf-8")

    monkeypatch.setattr(utils, "urlopen", lambda *_: _BytesContext(rss_xml))
    monkeypatch.setattr(utils, "data_directory", str(tmp_path))

    df = utils.available_mobility_data(version=2).sort_values("data_ymd").reset_index(drop=True)

    assert bool(df.loc[0, "downloaded"]) is True
    assert str(df.loc[0, "local_path"]).endswith("_v2.csv.gz")
    assert bool(df.loc[1, "downloaded"]) is False
    assert pd.isna(df.loc[1, "local_path"])
    assert bool(df.loc[2, "downloaded"]) is True
    assert str(df.loc[2, "local_path"]).endswith("20230103_Viajes_municipios.csv.gz")


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
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
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


def test_download_file_if_not_existing_supports_filename_only_path(monkeypatch, tmp_path):
    payload = b"just-file"
    output_file = tmp_path / "standalone.bin"
    monkeypatch.setattr(utils, "urlopen", lambda *_: _HTTPBytesResponse(payload, status=200))
    monkeypatch.chdir(tmp_path)

    utils.download_file_if_not_existing("https://example.org/standalone.bin", "standalone.bin")
    assert output_file.read_bytes() == payload


def test_download_replaces_corrupt_cached_gzip(monkeypatch, tmp_path):
    output_file = tmp_path / "daily.csv.gz"
    output_file.write_bytes(b"incomplete gzip payload")
    payload = gzip.compress(b"fecha|viajes\n20240101|3\n")
    monkeypatch.setattr(utils, "urlopen", lambda *_: _HTTPBytesResponse(payload))

    utils.download_file_if_not_existing(
        "https://example.org/daily.csv.gz", str(output_file)
    )

    assert gzip.decompress(output_file.read_bytes()) == b"fecha|viajes\n20240101|3\n"


def test_validated_gzip_cache_skips_repeat_decompression_and_checks_changes(
    monkeypatch, tmp_path
):
    output_file = tmp_path / "daily.csv.gz"
    payload = gzip.compress(b"fecha|viajes\n20240101|3\n")
    monkeypatch.setattr(utils, "urlopen", lambda *_: _HTTPBytesResponse(payload))
    url = "https://example.org/daily.csv.gz"
    utils.download_file_if_not_existing(url, str(output_file))

    original_open = utils.gzip.open
    calls = []

    def counting_open(*args, **kwargs):
        calls.append(args[0])
        return original_open(*args, **kwargs)

    monkeypatch.setattr(utils.gzip, "open", counting_open)
    utils.download_file_if_not_existing(url, str(output_file))
    assert calls == []

    output_file.write_bytes(b"corrupt cache")
    utils.download_file_if_not_existing(url, str(output_file))
    assert calls
    assert gzip.decompress(output_file.read_bytes()) == b"fecha|viajes\n20240101|3\n"

    original_stat = output_file.stat()
    output_file.write_bytes(b"x" * len(payload))
    os.utime(
        output_file,
        ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns),
    )
    utils.download_file_if_not_existing(url, str(output_file), verify_cache=True)
    assert gzip.decompress(output_file.read_bytes()) == b"fecha|viajes\n20240101|3\n"


def test_download_interruption_keeps_final_path_and_removes_temporary_file(
    monkeypatch, tmp_path
):
    output_file = tmp_path / "daily.csv.gz"
    output_file.write_bytes(b"old corrupt cache")

    class InterruptedResponse(_HTTPBytesResponse):
        def __init__(self):
            super().__init__(b"partial")
            self.calls = 0

        def read(self, size=-1):
            self.calls += 1
            if self.calls == 2:
                raise OSError("connection interrupted")
            return super().read(size)

    monkeypatch.setattr(utils, "urlopen", lambda *_: InterruptedResponse())
    with pytest.raises(OSError, match="connection interrupted"):
        utils.download_file_if_not_existing(
            "https://example.org/daily.csv.gz", str(output_file)
        )

    assert output_file.read_bytes() == b"old corrupt cache"
    assert list(tmp_path.glob(".pyspainmobility-*")) == []
