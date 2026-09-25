import os

import pandas as pd
import xml.etree.ElementTree as ET
import re
from urllib.request import urlopen
import zipfile
import gzip
import json
import tempfile
from datetime import date as calendar_date
from numbers import Integral
from os.path import expanduser
from urllib.request import urlopen, Request      


data_directory = os.path.join(expanduser("~"), 'data')

def available_mobility_data(version: int = 2) -> pd.DataFrame:
    version_assert(version)

    url = None

    if version == 1:
        url = 'https://opendata-movilidad.mitma.es/RSS.xml'
    elif version == 2:
        url = 'https://movilidad-opendata.mitma.es/RSS.xml'

    data = []

    with urlopen(url) as f:
        tree = ET.parse(f)
        for item in tree.getroot()[0].findall('item'):
            title = str(item.findtext('title')).strip()
            link = item.findtext('link')
            pubdate = item.findtext('pubDate')
            file_extension = title[title.find('.') + 1:]
            tmp_date = link.split('/')[-1]
            try:
                if bool(re.match(r'^\d+$', str(tmp_date[:6]))):
                    date_ym = tmp_date[:4] + '-' + tmp_date[4:6]
                else:
                    date_ym = None
                if bool(re.match(r'^\d+$', str(tmp_date[6:8]))):
                    date_ymd = tmp_date[:4] + '-' + tmp_date[4:6] + '-' + tmp_date[6:8]
                else:
                    date_ymd = None
            except:
                date_ym = None
                date_ymd = None

            # Check both the raw RSS filename and the library's internal
            # versioned filename pattern (e.g. *_v2.csv.gz).
            local_path = os.path.join(data_directory, tmp_date)
            local_path_versioned = None
            for ext in (".csv.gz", ".txt.gz"):
                if tmp_date.endswith(ext):
                    stem = tmp_date[: -len(ext)]
                    local_path_versioned = os.path.join(
                        data_directory, f"{stem}_v{version}{ext}"
                    )
                    break

            if os.path.exists(local_path):
                downloaded = True
                valid_path = local_path
            elif local_path_versioned and os.path.exists(local_path_versioned):
                downloaded = True
                valid_path = local_path_versioned
            else:
                downloaded = False
                valid_path = None


            data.append([link, pubdate, file_extension, date_ym, date_ymd, valid_path, downloaded])

    df = pd.DataFrame(data, columns=['link', 'pub_date', 'file_extension', 'data_ym', 'data_ymd', 'local_path', 'downloaded'])
    df.dropna(subset = ['data_ym'], inplace=True)
    return df

def unzip_file(file: str, destination: str) -> None:
    """
    Unzip the file to the destination directory.
    """
    with zipfile.ZipFile(file, 'r') as zip_ref:
        zip_ref.extractall(destination)
        print(f'Unzipped {file} to {destination}')

def available_zoning_data(version: int = 2, zone: str = None) -> pd.DataFrame:
    version_assert(version)
    normalized_zone = None
    if zone is not None:
        zone_assert(zone, version)
        normalized_zone = zone_normalization(zone)

    url = None

    if version == 1:
        url = 'https://opendata-movilidad.mitma.es/RSS.xml'
    elif version == 2:
        url = 'https://movilidad-opendata.mitma.es/RSS.xml'

    data = []

    relation_files = {
        "relacion_ine_zonificacionMitma.csv",
        "relaciones_municipio_mitma.csv",
        "relaciones_distrito_mitma.csv",
    }
    if normalized_zone is None:
        zone_files_pattern = (
            r"(zonificacion_(municipios|distritos|gaus)\..*)|"
            r"(poblacion_(municipios|distritos|gaus)\..*)|"
            r"(nombres_(municipios|distritos|gaus)\..*)"
        )
    else:
        zone_files_pattern = (
            rf"(zonificacion_{normalized_zone}\..*)|"
            rf"(poblacion_{normalized_zone}\..*)|"
            rf"(nombres_{normalized_zone}\..*)"
        )

    with urlopen(url) as f:
        tree = ET.parse(f)
        # link, file_extension, data_ym, data_ymd, local_path, downloaded
        for item in tree.getroot()[0].findall('item'):
            link = item.findtext('link')
            pubdate = item.findtext('pubDate')
            tmp_date = link.split('/')[-1]
            is_relation_file = tmp_date in relation_files
            is_zone_specific_file = bool(re.fullmatch(zone_files_pattern, tmp_date))
            if is_relation_file or is_zone_specific_file:
                data.append([link, pubdate, tmp_date])

    return pd.DataFrame(data, columns=['link', 'pub_date', 'filename'])

