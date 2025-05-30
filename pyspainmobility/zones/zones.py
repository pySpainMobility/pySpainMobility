from pyspainmobility.utils import utils
import pandas as pd
import geopandas as gpd
import os
import matplotlib

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
        zones = utils.zone_normalization(zones)
        self.zones = zones
        links = utils.available_zoning_data(version, zones)['link'].unique().tolist()

        # Get the data directory
        data_directory = utils.get_data_directory()
        self.data_directory = data_directory
        # for each link, check if the file exists in the data directory. If not, download it
        for link in links:
            # Get the file name
            file_name = link.split('/')[-1]

            # Check if the file exists in the data directory
            local_path = data_directory +'/'+ file_name

            if not os.path.exists(local_path):
                # Download the file
                "Downloading necessary files...."
                utils.download_file_if_not_existing(link, local_path)

            # unzip zonification_distritos.zip or zonificacion_municipios.zip if version is 1
            if version == 1 and file_name.endswith('.zip'):
                utils.unzip_file(os.path.join(data_directory, link.split('/')[-1]), data_directory)

        print('Zones already downloaded. Reading the files....')
        complete_df = None

        # check if a previously processed file exists in the output directory
        if output_directory is not None:
            output_path = os.path.join(output_directory, f'{zones}_{version}.geojson')
        else:
            output_path = os.path.join(data_directory, f'{zones}_{version}.geojson')

        if os.path.exists(output_path):
            print(f"File {output_path} already exists. Loading it...")
            complete_df = gpd.read_file(output_path)

        if version == 2:
            nombre = gpd.read_file(os.path.join(utils.get_data_directory(), f'nombres_{zones}.csv'))
            pop = gpd.read_file(os.path.join(utils.get_data_directory(), f'poblacion_{zones}.csv'))
            zonification = gpd.read_file(os.path.join(utils.get_data_directory(), f'zonificacion_{zones}.shp'))

            pop = pop.replace('NA', None)
            complete_df = nombre.set_index('ID').join(pop.set_index('field_1')).rename(columns={'field_2': 'population'})

            complete_df = complete_df.join(zonification.set_index('ID'))
            complete_df = gpd.GeoDataFrame(complete_df)

            complete_df.reset_index(inplace=True)
            complete_df.rename(columns={'ID': 'id'}, inplace=True)
            complete_df.set_index('id', inplace=True)

            if output_directory is not None:
                complete_df.to_file(os.path.join(output_directory, f'{zones}_{version}.geojson'), driver="GeoJSON")
            else:
                complete_df.to_file(os.path.join(data_directory, f'{zones}_{version}.geojson'), driver="GeoJSON")

        elif version == 1:
            zonification = gpd.read_file(os.path.join(utils.get_data_directory(), f'zonificacion-{zones}/{zones}_mitma.shp'))
            zonification.to_file(os.path.join(output_directory, f'{zones}_{version}.geojson'), driver="GeoJSON")

        self.complete_df = complete_df

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
        return self.complete_df

    def get_zone_relations(self):
        """
        TODO

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
        if self.version == 2:
            relacion = gpd.read_file(os.path.join(utils.get_data_directory(), 'relacion_ine_zonificacionMitma.csv'))

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
            relacion = gpd.read_file(os.path.join(utils.get_data_directory(), f'relaciones_{used_zone}_mitma.csv'))

            relacion.rename(columns={f'{used_zone}_mitma': 'id'}, inplace=True)

            if used_zone == 'municipio':
                temp = gpd.read_file(os.path.join(utils.get_data_directory(), 'relaciones_distrito_mitma.csv'))
                relacion = relacion.set_index('id').join(temp.set_index('municipio_mitma')).reset_index()

            if used_zone == 'distrito':
                temp = gpd.read_file(os.path.join(utils.get_data_directory(), 'relaciones_municipio_mitma.csv'))
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