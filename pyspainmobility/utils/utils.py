import os

import pandas as pd
import xml.etree.ElementTree as ET
import re
from urllib.request import urlopen
import zipfile
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

            # check if the file is already downloaded in the data directory
            local_path = data_directory + tmp_date
            if os.path.exists(local_path):
                downloaded = True
                valid_path = local_path
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

def available_zoning_data(version: int = 2, zone:str = None) -> pd.DataFrame:
    version_assert(version)
    zone_assert(zone)

    url = None

    if version == 1:
        url = 'https://opendata-movilidad.mitma.es/RSS.xml'
    elif version == 2:
        url = 'https://movilidad-opendata.mitma.es/RSS.xml'

    data = []

    with urlopen(url) as f:
        tree = ET.parse(f)
        # link, file_extension, data_ym, data_ymd, local_path, downloaded
        for item in tree.getroot()[0].findall('item'):
            link = item.findtext('link')
            pubdate = item.findtext('pubDate')
            tmp_date = link.split('/')[-1]
            # if one between zonification_, poblacion or relacion_ine_zonificacionMitma is in the tmp_date, add it to the data
            if zone is not None:
                normalize_zone = zone_normalization(zone)
                if bool(re.match(f"(zonificacion_{normalize_zone}\\.*)|(poblacion_{normalize_zone}\\.*)|(nombres_{normalize_zone}\\.*)|(poblacion.csv)|(relacion_ine_zonificacionMitma.csv)|(relaciones_municipio_mitma.csv)|(relaciones_distrito_mitma.csv)", tmp_date)):
                    data.append([link, pubdate, tmp_date])

    return pd.DataFrame(data, columns=['link', 'pub_date', 'filename'])

def zone_assert(zone: str = None, version: int = 2) -> None:
    assert zone in ["districts", "dist", "distr", "distritos",
    "municipalities", "muni", "municip", "municipios",
    "lua", "large_urban_areas", "gau", "gaus", "grandes_areas_urbanas"], "zone must be one of the following: districts, dist, distr, distritos, municipalities, muni, municipal, municipios, lua, large_urban_areas, gau, gaus, grandes_areas_urbanas"

    if version == 1:
        if zone in ["lua", "large_urban_areas", "gau", "gaus", "grandes_areas_urbanas"]:
            raise Exception('gaus is not a valid zone for version 1. Please use version 2 or use a different zone')

def version_assert(version: int = None) -> None:
    assert version in [1, 2], "version must be 1 or 2. Verison 1 contains the data from 2020 to 2021. Version 2 contains the data from 2022 onwards."

def mobility_assert(mobility_type: str = None) -> None:
    assert mobility_type in ["od", "origin-destination", "os", "overnight_stays", "nt", "number_of_trips"], "mobility_type must be one of the following: od, origin-destination, os, overnight_stays, nt, number_of_trips"

def date_format_assert(date: str = None) -> None:
    assert bool(re.match(r'^\d{4}-\d{2}-\d{2}$', date)), "date must be in the format YYYY-MM-DD"

def zone_normalization(zone: str = None) -> str:
    mapping = {
        'districts': 'distritos',
        'dist': 'distritos',
        'distr': 'distritos',
        'distritos': 'distritos',
        'municipalities': 'municipios',
        'muni': 'municipios',
        'municip': 'municipios',
        'municipios': 'municipios',
        'lua': 'gaus',
        'large_urban_areas': 'gaus',
        'gau': 'gaus',
        'grandes_areas_urbanas': 'gaus',
    }
    return mapping[str(zone).lower()] if zone in mapping else str(zone).lower()

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



def download_file_if_not_existing(url: str, local_path: str) -> None:
    """
    Download *url* to *local_path* unless the file already exists **and**
    is non-empty.  Zero-byte (or corrupted) files are deleted and fetched
    again.
    """
    # If a previous run left an empty file, wipe it 
    if os.path.exists(local_path) and os.path.getsize(local_path) == 0:
        print(f"Found empty file at {local_path} – redownloading.")
        os.remove(local_path)

    # Normal early-exit when the file is OK
    if os.path.exists(local_path):
        return

    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    try:
        print(f"Downloading: {url}")
        req = Request(url, headers={"User-Agent": "Mozilla/5.0"})   # header
        with urlopen(req) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            data = resp.read()
            if not data:
                raise Exception("Downloaded file is empty")

        with open(local_path, "wb") as fh:
            fh.write(data)
        print(f"Saved {len(data)} bytes to {local_path}")

    except Exception as e:
        # Clean up partial artefacts
        if os.path.exists(local_path):
            os.remove(local_path)
        raise

def get_dates_between(start_date: str, end_date: str) -> list:
    """
    Get the list of dates between the start date and end date.
    """
    start_date = pd.to_datetime(start_date)
    end_date = pd.to_datetime(end_date)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    return dates.strftime('%Y-%m-%d').tolist()