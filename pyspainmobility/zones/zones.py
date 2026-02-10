from pyspainmobility.utils import utils
import pandas as pd
import geopandas as gpd
import os
import matplotlib
from os.path import expanduser

class Zones:
    def __init__(self, zones: str = None, version: int = 1, output_directory: str = None):
        """
        Class to handle the zoning related to the Spanish big mobility data. The class is used to download the data and
        process it. Selectable granularities are districts (distritos), municipalities (municipios) and large urban areas (grandes áreas urbanas). As a reminder,
        mobility data for the COVID-19 period (version 1) are not available for the large urban areas.

        Parameters
        ----------
        zones : str
            The zones to download the data for. Default is municipalities. Zones must be one of the following: districts, dist, distr, distritos, municipalities, muni, municipal, municipios, lua, large_urban_areas, gau, gaus, grandes_areas_urbanas
        version : int
            The version of the data to download. Default is 2. Version must be 1 or 2. Version 1 contains the data from 2020 to 2021. Version 2 contains the data from 2022 onwards.
        output_directory : str
            The directory to save the raw data and the processed parquet. Default is None. If not specified, the data will be saved in a folder named 'data' in user's home directory.

        Examples
        --------

        >>> from pyspainmobility import Zones
        >>> # instantiate the object
        >>> zones = Zones(zones='municipalities', version=2, output_directory='data')
        >>> # get the geodataframe with the zones
        >>> gdf = zones.get_zone_geodataframe()
        >>> print(gdf.head())
                                                       name            population
        ID
        01001                                        Alegría-Dulantzi     2925.0
        01002                                                 Amurrio    10307.0
        01004_AM                  Artziniega agregacion de municipios     3005.0
        01009_AM                   Asparrena agregacion de municipios     4599.0

        """

        utils.version_assert(version)
        utils.zone_assert(zones, version)
        self.version = version
        self.zones = utils.zone_normalization(zones)
        self.complete_df = None
        self._zoning_links = None
        self._downloads_ready = False

        # Get the data directory
        data_directory = utils.get_data_directory()
        self.data_directory = data_directory
        
        # Proper output directory handling
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
        
        # Ensure directory exists
        try:
            os.makedirs(self.output_path, exist_ok=True)
        except PermissionError as e:
            raise PermissionError(f"Cannot create directory {self.output_path}. Please check permissions or use a different path. Error: {e}")
        except Exception as e:
            raise Exception(f"Error creating directory {self.output_path}: {e}")

    def _get_zoning_links(self) -> list:
        """
        Resolve available zoning links lazily.
        """
        if self._zoning_links is None:
            self._zoning_links = (
                utils.available_zoning_data(self.version, self.zones)["link"]
                .dropna()
                .unique()
                .tolist()
            )
        return self._zoning_links

    def _ensure_zoning_files_downloaded(self) -> None:
        """
        Download required files only when the user first requests data.
        """
        if self._downloads_ready:
            return

        links = self._get_zoning_links()
        for link in links:
            file_name = link.split("/")[-1]
            local_path = os.path.join(self.output_path, file_name)

            if not os.path.exists(local_path):
                print("Downloading necessary files....")
                utils.download_file_if_not_existing(link, local_path)

            if self.version == 1 and file_name.endswith(".zip"):
                utils.unzip_file(local_path, self.output_path)

        self._downloads_ready = True

    def _load_zone_geodataframe(self) -> None:
        """
        Build/load the zone geodataframe lazily on first access.
        """
        if self.complete_df is not None:
            return

        self._ensure_zoning_files_downloaded()
        print("Zones already downloaded. Reading the files....")
        output_file_path = os.path.join(self.output_path, f"{self.zones}_{self.version}.geojson")

        if os.path.exists(output_file_path):
            print(f"File {output_file_path} already exists. Loading it...")
            self.complete_df = gpd.read_file(output_file_path)
            return

        if self.version == 2:
            def _read_pipe_csv(path, cols):
                """
                Read a ‘|’-separated MITMA CSV that may or may not contain a header
                and may start with a UTF-8 BOM. Returns a tidy DataFrame.
                """
                df = pd.read_csv(
                    path,
                    sep="|",
                    dtype=str,
                    header=None,
                    names=cols,
                    encoding="utf-8-sig",
                )
                df[cols[0]] = df[cols[0]].str.strip()
                if df.iloc[0, 0].upper() == cols[0].upper():
                    df = df.iloc[1:]
                return df

            nombre = _read_pipe_csv(
                self._resolve_data_file(f"nombres_{self.zones}.csv"),
                ["ID", "name"],
            )
            pop = (
                _read_pipe_csv(
                    self._resolve_data_file(f"poblacion_{self.zones}.csv"),
                    ["ID", "population"],
                )
                .replace("NA", None)
            )

            zonification = gpd.read_file(
                self._resolve_data_file(f"zonificacion_{self.zones}.shp")
            )
            if zonification.crs is None or zonification.crs.to_epsg() != 4326:
                zonification = zonification.to_crs(epsg=4326)

            for col in zonification.columns:
                if col.lower() in {"id", "id_1", "codigo", "codigoine", "cod_mun"}:
                    zonification["ID"] = zonification[col].astype(str).str.strip()
                    break
            else:
                raise KeyError("No ID-like column found in the shapefile")

            complete_df = (
                nombre.set_index("ID")
                .join(pop.set_index("ID"))
                .join(zonification.set_index("ID"))
            )
            complete_df = gpd.GeoDataFrame(complete_df, crs="EPSG:4326")
            complete_df.reset_index(inplace=True)
            complete_df.rename(columns={"ID": "id"}, inplace=True)
            complete_df.set_index("id", inplace=True)
            complete_df.to_file(output_file_path, driver="GeoJSON")
            self.complete_df = complete_df
            return

        zonification = gpd.read_file(
            os.path.join(self.output_path, f"zonificacion-{self.zones}/{self.zones}_mitma.shp")
        )
        if zonification.crs is None or zonification.crs.to_epsg() != 4326:
            zonification = zonification.to_crs(epsg=4326)

        complete_df = zonification
        complete_df.rename(columns={"ID": "id"}, inplace=True)
        complete_df.set_index("id", inplace=True)
        complete_df.to_file(output_file_path, driver="GeoJSON")
        self.complete_df = complete_df


    def _resolve_data_file(self, filename: str) -> str:
        """
        Resolve a data file path, preferring the instance output path and
        falling back to the global default data directory for backward
        compatibility.
        """
        preferred = os.path.join(self.output_path, filename)
        if os.path.exists(preferred):
            return preferred

        fallback = os.path.join(utils.get_data_directory(), filename)
        if os.path.exists(fallback):
            return fallback

        return preferred

    def _read_relation_table(self, filename: str) -> pd.DataFrame:
        """
        Read relation CSV files with robust delimiter detection.
        """
        path = self._resolve_data_file(filename)
        for sep in ("|", ",", ";", "\t"):
            try:
                df = pd.read_csv(path, sep=sep, dtype=str, encoding="utf-8-sig")
                if len(df.columns) > 1:
                    return df
            except Exception:
                continue
        return pd.read_csv(path, dtype=str, encoding="utf-8-sig")

    def get_zone_geodataframe(self):
        """
        Function that returns the geodataframe with the zones. The geodataframe contains the following columns:
        - id: the id of the zone
        - name: the name of the zone
        - population: the population of the zone (if available)

        Parameters
        ----------

        Examples
        --------

        >>> from pyspainmobility import Zones
        >>> # instantiate the object
        >>> zones = Zones(zones='municipalities', version=2, output_directory='data')
        >>> # get the geodataframe with the zones
        >>> gdf = zones.get_zone_geodataframe()
        >>> print(gdf.head())
                                                       name            population
        ID
        01001                                        Alegría-Dulantzi     2925.0
        01002                                                 Amurrio    10307.0
        01004_AM                  Artziniega agregacion de municipios     3005.0
        01009_AM                   Asparrena agregacion de municipios     4599.0

        """
        self._load_zone_geodataframe()
        return self.complete_df

    def get_zone_relations(self):
        """
        Return official mapping tables between INE administrative units and
        MITMA zoning identifiers.

        For version 2, the returned table includes one row per relation entry
        with harmonized column names.
        For version 1, the method returns one row per MITMA zone id, where
        each relation column contains the set of linked INE identifiers.

        Parameters
        ----------
        None

        Returns
        -------
        pandas.DataFrame
            Relation table between census/municipality identifiers and MITMA
            zoning identifiers.

        Examples
        --------

        >>> from pyspainmobility import Zones
        >>> zones = Zones(zones='municipalities', version=2, output_directory='data')
        >>> rel = zones.get_zone_relations()
        >>> rel.columns.tolist()
        ['census_sections', 'census_districts', 'municipalities',
         'municipalities_mitma', 'districts_mitma', 'luas_mitma']
        """
        self._ensure_zoning_files_downloaded()
        if self.version == 2:
            relacion = self._read_relation_table('relacion_ine_zonificacionMitma.csv')

            remapping = {
                'seccion_ine': 'census_sections',
                'distrito_ine': 'census_districts',
                'municipio_ine': 'municipalities',
                'municipio_mitma': 'municipalities_mitma',
                'distrito_mitma': 'districts_mitma',
                'gau_mitma': 'luas_mitma'
            }
            relacion.rename(columns=remapping, inplace=True)
            relacion = relacion.replace('NA', None)
            return relacion
        else:
            used_zone = self.zones[:-1]
            relacion = self._read_relation_table(f'relaciones_{used_zone}_mitma.csv')

            relacion.rename(columns={f'{used_zone}_mitma': 'id'}, inplace=True)

            if used_zone == 'municipio':
                temp = self._read_relation_table('relaciones_distrito_mitma.csv')
                relacion = relacion.set_index('id').join(temp.set_index('municipio_mitma')).reset_index()

            if used_zone == 'distrito':
                temp = self._read_relation_table('relaciones_municipio_mitma.csv')
                relacion = relacion.set_index('municipio_mitma').join(temp.set_index('municipio_mitma')).reset_index()

            to_rename = {
                'distrito': 'census_districts',
                'distrito_mitma': 'districts_mitma',
                'municipio': 'municipalities',
                'municipio_mitma': 'municipalities_mitma',
            }

            relacion.rename(columns=to_rename, inplace=True)

            temp_df = pd.DataFrame(relacion['id'].unique(), columns=['id']).set_index('id')
            for i in list(relacion.columns):
                if i != 'id':
                    temp_df = temp_df.join(relacion.groupby('id')[i].apply(set))

            return temp_df
