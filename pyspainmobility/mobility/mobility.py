from typing import Any

from pyspainmobility.utils import utils
import os
import pandas as pd
import tqdm
from os.path import expanduser

class SpainMobility:
    """
    This is the object taking care of the data download and preprocessing of (i) daily origin-destination matrices (ii), overnight stays and (iii) number of trips.
    The data is downloaded from the Spanish Ministry of Transport, Mobility and Urban Agenda (MITMA) Open Data portal.
    Additional information can be found at https://www.transportes.gob.es/ministerio/proyectos-singulares/estudio-de-movilidad-con-big-data.
    The data is available for two versions: version 1 (2020-02-14 to 2021-05-09) and version 2 (2022-01-01 onward).
    Data are available at different levels of granularity: districts (distritos), municipalities (municipios) and large urban areas (grandes áreas urbanas).
    Concerning version 1, data are LUA are not available. Also, overnight stays are not available for version 1.

    Parameters
    ----------
    version : int
        The version of the data to download. Default is 2. Version must be 1 or 2. Version 1 contains the data from 2020 to 2021. Version 2 contains the data from 2022 onwards.
    zones : str
        The zones to download the data for. Default is municipalities. Zones must be one of the following: districts, dist, distr, distritos, municipalities, muni, municipal, municipios, lua, large_urban_areas, gau, gaus, grandes_areas_urbanas
    start_date : str
        The start date of the data to download. Date must be in the format YYYY-MM-DD. A start date is required
    end_date : str
        The end date of the data to download. Default is None. Date must be in the format YYYY-MM-DD. if not specified, the end date will be the same as the start date.
    output_directory : str
        The directory to save the raw data and the processed parquet. Default is None. If not specified, the data will be saved in a folder named 'data' in user's home directory.
    Examples
    --------
    >>> from pyspainmobility import SpainMobility
    >>> # instantiate the object
    >>> mobility_data = SpainMobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
    >>> # download and save the origin-destination data
    >>> mobility_data.get_od_data(keep_activity=True)
    >>> # download and save the overnight stays data
    >>> mobility_data.get_overnight_stays_data()
    >>> # download and save the number of trips data
    >>> mobility_data.get_number_of_trips_data()
    """
    def __init__(self, version: int = 2, zones: str = 'municipalities', start_date:str = None, end_date:str = None, output_directory:str = None):
        self.version = version
        self.zones = zones
        self.start_date = start_date
        self.end_date = end_date
        self.output_directory = output_directory

        utils.zone_assert(zones, version)
        utils.version_assert(version)
        if start_date is None:
            raise ValueError("start_date is required")
        utils.date_format_assert(start_date)
        if end_date is None:
            end_date = start_date
        utils.date_format_assert(end_date)

        self.zones = utils.zone_normalization(zones)

        data_directory = utils.get_data_directory()

        self.dates = utils.get_dates_between(start_date, end_date)

        # check if a previously processed file exists in the output directory
        if output_directory is not None:
            home = expanduser("~")
            self.output_path = os.path.join(home,output_directory)
        else:
            self.output_path = os.path.join(data_directory)

        if self.version == 2:
            if self.zones == 'gaus':
                self.zones = 'GAU'


    def get_od_data(self, keep_activity: bool = False, return_df: bool = False):
        """
        Function to download and save the origin-destination data.

        Parameters
        ----------
        keep_activity : bool
            Default value is False. If True, the columns 'activity_origin' and 'activity_destination' will be kept in the final dataframe. If False, the columns will be dropped.
            The columns contain the activity of the origin and destination zones. The possible values are: 'home', 'work_or_study', 'other_frequent', 'other_non_frequent'.
            Consider that keeping the activity columns will increase the size of the final dataframe and the saved files significantly.

        return_df : bool
            Default value is False. If True, the function will return the dataframe in addition to saving it to a file.
        Examples
        --------

        >>> from pyspainmobility import SpainMobility
        >>> # instantiate the object
        >>> mobility_data = SpainMobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
        >>> # download and save the origin-destination data
        >>> mobility_data.get_od_data(keep_activity=True)
        >>> # download and save the od data and return the dataframe
        >>> df = mobility_data.get_od_data(keep_activity=False, return_df=True)
        >>> print(df.head())
            date  hour id_origin id_destination  n_trips  trips_total_length_km
        0  2023-04-01     0     01001          01001    5.006              19.878000
        1  2023-04-01     0     01001       01009_AM   14.994              70.697000
        2  2023-04-01     0     01001       01058_AM    9.268              87.698000
        3  2023-04-01     0     01001          01059   42.835             512.278674
        4  2023-04-01     0     01001          48036    2.750             147.724000
        """

        if self.version == 2:
            m_type = 'Viajes'
            local_list = self._donwload_helper(m_type)
            temp_dfs = []
            print('Generating parquet file for ODs....')
            for f in tqdm.tqdm(local_list):
                df = pd.read_csv(f, sep='|')

                df.rename(columns={
                    'fecha': 'date',
                    'periodo': 'hour',
                    'origen': 'id_origin',
                    'destino': 'id_destination',
                    'actividad_origen': 'activity_origin',
                    'actividad_destino': 'activity_destination',
                    'residencia': 'residence_province_ine_code',
                    'distancia': 'distance',
                    'viajes': 'n_trips',
                    'viajes_km': 'trips_total_length_km'
                }, inplace=True)

                tmp_date = str(df.loc[0]['date'])
                new_date = tmp_date[0:4] + '-' + tmp_date[4:6] + '-' + tmp_date[6:8]
                df['date'] = new_date

                df.replace({"activity_origin":
                                {'casa': 'home',
                                 'frecuente': 'other_frequent',
                                 'trabajo_estudio': 'work_or_study',
                                 'no_frecuente': 'other_non_frequent'}},
                           inplace=True
                           )

                df.replace({"activity_destination":
                                {'casa': 'home',
                                 'frecuente': 'other_frequent',
                                 'trabajo_estudio': 'work_or_study',
                                 'no_frecuente': 'other_non_frequent'}},
                           inplace=True
                           )

                if keep_activity:
                    df = df.groupby(['date', 'hour', 'id_origin', 'id_destination', 'activity_origin',
                                     'activity_destination']).sum()[
                        ['n_trips', 'trips_total_length_km']]
                else:
                    df = df.groupby(['date', 'hour', 'id_origin', 'id_destination']).sum()[
                        ['n_trips', 'trips_total_length_km']]
                df = df.reset_index()
                temp_dfs.append(df)
            print('Concatenating all the dataframes....')
            if len(temp_dfs) == 1:
                df = temp_dfs[0]
            else:
                df = pd.concat(temp_dfs)
            self._saving_parquet(df, m_type)

            if return_df:
                return df
        return None

    def get_overnight_stays_data(self, return_df: bool = False):
        """
        Function to download and save the overnight stays data.

        Parameters
        ----------
        return_df : bool
            Default value is False. If True, the function will return the dataframe in addition to saving it to a file.
        Examples
        --------

        >>> from pyspainmobility import SpainMobility
        >>> # instantiate the object
        >>> mobility_data = SpainMobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
        >>> # download and save the overnight stays data and return the dataframe
        >>> df = mobility_data.get_overnight_stays_data( return_df=True)
        >>> print(df.head())
           date residence_area overnight_stay_area    people
        0  2023-04-01          01001               01001  2716.303
        1  2023-04-01          01001            01009_AM    14.088
        2  2023-04-01          01001            01017_AM     2.476
        3  2023-04-01          01001            01058_AM    18.939
        4  2023-04-01          01001               01059   144.118
        """
        if self.version == 2:
            m_type = 'Pernoctaciones'
            local_list = self._donwload_helper(m_type)
            temp_dfs = []
            print('Generating parquet file for Overnight Stays....')
            for f in tqdm.tqdm(local_list):
                df = pd.read_csv(f, sep='|')
                df.rename(columns={
                    'fecha': 'date',
                    'zona_residencia': 'residence_area',
                    'zona_pernoctacion': 'overnight_stay_area',
                    'personas': 'people'
                }, inplace=True)

                tmp_date = str(df.loc[0]['date'])
                new_date = tmp_date[0:4] + '-' + tmp_date[4:6] + '-' + tmp_date[6:8]
                df['date'] = new_date

                temp_dfs.append(df)

            print('Concatenating all the dataframes....')
            df = pd.concat(temp_dfs)
            self._saving_parquet(df, m_type)
            if return_df:
                return df
        return None

    def get_number_of_trips_data(self, return_df: bool = False):
        """
        Function to download and save the data regarding the number of trips to an area of certain demographic categories.

        Parameters
        ----------
        return_df : bool
            Default value is False. If True, the function will return the dataframe in addition to saving it to a file.
        Examples
        --------

        >>> from pyspainmobility import SpainMobility
        >>> # instantiate the object
        >>> mobility_data = SpainMobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
        >>> # download and save the overnight stays data and return the dataframe
        >>> df = mobility_data.get_number_of_trips_data( return_df=True)
        >>> print(df.head())
        date overnight_stay_area   age  gender number_of_trips   people
        0  2023-04-01               01001  0-25    male               0  128.457
        1  2023-04-01               01001  0-25    male               1   38.537
        2  2023-04-01               01001  0-25    male               2  129.136
        3  2023-04-01               01001  0-25    male              2+  129.913
        4  2023-04-01               01001  0-25  female               0  188.744
        """
        if self.version == 2:
            m_type = 'Personas'
            local_list = self._donwload_helper(m_type)
            temp_dfs = []
            print('Generating parquet file for Overnight Stays....')
            for f in tqdm.tqdm(local_list):
                df = pd.read_csv(f, sep='|')

                df.rename(columns={
                    'fecha': 'date',
                    'zona_pernoctacion': 'overnight_stay_area',
                    'edad': 'age',
                    'sexo': 'gender',
                    'numero_viajes': 'number_of_trips',
                    'personas': 'people'
                }, inplace=True)

                df.replace({"gender":
                                {'hombre': 'male',
                                 'mujer': 'female'}},
                           inplace=True
                           )

                tmp_date = str(df.loc[0]['date'])
                new_date = tmp_date[0:4] + '-' + tmp_date[4:6] + '-' + tmp_date[6:8]
                df['date'] = new_date

                temp_dfs.append(df)

            print('Concatenating all the dataframes....')
            df = pd.concat(temp_dfs)
            self._saving_parquet(df, m_type)
            if return_df:
                return df

        return None

    def _saving_parquet(self, df: pd.DataFrame, m_type: str):
        print('Writing the parquet file....')
        df.to_parquet(
            os.path.join(self.output_path,
                         f"{m_type}_{self.zones}_{self.start_date}_{self.end_date}_v{self.version}.parquet"),
            index=False)
        print('Parquet file generated successfully at ',
              os.path.join(self.output_path, f"{m_type}_{self.zones}_{self.start_date}_{self.end_date}_v{self.version}.parquet"))

    def _donwload_helper(self, m_type:str):
        local_list = []
        if self.version == 2:
            for d in self.dates:
                d_first = d[:7]
                d_second = d.replace("-", "")
                if m_type == 'Personas':
                    download_url = f"https://movilidad-opendata.mitma.es/estudios_basicos/por-{self.zones}/{m_type.lower()}/ficheros-diarios/{d_first}/{d_second}_{m_type}_dia_{self.zones}.csv.gz"
                else:
                    download_url = f"https://movilidad-opendata.mitma.es/estudios_basicos/por-{self.zones}/{m_type.lower()}/ficheros-diarios/{d_first}/{d_second}_{m_type}_{self.zones}.csv.gz"

                print('Downloading file from', download_url)
                try:
                    utils.download_file_if_not_existing(download_url,os.path.join(self.output_path, f"{d_second}_{m_type}_{self.zones}_v{self.version}.csv.gz"))
                    local_list.append(os.path.join(self.output_path, f"{d_second}_{m_type}_{self.zones}_v{self.version}.csv.gz"))
                except:
                    continue
        elif self.version == 1:

            if self.zones == 'gaus':
                raise Exception('gaus is not a valid zone for version 1. Please use version 2 or use a different zone')

            for d in self.dates:
                d_first = d[:7]
                d_second = d.replace("-", "")
                try:
                    url_base = f"https://opendata-movilidad.mitma.es/{m_type}-mitma-{self.zones}/ficheros-diarios/{d_first}/{d_second}_{m_type[:-1]}_{m_type[-1]}_mitma_{self.zones[:-1]}.txt.gz"
                    utils.download_file_if_not_existing(url_base, os.path.join(self.output_path, f"{d_second}_{m_type}_{self.zones}_v{self.version}.txt.gz"))
                    local_list.append(os.path.join(self.output_path, f"{d_second}_{m_type}_{self.zones}_v{self.version}.txt.gz"))
                except:
                    continue
        return local_list