def zone_assert(zone: str = None, version: int = 2) -> None:
    normalized_zone = str(zone).lower()
    allowed_zones = [
        "districts", "dist", "distr", "distritos",
        "municipalities", "muni", "municip", "municipal", "municipios",
        "lua", "large_urban_areas", "gau", "gaus", "grandes_areas_urbanas"
    ]
    if normalized_zone not in allowed_zones:
        raise ValueError(
            "zone must be one of the following: districts, dist, distr, distritos, "
            "municipalities, muni, municipal, municipios, lua, large_urban_areas, "
            "gau, gaus, grandes_areas_urbanas"
        )

    if version == 1:
        if normalized_zone in ["lua", "large_urban_areas", "gau", "gaus", "grandes_areas_urbanas"]:
            raise Exception('gaus is not a valid zone for version 1. Please use version 2 or use a different zone')

def version_assert(version: int = None) -> None:
    if (
        isinstance(version, bool)
        or not isinstance(version, Integral)
        or version not in (1, 2)
    ):
        raise ValueError(
            "version must be 1 or 2. Version 1 contains the data from 2020 to 2021. "
            "Version 2 contains the data from 2022 onwards."
        )

def mobility_assert(mobility_type: str = None) -> None:
    if mobility_type not in ["od", "origin-destination", "os", "overnight_stays", "nt", "number_of_trips"]:
        raise ValueError(
            "mobility_type must be one of the following: od, origin-destination, "
            "os, overnight_stays, nt, number_of_trips"
        )

