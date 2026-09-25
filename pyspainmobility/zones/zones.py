from pyspainmobility.utils import utils
import pandas as pd
import geopandas as gpd
import os
from os.path import expanduser
from typing import Optional

class Zones:
    def __init__(self, zones: str = 'municipalities', version: int = 2, output_directory: str = None):
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
            if os.path.isabs(output_directory):
                # Preserve absolute paths even if parent directories do not exist yet.
                self.output_path = output_directory
            else:
                # Treat relative paths as relative to home directory.
                home = expanduser("~")
                clean_path = output_directory.lstrip("/\\")
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

            if (
                not os.path.exists(local_path)
                or os.path.getsize(local_path) == 0
                or file_name.endswith((".gz", ".zip"))
            ):
                print("Checking necessary files....")
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
            self.complete_df = self._canonicalize_geodataframe(
                gpd.read_file(output_file_path)
            )
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
            complete_df = self._canonicalize_geodataframe(complete_df)
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
        complete_df = self._canonicalize_geodataframe(complete_df)
        complete_df.to_file(output_file_path, driver="GeoJSON")
        self.complete_df = complete_df

    @staticmethod
    def _canonicalize_geodataframe(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Return every zoning geometry with the same string ``id`` index.

        GeoJSON persists a named index as a regular property.  Without this
        normalization, a fresh download and a cached GeoJSON exposed different
        join contracts to users.
        """
        if not isinstance(frame, gpd.GeoDataFrame):
            raise TypeError("Zone geometry must be a GeoDataFrame.")
        result = frame.copy()
        id_column = next(
            (column for column in result.columns if str(column).lower() == "id"),
            None,
        )
        if id_column is not None:
            identifiers = result[id_column]
        elif result.index.name is not None and str(result.index.name).lower() == "id":
            identifiers = pd.Series(result.index, index=result.index)
        else:
            raise KeyError("Zone geometry must provide an 'id' column or index.")
        if identifiers.isna().any():
            raise ValueError("Zone geometry contains null or empty IDs.")
        identifiers = identifiers.astype(str).str.strip()
        if identifiers.eq("").any():
            raise ValueError("Zone geometry contains null or empty IDs.")
        if identifiers.duplicated().any():
            examples = identifiers[identifiers.duplicated()].head(5).tolist()
            raise ValueError("Zone geometry contains duplicate IDs: %s" % examples)
        result.index = pd.Index(identifiers, name="id")
        if id_column is not None:
            result = result.drop(columns=[id_column])
        return result


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

    @staticmethod
    def _normalize_relation_identifier(value, *, column: str) -> Optional[str]:
        """Normalize one scalar identifier from a zoning relation table."""
        if isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError(
                f"Relation column '{column}' contains a multi-valued entry. "
                "Use the version-2 relation table or resolve it explicitly before "
                "building a network mapping."
            )
        if pd.isna(value):
            return None
        identifier = str(value).strip()
        return identifier or None

    def get_network_mapping(
        self,
        source_column: str,
        target_column: str,
        source_ids=None,
    ) -> pd.DataFrame:
        """Return a verified, deterministic mapping for network aggregation.

        The official relationship file can contain several rows for one source
        zone.  Repeated *identical* pairs are harmless and are removed; two
        distinct targets for the same source are ambiguous and raise a
        :class:`ValueError`.  This prevents an aggregation from silently
        choosing an arbitrary territorial correspondence.

        Parameters
        ----------
        source_column, target_column : str
            Column names returned by :meth:`get_zone_relations`.
        source_ids : iterable, optional
            IDs occurring in the OD/network being aggregated.  When supplied,
            the output is restricted to these IDs and missing correspondences
            are reported before any flow is transformed.

        Returns
        -------
        pandas.DataFrame
            Two string columns, ``source_id`` and ``target_id``, sorted by
            ``source_id``.  It is accepted directly by
            :func:`pyspainmobility.network.aggregate_network` and
            :func:`pyspainmobility.network.aggregate_od_network`.
        """
        relations = self.get_zone_relations()
        if relations.index.name == "id" and "id" not in relations.columns:
            relations = relations.reset_index()
        required = {source_column, target_column}
        missing_columns = sorted(required.difference(relations.columns))
        if missing_columns:
            raise KeyError(
                "Unknown relation column(s): %s. Available columns: %s"
                % (missing_columns, sorted(relations.columns))
            )

        mapping = relations.loc[:, [source_column, target_column]].copy()
        mapping.columns = ["source_id", "target_id"]
        mapping["source_id"] = mapping["source_id"].map(
            lambda value: self._normalize_relation_identifier(
                value, column=source_column
            )
        )
        mapping["target_id"] = mapping["target_id"].map(
            lambda value: self._normalize_relation_identifier(
                value, column=target_column
            )
        )

        # A row without a source cannot describe a source-to-target mapping.
        mapping = mapping.loc[mapping["source_id"].notna()].copy()
        if source_ids is not None:
            if isinstance(source_ids, (str, bytes)):
                raise TypeError("source_ids must be an iterable of identifiers, not a string.")
            requested = pd.Index(
                [
                    self._normalize_relation_identifier(value, column="source_ids")
                    for value in source_ids
                ]
            )
            if requested.isna().any():
                raise ValueError("source_ids contains null or empty identifiers.")
            requested = requested.drop_duplicates()
            available = pd.Index(mapping["source_id"])
            absent = requested.difference(available)
            if not absent.empty:
                raise ValueError(
                    "No relation mapping is available for source IDs: %s"
                    % absent[:5].tolist()
                )
            mapping = mapping.loc[mapping["source_id"].isin(requested)]

        missing_target = mapping.loc[mapping["target_id"].isna(), "source_id"]
        if not missing_target.empty:
            examples = missing_target.drop_duplicates().head(5).tolist()
            raise ValueError(
                "Relation mapping has source IDs without a target in '%s': %s"
                % (target_column, examples)
            )

        mapping = mapping.drop_duplicates()
        target_counts = mapping.groupby("source_id", sort=False)["target_id"].nunique()
        ambiguous = target_counts.loc[target_counts > 1].index.tolist()
        if ambiguous:
            raise ValueError(
                "Relation mapping is not one-to-one: source IDs map to multiple "
                "targets in '%s': %s" % (target_column, ambiguous[:5])
            )

        return mapping.sort_values("source_id", kind="stable").reset_index(drop=True)

    def get_province_mapping(
        self,
        source_column: str = "districts_mitma",
        municipality_column: str = "municipalities",
        source_ids=None,
    ) -> pd.DataFrame:
        """Map MITMA zones to Spanish provinces through INE municipality IDs.

        Province geometries are not a native :class:`Zones` level.  Spanish
        INE municipality identifiers have five digits and their first two
        digits identify the province.  This helper exposes that hierarchy as a
        validated ``source_id``/``target_id`` mapping, where ``target_id`` is
        the two-digit INE province code.

        By default it maps MITMA districts, the level used by the mobility OD
        data.  As with :meth:`get_network_mapping`, ambiguous district-to-
        municipality relations raise instead of selecting a first match.
        """
        mapping = self.get_network_mapping(
            source_column=source_column,
            target_column=municipality_column,
            source_ids=source_ids,
        )
        valid_municipalities = mapping["target_id"].str.fullmatch(r"\d{5}")
        if not valid_municipalities.all():
            examples = mapping.loc[~valid_municipalities, "target_id"].head(5).tolist()
            raise ValueError(
                "Cannot derive province codes: '%s' must contain five-digit INE "
                "municipality identifiers; invalid values: %s"
                % (municipality_column, examples)
            )
        result = mapping.copy()
        result["target_id"] = result["target_id"].str[:2]
        return result
