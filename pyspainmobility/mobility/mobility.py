from typing import Any

from pyspainmobility.utils import utils
import os

def get_daily_mobility_basico(mobility_type: str = None, version: int = 2, zones: str = None, dates = None):
    """
    Get the zones for the specified version.
    """
    utils.zone_assert(zones, version)
    utils.version_assert(version)
    utils.mobility_assert(mobility_type)

    zones = utils.zone_normalization(zones)
    mobility_type = utils.mobility_type_normalization(mobility_type, version)

    if isinstance(dates, str):
        dates = [dates]

    if isinstance(dates, set):
        # we have the starting date and the ending date in format YYYY-MM-DD, we need to create a list of dates between them
        start_date = dates[0]
        end_date = dates[1]
        dates = utils.get_dates_between(start_date, end_date)

    # dates cannot be None
    assert dates is not None, "dates cannot be None. Please provide a list of dates in format YYYY-MM-DD or a set with the starting and ending date in format YYYY-MM-DD or a single day in format YYYY-MM-DD"

    # Get the data directory
    data_directory = utils.get_data_directory()
    # Get the links for the specified version and zones

    local_list = []

    if version == 2:
        if zones == 'gaus':
            zones = 'GAU'

        for d in dates:
            d_first = d[:7]
            d_second = d.replace("-", "")
            try:
                if mobility_type == 'Personas':
                    utils.download_file_if_not_existing(f"https://movilidad-opendata.mitma.es/estudios_basicos/por-{zones}/{mobility_type.lower()}/ficheros-diarios/{d_first}/{d_second}_{mobility_type}_dia_{zones}.csv.gz", os.path.join(data_directory, f"{d_second}_{mobility_type}_{zones}.csv.gz"))
                    local_list.append(os.path.join(data_directory, f"{d_second}_{mobility_type}_{zones}.csv.gz"))
                else:
                    utils.download_file_if_not_existing(f"https://movilidad-opendata.mitma.es/estudios_basicos/por-{zones}/{mobility_type.lower()}/ficheros-diarios/{d_first}/{d_second}_{mobility_type}_{zones}.csv.gz", os.path.join(data_directory, f"{d_second}_{mobility_type}_{zones}.csv.gz"))
                    local_list.append(os.path.join(data_directory, f"{d_second}_{mobility_type}_{zones}.csv.gz"))
            except:
                continue

    elif version == 1:

        if zones == 'gaus':
            raise Exception('gaus is not a valid zone for version 1. Please use version 2 or use a different zone')

        for d in dates:
            d_first = d[:7]
            d_second = d.replace("-", "")
            try:
                url_base = f"https://opendata-movilidad.mitma.es/{mobility_type}-mitma-{zones}/ficheros-diarios/{d_first}/{d_second}_{mobility_type[:-1]}_{mobility_type[-1]}_mitma_{zones[:-1]}.txt.gz"
                utils.download_file_if_not_existing(url_base, os.path.join(data_directory, f"{d_second}_{mobility_type}_{zones}.txt.gz"))
                local_list.append(os.path.join(data_directory, f"{d_second}_{mobility_type}_{zones}.txt.gz"))
            except:
                continue