def date_format_assert(date: str = None) -> None:
    if not isinstance(date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise ValueError("date must be in the format YYYY-MM-DD")
    try:
        calendar_date.fromisoformat(date)
    except ValueError as exc:
        raise ValueError("date must be a valid calendar date in YYYY-MM-DD format") from exc

def zone_normalization(zone: str = None) -> str:
    normalized_zone = str(zone).lower()
    mapping = {
        'districts': 'distritos',
        'dist': 'distritos',
        'distr': 'distritos',
        'distritos': 'distritos',
        'municipalities': 'municipios',
        'muni': 'municipios',
        'municip': 'municipios',
        'municipal': 'municipios',
        'municipios': 'municipios',
        'lua': 'gaus',
        'large_urban_areas': 'gaus',
        'gau': 'gaus',
        'gaus': 'gaus',
        'grandes_areas_urbanas': 'gaus',
    }
    return mapping[normalized_zone] if normalized_zone in mapping else normalized_zone

def mobility_type_normalization(mobility_type: str = None, version: int = 2) -> str:
    corrected_mob_type = None

    if version == 1:
        if mobility_type in ("od", "origin-destination"):
            corrected_mob_type = "maestra1"
        elif mobility_type in ("nt", "number_of_trips"):
            corrected_mob_type = "maestra2"
        elif mobility_type in ("os", "overnight_stays"):
            raise Exception('os is not a valid mobility type for version 1. Please use version 2 or use a different mobility type')

    elif version == 2:
        if mobility_type in ("od", "origin-destination"):
            corrected_mob_type = "Viajes"
        elif mobility_type in ("os", "overnight_stays"):
            corrected_mob_type = "Pernoctaciones"
        elif mobility_type in ("nt", "number_of_trips"):
            corrected_mob_type = "Personas"

    return corrected_mob_type

def get_data_directory() -> str:
    """
    Get the data directory for the specified version.
    """
    return data_directory

def set_data_directory(directory: str) -> None:
    """
    Set the data directory for the specified version.
    """
    global data_directory
    data_directory = directory

def get_valid_dates(version: int = 2) -> list:
    """
    Get the valid dates for the specified version.
    """
    df = available_mobility_data(version)
    df.sort_values(by=['data_ymd'], ascending=True, inplace=True)
    df.dropna(subset = ['data_ymd'], inplace=True)
    return df['data_ymd'].unique().tolist()



def download_file_if_not_existing(
    url: str, local_path: str, *, verify_cache: bool = False
) -> None:
    """
    Download *url* to *local_path* unless a valid cached file is present.

    Gzip and ZIP archives are checked fully once, then an unchanged validated
    file is recognized by a local stat marker. Pass ``verify_cache=True`` to
    recheck an unchanged archive's contents. New downloads are staged and
    atomically moved into place after validation.
    """
    archive = local_path.endswith((".gz", ".zip"))
    marker_path = os.path.join(
        os.path.dirname(local_path),
        ".%s.pyspainmobility-validated.json" % os.path.basename(local_path),
    )

    def signature(path: str) -> dict:
        stat = os.stat(path)
        return {
            "size": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "inode": stat.st_ino,
            "device": stat.st_dev,
        }

    def has_matching_marker(path: str) -> bool:
        try:
            with open(marker_path, encoding="utf-8") as stream:
                marker = json.load(stream)
            return marker == signature(path)
        except (OSError, ValueError, TypeError):
            return False

    def mark_validated(path: str) -> None:
        if not archive:
            return
        marker_temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=os.path.dirname(path) or ".",
                prefix=".pyspainmobility-", suffix=".json", delete=False,
            ) as stream:
                marker_temporary_path = stream.name
                json.dump(signature(path), stream)
            os.replace(marker_temporary_path, marker_path)
        except OSError:
            # The marker is only a performance hint. A later call will run
            # full archive validation if it cannot be saved.
            if marker_temporary_path is not None and os.path.exists(marker_temporary_path):
                os.remove(marker_temporary_path)

    def valid_cached_file(path: str, *, trust_marker: bool = False) -> bool:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return False
        if archive and trust_marker and has_matching_marker(path):
            return True
        try:
            if path.endswith(".gz"):
                with gzip.open(path, "rb") as stream:
                    while stream.read(1024 * 1024):
                        pass
            elif path.endswith(".zip"):
                with zipfile.ZipFile(path) as zip_archive:
                    if zip_archive.testzip() is not None:
                        return False
        except (OSError, EOFError, zipfile.BadZipFile, zipfile.LargeZipFile):
            return False
        return True

    if valid_cached_file(local_path, trust_marker=not verify_cache):
        if archive and not has_matching_marker(local_path):
            mark_validated(local_path)
        return

    target_dir = os.path.dirname(local_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)

    temporary_path = None
    try:
        print(f"Downloading: {url}")
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})   # header
        with urlopen(req) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=target_dir or ".", prefix=".pyspainmobility-",
                suffix=os.path.splitext(local_path)[1],
                delete=False,
            ) as fh:
                temporary_path = fh.name
                size = 0
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    fh.write(chunk)
                    size += len(chunk)
            if size == 0:
                raise ValueError("Downloaded file is empty")
            content_length = resp.headers.get("Content-Length") if hasattr(resp, "headers") else None
            if content_length is not None and size != int(content_length):
                raise ValueError("Downloaded file size does not match Content-Length")
        if not valid_cached_file(temporary_path):
            raise ValueError("Downloaded file failed integrity validation")
        os.replace(temporary_path, local_path)
        temporary_path = None
        mark_validated(local_path)
        print(f"Saved {size} bytes to {local_path}")

    except Exception:
        if temporary_path is not None and os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise

def get_dates_between(start_date: str, end_date: str) -> list:
    """
    Get the list of dates between the start date and end date.
    """
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    return dates.strftime('%Y-%m-%d').tolist()
