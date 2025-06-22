from typing import Any
from pandas.errors import EmptyDataError 
from pyspainmobility.utils import utils
import os
import pandas as pd
import tqdm
from os.path import expanduser

# Optional Dask import – only used when caller sets use_dask=True
try:
    import dask.dataframe as dd
    from dask import delayed
except ImportError:  
    dd = None
    delayed = None

class Mobility:
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
    use_dask : bool
        Whether to use Dask for processing large datasets. Default is False. Requires dask to be installed.
    Examples
    --------
    >>> from pyspainmobility import Mobility
    >>> # instantiate the object
    >>> mobility_data = Mobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
    >>> # download and save the origin-destination data
    >>> mobility_data.get_od_data(keep_activity=True)
    >>> # download and save the overnight stays data
    >>> mobility_data.get_overnight_stays_data()
    >>> # download and save the number of trips data
    >>> mobility_data.get_number_of_trips_data()
    """
    def __init__(self, version: int = 2, zones: str = 'municipalities', start_date:str = None, end_date:str = None, output_directory:str = None, use_dask: bool = False):
        self.version = version
        self.zones = zones
        self.start_date = start_date
        self.end_date = end_date
        self.output_directory = output_directory
        self.use_dask = use_dask

        if self.use_dask and dd is None:
            raise ImportError("Dask is not installed. Please install dask to use use_dask=True")

        utils.zone_assert(zones, version)
        utils.version_assert(version)
        if start_date is None:
            raise ValueError("start_date is required")
        utils.date_format_assert(start_date)
        if end_date is None:
            end_date = start_date
        utils.date_format_assert(end_date)

        # --- fail fast if the end date is before the start date ---
        from pandas import to_datetime
        if to_datetime(end_date) < to_datetime(start_date):
            raise ValueError(
                f"end_date ({end_date}) must be the same as or after start_date ({start_date})."
            )

        self.zones = utils.zone_normalization(zones)

        data_directory = utils.get_data_directory()

        self.dates = utils.get_dates_between(start_date, end_date)

        valid_dates = utils.get_valid_dates(self.version)

        first, last = valid_dates[0], valid_dates[-1]
        if self.dates[0] < first or self.dates[-1] > last:
            raise ValueError(
                f"Version {self.version} data are only available from {first} to {last}. "
                f"You requested from {self.start_date} to {self.end_date}.")

        # proper directory handling
        if output_directory is not None:
            # Always treat as relative to home directory unless it's a proper absolute system path
            if os.path.isabs(output_directory) and os.path.exists(os.path.dirname(output_directory)):
                # It's a valid absolute path
                self.output_path = output_directory
            else:
                # Treat as relative to home directory, strip leading slash if present
                home = expanduser("~")
                clean_path = output_directory.lstrip('/')
                self.output_path = os.path.join(home, clean_path)
        else:
            self.output_path = data_directory
        
        #Ensure directory exists
        try:
            os.makedirs(self.output_path, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(f"Cannot create directory {self.output_path}. Please check permissions or use a different path. Error: {e}")
        except Exception as e:
            raise Exception(f"Error creating directory {self.output_path}: {e}")

        if self.version == 2:
            if self.zones == 'gaus':
                self.zones = 'GAU'

    def _process_single_od_file(self, filepath, keep_activity, social_agg):
        """Extract common file processing logic - DEBUGGING VERSION"""
        import gzip
        
        print(f"Processing file: {filepath}")
        
        # Check if file exists and get size
        if not os.path.exists(filepath):
            print(f"[ERROR] File does not exist: {filepath}")
            return None
        
        file_size = os.path.getsize(filepath)
        #print(f"File size: {file_size} bytes")
        
        if file_size == 0:
            print(f"[warn] {os.path.basename(filepath)} is actually empty (0 bytes), skipped")
            return None
        
        try:
            # Check if it's a gzipped file and handle accordingly
            if filepath.endswith('.gz'):
                print("Reading gzipped file...")
                    
                # Now read with pandas
                df = pd.read_csv(filepath, sep="|", compression='gzip',   dtype={"origen": "string", "destino": "string"})
            else:
                print("Reading regular CSV file...")
                df = pd.read_csv(filepath, sep="|",   dtype={"origen": "string", "destino": "string"})
            #Debug prints
              
            #print(f"DataFrame shape after reading: {df.shape}")   
            #print(f"DataFrame columns: {list(df.columns)}")
            
            if len(df) == 0:
                print(f"[warn] {os.path.basename(filepath)} contains no data rows, skipped")
                return None
                
        except EmptyDataError:
            print(f"[warn] {os.path.basename(filepath)} triggered EmptyDataError, skipped")
            return None
        except Exception as e:
            print(f"[ERROR] Error reading {filepath}: {e}")
            return None

        
        df.rename(
            columns={
                "fecha": "date",
                "periodo": "hour",
                "origen": "id_origin",
                "destino": "id_destination",
                "actividad_origen": "activity_origin",
                "actividad_destino": "activity_destination",
                "residencia": "residence_province_ine_code",
                "distancia": "distance",
                "viajes": "n_trips",
                "viajes_km": "trips_total_length_km",
                # socio-demo
                "renta": "income",
                "edad": "age",
                "sexo": "gender",
            },
            inplace=True,
        )

        # --- tidy date ---
        tmp = str(df.loc[0, "date"])
        df["date"] = f"{tmp[:4]}-{tmp[4:6]}-{tmp[6:8]}"

        #  map activity / gender labels
        df.replace(
            {
                "activity_origin": {
                    "casa": "home",
                    "frecuente": "other_frequent",
                    "trabajo_estudio": "work_or_study",
                    "no_frecuente": "other_non_frequent",
                },
                "activity_destination": {
                    "casa": "home",
                    "frecuente": "other_frequent",
                    "trabajo_estudio": "work_or_study",
                    "no_frecuente": "other_non_frequent",
                },
                "gender": {"hombre": "male", "mujer": "female"},
            },
            inplace=True,
        )

        # ------------------------------------------------------
        # BUILD GROUP-BY KEY ACCORDING TO THE TWO FLAGS
        # ------------------------------------------------------
        group_cols = ["date", "hour", "id_origin", "id_destination"]
        if keep_activity:
            group_cols += ["activity_origin", "activity_destination"]
        if social_agg:
            group_cols += ["income", "age", "gender"]

        df = (
            df.groupby(group_cols)
            .sum()[["n_trips", "trips_total_length_km"]]
            .reset_index()
        )
        
        return df

    def get_od_data(self, keep_activity: bool = False, return_df: bool = False,  social_agg: bool = False,):
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

        social_agg : bool
            Default value is  False. Adds socio-demographic breakdown. 
        • income:  <10 k, 10 to 15 k, >15 k € (in thousands)  
        • age:  0 to 24, 25 to 44, 45 to 64, >65 yrs, NA  
        • gender:  male, female, NA  

        
        Examples
        --------

        >>> from pyspainmobility import Mobility
        >>> # instantiate the object
        >>> mobility_data = Mobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
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
            m_type = "Viajes"
            local_list = self._donwload_helper(m_type)
            temp_dfs = []
            print("Generating parquet file for ODs....")
            
            if self.use_dask:
                # Use Dask for processing
                return self._process_od_data_dask(local_list, m_type, keep_activity, social_agg, return_df)
            else:
                # Original pandas processing using extracted method
                for f in tqdm.tqdm(local_list):
                    result = self._process_single_od_file(f, keep_activity, social_agg)
                    if result is not None:
                        temp_dfs.append(result)

                if not temp_dfs:
                    print("No valid data found")
                    return None

                print("Concatenating all the dataframes....")
                df = temp_dfs[0] if len(temp_dfs) == 1 else pd.concat(temp_dfs)

                self._saving_parquet(df, m_type)
                return df if return_df else None

        elif self.version == 1:
            m_type = "maestra1"
            local_list = self._donwload_helper(m_type)
            temp_dfs = []
            print("Generating parquet file for ODs....")

            if self.use_dask:
                # Use Dask for processing
                return self._process_od_data_dask(local_list, m_type, False, False, return_df)
            else:
                # Original pandas processing using extracted method
                for f in tqdm.tqdm(local_list):
                    result = self._process_single_od_file(f, False, False)
                    if result is not None:
                        temp_dfs.append(result)

                if not temp_dfs:
                    print("No valid data found")
                    return None

                print("Concatenating all the dataframes....")
                df = temp_dfs[0] if len(temp_dfs) == 1 else pd.concat(temp_dfs)

                self._saving_parquet(df, m_type)
                return df if return_df else None

        return None

    def _process_od_data_dask(self, local_list, m_type, keep_activity, social_agg, return_df):
        """Process OD data using Dask for better performance with large datasets """
        print("Processing with Dask...")
        
        if delayed is None:
            raise ImportError("Dask delayed is not available")
        
        @delayed
        def process_single_file(filepath):
            return self._process_single_od_file(filepath, keep_activity, social_agg)
        
        # Create delayed tasks for each file
        delayed_tasks = [process_single_file(f) for f in local_list]
        
        # Compute all delayed tasks
        try:
            processed_dfs = dd.compute(*delayed_tasks)
        except Exception as e:
            print(f"Dask computation failed: {e}")
            print("Falling back to pandas processing...")
            # Fallback using the same processing method
            processed_dfs = []
            for f in tqdm.tqdm(local_list):
                result = self._process_single_od_file(f, keep_activity, social_agg)
                if result is not None:
                    processed_dfs.append(result)
        
        # Filter out None results and concatenate
        valid_dfs = [df for df in processed_dfs if df is not None]
        
        if not valid_dfs:
            print("No valid data found")
            return None
        
        print("Concatenating results...")
        df = pd.concat(valid_dfs, ignore_index=True)
        
        self._saving_parquet(df, m_type)
        return df if return_df else None

    def get_overnight_stays_data(self, return_df: bool = False):
        """
        Function to download and save the overnight stays data.

        Parameters
        ----------
        return_df : bool
            Default value is False. If True, the function will return the dataframe in addition to saving it to a file.
        Examples
        --------

        >>> from pyspainmobility import Mobility
        >>> # instantiate the object
        >>> mobility_data = Mobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
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
            
            if self.use_dask and len(local_list) > 1:
                # Use Dask for larger datasets
                @delayed
                def process_overnight_file(filepath):
                    try:
                        df = pd.read_csv(filepath, sep='|')
                        df.rename(columns={
                            'fecha': 'date',
                            'zona_residencia': 'residence_area',
                            'zona_pernoctacion': 'overnight_stay_area',
                            'personas': 'people'
                        }, inplace=True)

                        if len(df) > 0:
                            tmp_date = str(df.iloc[0]['date'])
                            df['date'] = f"{tmp_date[:4]}-{tmp_date[4:6]}-{tmp_date[6:8]}"
                        return df
                    except Exception as e:
                        print(f"Error processing {filepath}: {e}")
                        return None
                
                delayed_tasks = [process_overnight_file(f) for f in local_list]
                processed_dfs = dd.compute(*delayed_tasks)
                valid_dfs = [df for df in processed_dfs if df is not None]
                
                if valid_dfs:
                    df = pd.concat(valid_dfs, ignore_index=True)
                else:
                    return None
            else:
                # Original pandas processing
                for f in tqdm.tqdm(local_list):
                    try:
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
                    except Exception as e:
                        print(f"Error processing file: {e}")
                        continue

                print('Concatenating all the dataframes....')
                df = pd.concat(temp_dfs) if temp_dfs else None
                
            if df is not None:
                self._saving_parquet(df, m_type)
                if return_df:
                    return df

        elif self.version == 1:
            raise Exception('Overnight stays data is not available for version 1. Please use version 2.')
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

        >>> from pyspainmobility import Mobility
        >>> # instantiate the object
        >>> mobility_data = Mobility(version=2, zones='municipalities', start_date='2022-01-01', end_date='2022-01-06', output_directory='/Desktop/spain/data/')
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
            print('Generating parquet file for Number of Trips....')
            
            if self.use_dask and len(local_list) > 1:  # multiple files
                # Use Dask for larger datasets
                @delayed
                def process_trips_file(filepath):
                    try:
                        df = pd.read_csv(filepath, sep='|')
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

                        if len(df) > 0:
                            tmp_date = str(df.iloc[0]['date'])
                            df['date'] = f"{tmp_date[:4]}-{tmp_date[4:6]}-{tmp_date[6:8]}"
                        return df
                    except Exception as e:
                        print(f"Error processing {filepath}: {e}")
                        return None
                
                delayed_tasks = [process_trips_file(f) for f in local_list]
                processed_dfs = dd.compute(*delayed_tasks)
                valid_dfs = [df for df in processed_dfs if df is not None]
                
                if valid_dfs:
                    df = pd.concat(valid_dfs, ignore_index=True)
                else:
                    return None
            else:
                # Original pandas processing
                for f in tqdm.tqdm(local_list):
                    try:
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
                    except Exception as e:
                        print(f"Error processing file: {e}")
                        continue

                print('Concatenating all the dataframes....')
                df = pd.concat(temp_dfs) if temp_dfs else None

            if df is not None:
                self._saving_parquet(df, m_type)
                if return_df:
                    return df
                
        if self.version == 1:
            m_type = 'maestra2'
            local_list = self._donwload_helper(m_type)
            temp_dfs = []
            print('Generating parquet file for Number of Trips....')

            if self.use_dask and len(local_list) > 1:  # multiple files
                # Use Dask for larger datasets
                @delayed
                def process_trips_file(filepath):
                    try:
                        df = pd.read_csv(filepath, sep='|')
                        df.rename(columns={
                            'fecha': 'date',
                            'distrito': 'overnight_stay_area',
                            'numero_viajes': 'number_of_trips',
                            'personas': 'people'
                        }, inplace=True)

                        if len(df) > 0:
                            tmp_date = str(df.iloc[0]['date'])
                            df['date'] = f"{tmp_date[:4]}-{tmp_date[4:6]}-{tmp_date[6:8]}"
                        return df
                    except Exception as e:
                        print(f"Error processing {filepath}: {e}")
                        return None

                delayed_tasks = [process_trips_file(f) for f in local_list]
                processed_dfs = dd.compute(*delayed_tasks)
                valid_dfs = [df for df in processed_dfs if df is not None]

                if valid_dfs:
                    df = pd.concat(valid_dfs, ignore_index=True)
                else:
                    return None
            else:
                # Original pandas processing
                for f in tqdm.tqdm(local_list):
                    try:
                        df = pd.read_csv(f, sep='|')

                        df.rename(columns={
                            'fecha': 'date',
                            'distrito': 'overnight_stay_area',
                            'numero_viajes': 'number_of_trips',
                            'personas': 'people'
                        }, inplace=True)

                        tmp_date = str(df.loc[0]['date'])
                        new_date = tmp_date[0:4] + '-' + tmp_date[4:6] + '-' + tmp_date[6:8]
                        df['date'] = new_date

                        temp_dfs.append(df)
                    except Exception as e:
                        print(f"Error processing file: {e}")
                        continue

                print('Concatenating all the dataframes....')
                df = pd.concat(temp_dfs) if temp_dfs else None

            if df is not None:
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