from pyspainmobility.utils import utils
import pandas as pd
import geopandas as gpd
import os
from os.path import expanduser


class SpainZones:
    def __init__(self, zones: str = None, version: int = 1, output_directory: str = None, return_df: bool = True):

        utils.version_assert(version)
        utils.zone_assert(zones, version)

        zones = utils.zone_normalization(zones)

        links = utils.available_zoning_data(version, zones)['link'].unique().tolist()

        # Get the data directory
        data_directory = utils.get_data_directory()

        # for each link, check if the file exists in the data directory. If not, download it
        for link in links:
            # Get the file name
            file_name = link.split('/')[-1]

            # Check if the file exists in the data directory
            local_path = data_directory + file_name

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
            if return_df:
                return complete_df

        if version == 2:
            nombre = gpd.read_file(os.path.join(utils.get_data_directory(), f'nombres_{zones}.csv'))
            pop = gpd.read_file(os.path.join(utils.get_data_directory(), f'poblacion_{zones}.csv'))
            relacion = gpd.read_file(os.path.join(utils.get_data_directory(), 'relacion_ine_zonificacionMitma.csv'))
            zonification = gpd.read_file(os.path.join(utils.get_data_directory(), f'zonificacion_{zones}.shp'))

            pop = pop.replace('NA', None)
            complete_df = nombre.set_index('ID').join(pop.set_index('field_1')).rename(columns={'field_2': 'population'})

            excluded_column = {
                'gaus': 'luas_mitma',
                'municipios': 'municipalities_mitma',
                'distritos': 'districts_mitma'
            }

            relacion.rename(columns={
                'seccion_ine': 'census_sections',
                'distrito_ine': 'census_districts',
                'municipio_ine': 'municipalities',
                'municipio_mitma': 'municipalities_mitma',
                'distrito_mitma': 'districts_mitma',
                'gau_mitma': 'luas_mitma'
            }, inplace=True)
            relacion = relacion.replace('NA', None)

            for cname in list(relacion.columns):
                if cname != excluded_column[zones]:
                    complete_df = complete_df.join(pd.DataFrame(relacion.groupby(excluded_column[zones])[cname].apply(set)))

            complete_df = complete_df.join(zonification.set_index('ID'))
            complete_df = gpd.GeoDataFrame(complete_df)

            complete_df.reset_index(inplace=True)
            complete_df.rename(columns={'ID': 'id'}, inplace=True)
            complete_df.set_index(zones, inplace=True)

            if output_directory is not None:
                complete_df.to_file(os.path.join(output_directory, f'{zones}_{version}.geojson'), driver="GeoJSON")
            else:
                complete_df.to_file(os.path.join(data_directory, f'{zones}_{version}.geojson'), driver="GeoJSON")

        elif version == 1:
            used_zone = zones[:-1]

            relacion = gpd.read_file(os.path.join(utils.get_data_directory(), f'relaciones_{used_zone}_mitma.csv'))
            zonification = gpd.read_file(os.path.join(utils.get_data_directory(), f'zonificacion-{zones}/{zones}_mitma.shp'))

            relacion.rename(columns={f'{used_zone}_mitma': 'id'}, inplace=True)

            if used_zone == 'municipio':
                temp = gpd.read_file(os.path.join(utils.get_data_directory(),'relaciones_distrito_mitma.csv'))
                relacion = relacion.set_index('id').join(temp.set_index('municipio_mitma')).reset_index()

            if used_zone == 'distrito':
                temp = gpd.read_file(os.path.join(utils.get_data_directory(),'relaciones_municipio_mitma.csv'))
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

            relacion = temp_df

            complete_df = relacion.join(zonification.set_index('ID'))
            complete_df = gpd.GeoDataFrame(complete_df)
            complete_df.to_file(os.path.join(output_directory, f'{zones}_{version}.geojson'), driver="GeoJSON")

        if return_df:
            # remove the geometry column from the dataframe
            return complete_df
        else:
            return None