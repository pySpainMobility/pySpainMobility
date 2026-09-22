from pandas.errors import EmptyDataError 
from pyspainmobility.utils import utils
import os
import pandas as pd
import tqdm
import warnings
from os.path import expanduser
from typing import Optional

# Optional Arrow import – used when backend='arrow'
try:
    import pyarrow as pa
    import pyarrow.csv as pacsv
except ImportError:
    pa = None
    pacsv = None

# Optional Polars import – used when backend='polars'
try:
    import polars as pl
except ImportError:
    pl = None

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
        Whether to use Dask for processing large datasets with the Arrow or
        pandas backend. Default is False. Ignored by the Polars backend, which
        already executes the multi-file query in parallel.
    backend : str
        Dataframe backend used while reading and processing files. The default
        'auto' selects Polars when installed, then Arrow, then pandas. Use
        'polars' for a lazy, streaming pipeline, 'arrow' for Apache
        Arrow-backed pandas columns, or 'pandas' for classic pandas dtypes.
        Polars and Arrow both return an Arrow-backed pandas DataFrame when a
        public method is called with ``return_df=True``.
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
    def __init__(
        self,
        version: int = 2,
        zones: str = 'municipalities',
        start_date: str = None,
        end_date: str = None,
        output_directory: str = None,
        use_dask: bool = False,
        backend: str = "auto",
    ):
        self.version = version
        self.zones = zones
        self.start_date = start_date
        self.output_directory = output_directory
        self.use_dask = use_dask
        self.requested_backend = str(backend).lower()
        self.backend = self.requested_backend

        if self.backend not in {"auto", "arrow", "pandas", "polars"}:
            raise ValueError(
                "backend must be one of 'auto', 'arrow', 'pandas', or 'polars'"
            )
        if self.backend == "auto":
            if pl is not None:
                self.backend = "polars"
            elif pa is not None and pacsv is not None:
                self.backend = "arrow"
            else:
                self.backend = "pandas"
        if self.backend == "arrow" and (pa is None or pacsv is None):
            warnings.warn(
                "backend='arrow' requested but pyarrow is not installed. "
                "Falling back to backend='pandas'. Install pyarrow for better "
                "performance and lower memory usage.",
                RuntimeWarning,
                stacklevel=2,
            )
            self.backend = "pandas"
        if self.backend == "polars" and pl is None:
            raise ImportError(
                "backend='polars' requires Polars. Reinstall pyspainmobility "
                "so its base dependencies are available."
            )

        if self.use_dask and self.backend == "polars":
            warnings.warn(
                "use_dask=True is ignored by backend='polars' because Polars "
                "already executes the multi-file pipeline in parallel.",
                RuntimeWarning,
                stacklevel=2,
            )
        elif self.use_dask and dd is None:
            raise ImportError("Dask is not installed. Please install dask to use use_dask=True")

        utils.zone_assert(zones, version)
        utils.version_assert(version)
        if start_date is None:
            raise ValueError("start_date is required")
        utils.date_format_assert(start_date)
        if end_date is None:
            end_date = start_date
        utils.date_format_assert(end_date)
        self.end_date = end_date

        # --- fail fast if the end date is before the start date ---
        from pandas import to_datetime
        if to_datetime(end_date) < to_datetime(start_date):
            raise ValueError(
                f"end_date ({end_date}) must be the same as or after start_date ({start_date})."
            )

        self.zones = utils.zone_normalization(zones)

        data_directory = utils.get_data_directory()

        self.dates = utils.get_dates_between(start_date, end_date)
        self._acquisition_manifests = {}
        self._od_processing_outcomes = {}

        try:
            valid_dates = utils.get_valid_dates(self.version)
        except Exception as exc:
            raise RuntimeError(
                "Could not reach the MITMA open-data server while fetching the list of available dates "
                f"for version {self.version}. This is usually a temporary problem on the government's side "
                "(e.g. HTTP 500 / service maintenance). Please wait a few minutes and try again. "
                f"Original error: {exc}"
            ) from exc
        if not valid_dates:
            raise RuntimeError(
                f"Could not resolve valid dates for version {self.version}. "
                "Please check network/data source availability and try again."
            )

        first, last = valid_dates[0], valid_dates[-1]
        if self.dates[0] < first or self.dates[-1] > last:
            raise ValueError(
                f"Version {self.version} data are only available from {first} to {last}. "
                f"You requested from {self.start_date} to {self.end_date}.")

        # proper directory handling
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

    def _read_pipe_file(self, filepath: str, dtype: dict = None) -> pd.DataFrame:
        """
        Read MITMA pipe-separated files using the configured backend.
        """
        if self.backend == "arrow":
            return self._read_pipe_file_arrow(filepath, dtype=dtype)
        if self.backend == "polars":
            return self._read_pipe_file_polars(filepath, dtype=dtype)
        return self._read_pipe_file_pandas(filepath, dtype=dtype)

    @staticmethod
    def _normalize_column_name(name: str) -> str:
        """
        Normalize a single column name for case-insensitive matching.
        """
        return str(name).replace("\ufeff", "").strip().lower()

    @staticmethod
    def _align_dtype_map_to_source_columns(filepath: str, dtype: dict = None) -> Optional[dict]:
        """
        Align dtype mapping keys to real source column names, handling
        BOM/case/whitespace differences before parsing.
        """
        if not dtype:
            return dtype

        try:
            header_df = pd.read_csv(
                filepath,
                sep="|",
                compression="infer",
                encoding="utf-8-sig",
                nrows=0,
            )
        except Exception:
            return dtype

        normalized_to_source = {
            Mobility._normalize_column_name(col): col for col in header_df.columns
        }
        aligned = {}
        for requested_col, requested_dtype in dtype.items():
            source_col = normalized_to_source.get(
                Mobility._normalize_column_name(requested_col)
            )
            if source_col is not None:
                aligned[source_col] = requested_dtype

        return aligned or dtype

    @staticmethod
    def _read_pipe_file_pandas(filepath: str, dtype: dict = None) -> pd.DataFrame:
        """
        Pandas parser with BOM-safe UTF-8 handling.
        """
        aligned_dtype = Mobility._align_dtype_map_to_source_columns(filepath, dtype)
        return pd.read_csv(
            filepath,
            sep="|",
            compression="infer",
            encoding="utf-8-sig",
            dtype=aligned_dtype,
            low_memory=False,
        )

    @staticmethod
    def _read_pipe_file_arrow(filepath: str, dtype: dict = None) -> pd.DataFrame:
        """
        Apache Arrow CSV parser, converted to an Arrow-backed pandas DataFrame.
        Falls back to pandas parser if Arrow cannot parse the source.
        """
        if pa is None or pacsv is None:
            warnings.warn(
                "pyarrow is not available. Falling back to pandas parser. "
                "Install pyarrow for better performance and lower memory usage.",
                RuntimeWarning,
                stacklevel=2,
            )
            return Mobility._read_pipe_file_pandas(filepath, dtype=dtype)

        column_types = None
        aligned_dtype = Mobility._align_dtype_map_to_source_columns(filepath, dtype)
        if aligned_dtype:
            column_types = {}
            for col, typ in aligned_dtype.items():
                if str(typ).lower() == "string":
                    column_types[col] = pa.string()

        try:
            table = pacsv.read_csv(
                filepath,
                read_options=pacsv.ReadOptions(encoding="utf8", use_threads=True),
                parse_options=pacsv.ParseOptions(delimiter="|"),
                convert_options=pacsv.ConvertOptions(
                    strings_can_be_null=True,
                    column_types=column_types,
                ),
            )
            return table.to_pandas(types_mapper=pd.ArrowDtype)
        except Exception as exc:
            print(f"[warn] Arrow parser failed for {filepath}: {exc}. Falling back to pandas parser.")
            return Mobility._read_pipe_file_pandas(filepath, dtype=dtype)

    @staticmethod
    def _read_pipe_file_polars(filepath: str, dtype: dict = None) -> pd.DataFrame:
        """
        Read a pipe-separated MITMA file with Polars and expose the result as
        an Arrow-backed pandas DataFrame for public API compatibility.
        """
        if pl is None:
            raise ImportError(
                "Polars is not available. Reinstall pyspainmobility so its "
                "base dependencies are available."
            )

        try:
            frame = Mobility._scan_pipe_files_polars(filepath).collect(
                engine="streaming"
            )
            return frame.to_arrow().to_pandas(types_mapper=pd.ArrowDtype)
        except Exception as exc:
            print(
                f"[warn] Polars parser failed for {filepath}: {exc}. "
                "Falling back to pandas parser."
            )
            return Mobility._read_pipe_file_pandas(filepath, dtype=dtype)

    def _finalize_backend_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize output dtypes according to the selected backend.
        """
        if self.backend not in {"arrow", "polars"} or df is None:
            return df
        try:
            return df.convert_dtypes(dtype_backend="pyarrow")
        except TypeError:
            return df.convert_dtypes()

    @staticmethod
    def _normalize_input_columns(df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize incoming column names to avoid translation misses caused by
        BOMs, casing differences, and surrounding whitespace.
        """
        normalized = df.copy()
        normalized.columns = [
            str(col).replace("\ufeff", "").strip().lower() for col in normalized.columns
        ]
        return normalized

    @staticmethod
    def _normalize_identifier_series(series: pd.Series) -> pd.Series:
        """
        Keep zoning identifiers as strings and remove float artifacts/grouping
        separators (e.g. '01001.0' -> '01001', '28.079' -> '28079').
        """
        normalized = series.astype("string").str.strip()
        normalized = normalized.replace({"": pd.NA, "NA": pd.NA, "nan": pd.NA, "None": pd.NA})
        normalized = normalized.str.replace(r"\.0+$", "", regex=True)
        normalized = normalized.str.replace(r"(?<=\d)\.(?=\d)", "", regex=True)
        return normalized

    @staticmethod
    def _normalize_date_series(series: pd.Series) -> pd.Series:
        """
        Convert MITMA date formats to YYYY-MM-DD.
        """
        normalized = series.astype("string").str.strip()
        normalized = normalized.replace({"": pd.NA, "NA": pd.NA, "nan": pd.NA, "None": pd.NA})
        normalized = normalized.str.replace(r"\.0+$", "", regex=True)
        normalized = normalized.str.replace("-", "", regex=False)
        normalized = normalized.str.replace("/", "", regex=False)
        normalized = normalized.str.replace(" ", "", regex=False)
        normalized = normalized.str.zfill(8)
        return (
            normalized.str.slice(0, 4)
            + "-"
            + normalized.str.slice(4, 6)
            + "-"
            + normalized.str.slice(6, 8)
        )

    @staticmethod
    def _to_numeric(series: pd.Series, strip_thousands: bool = False) -> pd.Series:
        """
        Safe numeric conversion with support for comma decimal separators.
        """
        normalized = series.astype("string").str.strip()
        normalized = normalized.replace({"": pd.NA, "NA": pd.NA, "nan": pd.NA, "None": pd.NA})
        normalized = normalized.str.replace(",", ".", regex=False)
        if strip_thousands:
            # A single ``.xxx`` is ambiguous in MITMA data and is treated as a
            # decimal value. Only two or more grouped triplets are unambiguously
            # a thousands notation. This decision must be row-local: using the
            # values in another file would make a multi-file result batch-dependent.
            thousands_mask = normalized.str.fullmatch(r"[+-]?\d{1,3}(?:\.\d{3}){2,}")
            normalized = normalized.where(
                ~thousands_mask,
                normalized.str.replace(".", "", regex=False),
            )
        return pd.to_numeric(normalized, errors="coerce")

    @staticmethod
    def _to_mitma_integer(series: pd.Series) -> pd.Series:
        """
        Parse MITMA count-like fields to integers.

        MITMA files encode large integers with dots (e.g. ``2214.577``), which
        pandas can otherwise interpret as decimals. This parser follows the
        project convention used in examples/issues:
        - ``1.0`` -> ``1``
        - ``2214.577`` -> ``2214577``
        - ``128.457`` -> ``128457``
        """
        normalized = series.astype("string").str.strip()
        normalized = normalized.replace({"": pd.NA, "NA": pd.NA, "nan": pd.NA, "None": pd.NA})
        normalized = normalized.str.replace(",", ".", regex=False)

        # Keep integer-like values as-is (e.g. "1.0"), but compact dot-separated
        # values used as grouped counts.
        integer_like = normalized.str.fullmatch(r"[+-]?\d+(?:\.0+)?")
        compacted = normalized.where(integer_like, normalized.str.replace(".", "", regex=False))
        return pd.to_numeric(compacted, errors="coerce").astype("Int64")

    @staticmethod
    def _polars_clean_string(column: str):
        """Return a normalized Polars string expression for MITMA fields."""
        return pl.col(column).str.strip_chars()

    @staticmethod
    def _polars_numeric(column: str, strip_thousands: bool = False):
        """Polars equivalent of :meth:`_to_numeric`."""
        normalized = (
            Mobility._polars_clean_string(column)
            .str.replace_all(",", ".", literal=True)
        )
        if strip_thousands:
            thousands_pattern = r"^[+-]?\d{1,3}(?:\.\d{3}){2,}$"
            normalized = pl.when(normalized.str.contains(thousands_pattern)).then(
                normalized.str.replace_all(".", "", literal=True)
            ).otherwise(normalized)
        return normalized.cast(pl.Float64, strict=False)

    @staticmethod
    def _polars_date(column: str):
        """Polars equivalent of :meth:`_normalize_date_series`."""
        normalized = (
            Mobility._polars_clean_string(column)
            .str.replace(r"\.0+$", "")
            .str.replace_all("-", "", literal=True)
            .str.replace_all("/", "", literal=True)
            .str.replace_all(" ", "", literal=True)
            .str.pad_start(8, "0")
        )
        return pl.concat_str(
            [
                normalized.str.slice(0, 4),
                pl.lit("-"),
                normalized.str.slice(4, 2),
                pl.lit("-"),
                normalized.str.slice(6, 2),
            ]
        )

    @staticmethod
    def _polars_identifier(column: str):
        """Polars equivalent of :meth:`_normalize_identifier_series`."""
        return (
            Mobility._polars_clean_string(column)
            .str.replace(r"\.0+$", "")
            .str.replace_all(".", "", literal=True)
        )

    @staticmethod
    def _scan_pipe_files_polars(filepaths, include_file_paths=False):
        """Create a normalized lazy scan for one or more MITMA files."""
        return pl.scan_csv(
            filepaths,
            separator="|",
            encoding="utf8-lossy",
            infer_schema=False,
            # ``empty_string_is_null`` was introduced after the last Polars
            # release supporting Python 3.9.  Listing the empty token as a
            # null value preserves the same parsing contract across both APIs.
            null_values=["", "NA", "nan", "None"],
            with_column_names=lambda columns: [
                Mobility._normalize_column_name(column) for column in columns
            ],
            include_file_paths="_source_path" if include_file_paths else None,
        )

    @staticmethod
    def _polars_to_pandas(frame):
        """Expose a Polars result through the library's pandas API."""
        return frame.to_arrow().to_pandas(types_mapper=pd.ArrowDtype)

    @staticmethod
    def _valid_input_files(filepaths):
        """Discard missing or empty downloads without aborting a batch."""
        valid = []
        for filepath in filepaths:
            if not os.path.exists(filepath):
                print(f"[warn] File does not exist, skipped: {filepath}")
            elif os.path.getsize(filepath) == 0:
                print(f"[warn] Empty file skipped: {filepath}")
            else:
                valid.append(filepath)
        return valid

    def _build_od_lazy_polars(self, filepaths, keep_activity, social_agg):
        """Build the optimized Polars query plan for one or more OD files."""
        source_to_target = {
            "actividad_origen": "activity_origin",
            "actividad_destino": "activity_destination",
            "renta": "income",
            "edad": "age",
            "sexo": "gender",
        }
        required_source = [
            "fecha",
            "periodo",
            "origen",
            "destino",
            "viajes",
            "viajes_km",
        ]

        lazy_frame = self._scan_pipe_files_polars(filepaths)
        source_columns = set(lazy_frame.collect_schema().names())
        missing = [column for column in required_source if column not in source_columns]
        if missing:
            print(
                f"[warn] Missing expected columns before translation: {missing}. "
                f"Columns found: {sorted(source_columns)}"
            )
            return None

        expressions = [
            self._polars_date("fecha").alias("date"),
            self._polars_clean_string("periodo")
            .cast(pl.Int64, strict=False)
            .alias("hour"),
            self._polars_identifier("origen").alias("id_origin"),
            self._polars_identifier("destino").alias("id_destination"),
        ]

        if keep_activity:
            activity_mapping = {
                "casa": "home",
                "frecuente": "other_frequent",
                "trabajo_estudio": "work_or_study",
                "no_frecuente": "other_non_frequent",
            }
            for source in ("actividad_origen", "actividad_destino"):
                expression = (
                    self._polars_clean_string(source).replace(activity_mapping)
                    if source in source_columns
                    else pl.lit(None, dtype=pl.String)
                )
                expressions.append(expression.alias(source_to_target[source]))

        if social_agg:
            for source in ("renta", "edad", "sexo"):
                expression = (
                    self._polars_clean_string(source)
                    if source in source_columns
                    else pl.lit(None, dtype=pl.String)
                )
                if source == "sexo":
                    expression = expression.replace(
                        {"hombre": "male", "mujer": "female"}
                    )
                expressions.append(expression.alias(source_to_target[source]))

        expressions.extend(
            [
                self._polars_numeric("viajes", strip_thousands=True).alias(
                    "n_trips"
                ),
                self._polars_numeric("viajes_km", strip_thousands=True).alias(
                    "trips_total_length_km"
                ),
            ]
        )

        group_cols = ["date", "hour", "id_origin", "id_destination"]
        if keep_activity:
            group_cols += ["activity_origin", "activity_destination"]
        if social_agg:
            group_cols += ["income", "age", "gender"]

        return (
            lazy_frame.select(expressions)
            .drop_nulls(
                [
                    "date",
                    "id_origin",
                    "id_destination",
                    "n_trips",
                    "trips_total_length_km",
                ]
            )
            .group_by(group_cols)
            .agg(
                pl.col("n_trips").sum(),
                pl.col("trips_total_length_km").sum(),
            )
            .sort(group_cols, nulls_last=True)
        )

    def _process_od_files_polars(
        self,
        filepaths,
        keep_activity,
        social_agg,
        as_pandas=True,
    ):
        """Execute one optimized Polars plan across all requested OD files."""
        filepaths = self._valid_input_files(filepaths)
        if not filepaths:
            return None
        try:
            query = self._build_od_lazy_polars(
                filepaths,
                keep_activity=keep_activity,
                social_agg=social_agg,
            )
            if query is None:
                return None
            result = query.collect(engine="streaming")
            if result.is_empty():
                print("[warn] No valid OD rows after preprocessing")
                return None
            return self._polars_to_pandas(result) if as_pandas else result
        except Exception as exc:
            print(f"[ERROR] Error processing OD data with Polars: {exc}")
            return None

    def _process_single_od_file_polars(self, filepath, keep_activity, social_agg):
        """Compatibility wrapper for processing one OD file with Polars."""
        return self._process_od_files_polars(
            [filepath],
            keep_activity=keep_activity,
            social_agg=social_agg,
        )

    def _process_single_od_file(self, filepath, keep_activity, social_agg):
        """Extract common OD file processing logic."""
        
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

        if self.backend == "polars":
            return self._process_single_od_file_polars(
                filepath,
                keep_activity=keep_activity,
                social_agg=social_agg,
            )
        
        try:
            print(f"Reading {'gzipped' if filepath.endswith('.gz') else 'regular'} file...")
            df = self._read_pipe_file(
                filepath,
                dtype={
                    "fecha": "string",
                    "periodo": "string",
                    "origen": "string",
                    "destino": "string",
                    "actividad_origen": "string",
                    "actividad_destino": "string",
                    "residencia": "string",
                    "renta": "string",
                    "edad": "string",
                    "sexo": "string",
                    "viajes": "string",
                    "viajes_km": "string",
                },
            )
            df = self._normalize_input_columns(df)

            if df.empty:
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

        required_cols = ["date", "hour", "id_origin", "id_destination", "n_trips", "trips_total_length_km"]
        missing = [col for col in required_cols if col not in df.columns]
        if missing:
            print(
                f"[warn] {os.path.basename(filepath)} missing expected columns after translation: {missing}. "
                f"Columns found: {list(df.columns)}"
            )
            return None

        for optional_col in ["activity_origin", "activity_destination", "income", "age", "gender"]:
            if optional_col not in df.columns:
                df[optional_col] = pd.NA

        df["date"] = self._normalize_date_series(df["date"])
        df["id_origin"] = self._normalize_identifier_series(df["id_origin"])
        df["id_destination"] = self._normalize_identifier_series(df["id_destination"])
        if "residence_province_ine_code" in df.columns:
            df["residence_province_ine_code"] = self._normalize_identifier_series(df["residence_province_ine_code"])

        hour_numeric = self._to_numeric(df["hour"])
        if hour_numeric.notna().all():
            df["hour"] = hour_numeric.astype(int)
        else:
            df["hour"] = df["hour"].astype("string").str.strip()

        df["n_trips"] = self._to_numeric(df["n_trips"], strip_thousands=True)
        df["trips_total_length_km"] = self._to_numeric(df["trips_total_length_km"], strip_thousands=True)

        df.dropna(
            subset=["date", "id_origin", "id_destination", "n_trips", "trips_total_length_km"],
            inplace=True,
        )
        if df.empty:
            print(f"[warn] {os.path.basename(filepath)} has no valid rows after preprocessing, skipped")
            return None

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

        # MITMA uses missing demographic values when information cannot be
        # provided (for example for privacy reasons).  They are still valid
        # mobility observations, so retaining optional dimensions must not
        # remove their flows from the aggregate.
        df = df.groupby(group_cols, as_index=False, dropna=False)[
            ["n_trips", "trips_total_length_km"]
        ].sum()
        
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

        m_type = "Viajes" if self.version == 2 else "maestra1"
        if self.version == 1:
            keep_activity = False
            social_agg = False

        local_list = self._donwload_helper(m_type)
        print("Generating parquet file for ODs....")

        if self.backend == "polars":
            frame = self._process_od_files_polars(
                local_list,
                keep_activity=keep_activity,
                social_agg=social_agg,
                as_pandas=False,
            )
            self._remember_od_processing(m_type, local_list, frame is not None)
            if frame is None:
                print("No valid data found")
                return None
            self._saving_parquet(frame, m_type)
            return self._polars_to_pandas(frame) if return_df else None

        if self.use_dask:
            return self._process_od_data_dask(
                local_list,
                m_type,
                keep_activity,
                social_agg,
                return_df,
            )

        frames = []
        for filepath in tqdm.tqdm(local_list):
            result = self._process_single_od_file(
                filepath,
                keep_activity,
                social_agg,
            )
            if result is not None:
                frames.append(result)

        if not frames:
            self._remember_od_processing(m_type, local_list, False)
            print("No valid data found")
            return None

        print("Concatenating all the dataframes....")
        frame = frames[0] if len(frames) == 1 else pd.concat(frames)
        frame = self._finalize_backend_dataframe(frame)
        self._remember_od_processing(m_type, local_list, True)
        self._saving_parquet(frame, m_type)
        return frame if return_df else None

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
            self._remember_od_processing(m_type, local_list, False)
            print("No valid data found")
            return None
        
        print("Concatenating results...")
        df = pd.concat(valid_dfs, ignore_index=True)
        df = self._finalize_backend_dataframe(df)
        self._remember_od_processing(m_type, local_list, True)
        
        self._saving_parquet(df, m_type)
        return df if return_df else None

    def _build_overnight_lazy_polars(self, filepaths):
        """Build the Polars plan for overnight-stay files."""
        lazy_frame = self._scan_pipe_files_polars(filepaths)
        required_source = {
            "fecha",
            "zona_residencia",
            "zona_pernoctacion",
            "personas",
        }
        source_columns = set(lazy_frame.collect_schema().names())
        missing = sorted(required_source - source_columns)
        if missing:
            print(f"[warn] Missing expected overnight-stay columns: {missing}")
            return None

        return (
            lazy_frame.select(
                self._polars_date("fecha").alias("date"),
                self._polars_identifier("zona_residencia").alias(
                    "residence_area"
                ),
                self._polars_identifier("zona_pernoctacion").alias(
                    "overnight_stay_area"
                ),
                self._polars_numeric("personas", strip_thousands=True).alias(
                    "people"
                ),
            )
            .drop_nulls(
                ["date", "residence_area", "overnight_stay_area", "people"]
            )
        )

    def _process_overnight_files_polars(self, filepaths, as_pandas=True):
        """Execute one optimized Polars plan across overnight-stay files."""
        filepaths = self._valid_input_files(filepaths)
        if not filepaths:
            return None
        try:
            query = self._build_overnight_lazy_polars(filepaths)
            if query is None:
                return None
            result = query.collect(engine="streaming")
            if result.is_empty():
                return None
            return self._polars_to_pandas(result) if as_pandas else result
        except Exception as exc:
            print(f"Error processing overnight-stay data with Polars: {exc}")
            return None

    def _build_number_of_trips_lazy_polars(self, filepaths):
        """Build the Polars plan for number-of-trips files."""
        lazy_frame = self._scan_pipe_files_polars(filepaths)
        area_source = "zona_pernoctacion" if self.version == 2 else "distrito"
        required_source = {"fecha", area_source, "numero_viajes", "personas"}
        source_columns = set(lazy_frame.collect_schema().names())
        missing = sorted(required_source - source_columns)
        if missing:
            print(f"[warn] Missing expected number-of-trips columns: {missing}")
            return None

        base_expressions = [
            self._polars_date("fecha").alias("date"),
            self._polars_identifier(area_source).alias("overnight_stay_area"),
        ]
        demographic_expressions = []
        if self.version == 2:
            demographic_expressions = [
                (
                    self._polars_clean_string("edad")
                    if "edad" in source_columns
                    else pl.lit(None, dtype=pl.String)
                ).alias("age"),
                (
                    self._polars_clean_string("sexo").replace(
                        {"hombre": "male", "mujer": "female"}
                    )
                    if "sexo" in source_columns
                    else pl.lit(None, dtype=pl.String)
                ).alias("gender"),
            ]

        measure_expressions = [
            self._polars_clean_string("numero_viajes")
            .str.replace(r"\.0+$", "")
            .alias("number_of_trips"),
            self._polars_numeric("personas", strip_thousands=True).alias("people"),
        ]
        expressions = base_expressions + demographic_expressions + measure_expressions
        if self.version == 1:
            expressions += [
                pl.lit(None, dtype=pl.String).alias("age"),
                pl.lit(None, dtype=pl.String).alias("gender"),
            ]

        return lazy_frame.select(expressions).drop_nulls(
            ["date", "overnight_stay_area", "number_of_trips", "people"]
        )

    def _process_number_of_trips_files_polars(self, filepaths, as_pandas=True):
        """Execute one optimized Polars plan across number-of-trips files."""
        filepaths = self._valid_input_files(filepaths)
        if not filepaths:
            return None
        try:
            query = self._build_number_of_trips_lazy_polars(filepaths)
            if query is None:
                return None
            result = query.collect(engine="streaming")
            if result.is_empty():
                return None
            return self._polars_to_pandas(result) if as_pandas else result
        except Exception as exc:
            print(f"Error processing number-of-trips data with Polars: {exc}")
            return None

    def _process_single_overnight_file(self, filepath: str):
        """
        Parse and normalize one overnight stays file.
        """
        if self.backend == "polars":
            return self._process_overnight_files_polars([filepath])

        try:
            df = self._read_pipe_file(
                filepath,
                dtype={
                    "fecha": "string",
                    "zona_residencia": "string",
                    "zona_pernoctacion": "string",
                    "personas": "string",
                },
            )
            df = self._normalize_input_columns(df)
            if df.empty:
                return None

            df.rename(
                columns={
                    "fecha": "date",
                    "zona_residencia": "residence_area",
                    "zona_pernoctacion": "overnight_stay_area",
                    "personas": "people",
                },
                inplace=True,
            )

            required_cols = ["date", "residence_area", "overnight_stay_area", "people"]
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                print(
                    f"[warn] {os.path.basename(filepath)} missing expected columns after translation: {missing}. "
                    f"Columns found: {list(df.columns)}"
                )
                return None

            df["date"] = self._normalize_date_series(df["date"])
            df["residence_area"] = self._normalize_identifier_series(df["residence_area"])
            df["overnight_stay_area"] = self._normalize_identifier_series(df["overnight_stay_area"])
            df["people"] = self._to_numeric(df["people"], strip_thousands=True)
            df.dropna(subset=required_cols, inplace=True)

            return df
        except EmptyDataError:
            print(f"[warn] {os.path.basename(filepath)} triggered EmptyDataError, skipped")
            return None
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            return None

    def _process_single_number_of_trips_file(self, filepath: str):
        """
        Parse and normalize one number-of-trips file for the active version.
        """
        if self.backend == "polars":
            return self._process_number_of_trips_files_polars([filepath])

        try:
            if self.version == 2:
                dtype = {
                    "fecha": "string",
                    "zona_pernoctacion": "string",
                    "edad": "string",
                    "sexo": "string",
                    "numero_viajes": "string",
                    "personas": "string",
                }
                rename_map = {
                    "fecha": "date",
                    "zona_pernoctacion": "overnight_stay_area",
                    "edad": "age",
                    "sexo": "gender",
                    "numero_viajes": "number_of_trips",
                    "personas": "people",
                }
            else:
                dtype = {
                    "fecha": "string",
                    "distrito": "string",
                    "numero_viajes": "string",
                    "personas": "string",
                }
                rename_map = {
                    "fecha": "date",
                    "distrito": "overnight_stay_area",
                    "numero_viajes": "number_of_trips",
                    "personas": "people",
                }

            df = self._read_pipe_file(filepath, dtype=dtype)
            df = self._normalize_input_columns(df)
            if df.empty:
                return None

            df.rename(columns=rename_map, inplace=True)

            required_cols = ["date", "overnight_stay_area", "number_of_trips", "people"]
            missing = [col for col in required_cols if col not in df.columns]
            if missing:
                print(
                    f"[warn] {os.path.basename(filepath)} missing expected columns after translation: {missing}. "
                    f"Columns found: {list(df.columns)}"
                )
                return None

            if "age" not in df.columns:
                df["age"] = pd.NA
            if "gender" not in df.columns:
                df["gender"] = pd.NA

            df["date"] = self._normalize_date_series(df["date"])
            df["overnight_stay_area"] = self._normalize_identifier_series(df["overnight_stay_area"])
            df["number_of_trips"] = df["number_of_trips"].astype("string").str.strip().str.replace(r"\.0+$", "", regex=True)
            df["people"] = self._to_numeric(df["people"], strip_thousands=True)

            df.replace({"gender": {"hombre": "male", "mujer": "female"}}, inplace=True)
            df.dropna(subset=["date", "overnight_stay_area", "number_of_trips", "people"], inplace=True)

            return df
        except EmptyDataError:
            print(f"[warn] {os.path.basename(filepath)} triggered EmptyDataError, skipped")
            return None
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            return None

    def _process_tabular_files(self, local_list, processor):
        """Run a pandas/Arrow file processor, optionally through Dask."""
        processed = None
        if self.use_dask and len(local_list) > 1:
            delayed_tasks = [delayed(processor)(filepath) for filepath in local_list]
            try:
                processed = dd.compute(*delayed_tasks)
            except Exception as exc:
                print(
                    f"Dask computation failed: {exc}. "
                    "Falling back to sequential processing..."
                )

        if processed is None:
            processed = [processor(filepath) for filepath in tqdm.tqdm(local_list)]

        valid_frames = [frame for frame in processed if frame is not None]
        if not valid_frames:
            return None
        return pd.concat(valid_frames, ignore_index=True)

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
        if self.version == 1:
            raise Exception('Overnight stays data is not available for version 1. Please use version 2.')

        m_type = "Pernoctaciones"
        local_list = self._donwload_helper(m_type)
        print("Generating parquet file for Overnight Stays....")

        if self.backend == "polars":
            frame = self._process_overnight_files_polars(
                local_list,
                as_pandas=False,
            )
        else:
            frame = self._process_tabular_files(
                local_list,
                self._process_single_overnight_file,
            )
            frame = self._finalize_backend_dataframe(frame)

        if frame is None:
            print("No valid data found")
            return None

        self._saving_parquet(frame, m_type)
        if not return_df:
            return None
        return self._polars_to_pandas(frame) if self.backend == "polars" else frame

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
        m_type = "Personas" if self.version == 2 else "maestra2"
        local_list = self._donwload_helper(m_type)
        print("Generating parquet file for Number of Trips....")

        if self.backend == "polars":
            frame = self._process_number_of_trips_files_polars(
                local_list,
                as_pandas=False,
            )
        else:
            frame = self._process_tabular_files(
                local_list,
                self._process_single_number_of_trips_file,
            )
            frame = self._finalize_backend_dataframe(frame)

        if frame is None:
            print("No valid data found")
            return None

        self._saving_parquet(frame, m_type)
        if not return_df:
            return None
        return self._polars_to_pandas(frame) if self.backend == "polars" else frame

    def _saving_parquet(self, df, m_type: str):
        print('Writing the parquet file....')
        output_file = os.path.join(
            self.output_path,
            f"{m_type}_{self.zones}_{self.start_date}_{self.end_date}_v{self.version}.parquet",
        )
        if pl is not None and isinstance(df, pl.DataFrame):
            df.write_parquet(output_file)
        else:
            df.to_parquet(output_file, index=False)
        print('Parquet file generated successfully at ', output_file)

    def get_acquisition_manifest(self, m_type: str = "Viajes") -> pd.DataFrame:
        """Return the pre-filter file-acquisition record for one data type.

        The manifest is populated by :meth:`_donwload_helper` and has one row
        per requested date.  ``status='available'`` means a non-empty source
        file was obtained locally. After ``get_od_data()``, ``parse_status``
        distinguishes valid, genuinely empty, and invalid source files. Pass
        this table to ``build_temporal_network`` for coverage-aware averages.
        """
        if m_type not in self._acquisition_manifests:
            raise ValueError(
                "No acquisition manifest is available for %r. Run the "
                "corresponding data download first." % m_type
            )
        outcomes = getattr(self, "_od_processing_outcomes", {})
        if m_type in outcomes:
            filepaths, processed_success = outcomes.pop(m_type)
            self._finalize_od_manifest(
                m_type, filepaths, processed_success=processed_success
            )
        return self._acquisition_manifests[m_type].copy()

    def _remember_od_processing(
        self, m_type: str, filepaths, processed_success: bool
    ) -> None:
        """Defer expensive per-file validation until coverage is requested."""
        if m_type in self._acquisition_manifests:
            self._od_processing_outcomes[m_type] = (
                tuple(filepaths), processed_success
            )

    def _finalize_od_manifest(
        self, m_type: str, filepaths, *, processed_success: bool
    ) -> None:
        """Record whether each acquired OD file survived mandatory parsing.

        All mandatory fields are checked before optional analytical filtering.
        A partly invalid file is marked failed rather than presenting the
        surviving rows as a complete observed day.
        """
        if m_type not in self._acquisition_manifests or not filepaths:
            return
        manifest = self._acquisition_manifests[m_type]
        available = manifest["status"].eq("available")
        if not available.any():
            return
        try:
            source = self._scan_pipe_files_polars(filepaths, include_file_paths=True)
            mandatory = {"fecha", "periodo", "origen", "destino", "viajes", "viajes_km"}
            if not mandatory.issubset(source.collect_schema().names()):
                raise ValueError("OD source lacks mandatory columns")
            selected = source.select(
                pl.col("_source_path"),
                self._polars_date("fecha")
                .str.strptime(pl.Date, "%Y-%m-%d", strict=False)
                .alias("_date"),
                self._polars_identifier("origen").alias("_origin"),
                self._polars_identifier("destino").alias("_destination"),
                self._polars_numeric("viajes", strip_thousands=True).alias("_weight"),
                self._polars_numeric("viajes_km", strip_thousands=True).alias("_length"),
            )
            diagnostics = (
                selected.group_by("_source_path")
                .agg(
                    pl.len().alias("row_count"),
                    (
                        pl.col("_date").is_null()
                        | pl.col("_origin").is_null()
                        | pl.col("_origin").eq("")
                        | pl.col("_destination").is_null()
                        | pl.col("_destination").eq("")
                        | pl.col("_weight").is_null()
                        | ~pl.col("_weight").is_finite()
                        | (pl.col("_weight") < 0)
                        | pl.col("_length").is_null()
                        | ~pl.col("_length").is_finite()
                        | (pl.col("_length") < 0)
                    )
                    .sum()
                    .alias("invalid_rows"),
                    pl.col("_date").drop_nulls().unique().alias("dates"),
                )
                .collect(engine="streaming")
            )
            by_path = {
                os.path.abspath(row["_source_path"]): row
                for row in diagnostics.to_dicts()
            }
            for index in manifest.index[available]:
                path = manifest.at[index, "local_path"]
                row = by_path.get(os.path.abspath(path)) if path else None
                if row is None:
                    manifest.at[index, "parse_status"] = "empty"
                elif (
                    not processed_success
                    or row["invalid_rows"]
                    or row["dates"] != [pd.Timestamp(manifest.at[index, "date"]).date()]
                ):
                    manifest.at[index, "parse_status"] = "failed"
                else:
                    manifest.at[index, "parse_status"] = "valid"
        except Exception as exc:
            manifest.loc[available, "parse_status"] = "failed"
            print(f"[warn] OD source validation failed: {exc}")
        failed_dates = manifest.loc[
            available & manifest["parse_status"].eq("failed"), "date"
        ].tolist()
        if failed_dates:
            warnings.warn(
                "OD source parsing failed for these dates; they will not count "
                "as observed days: %s" % failed_dates[:5],
                RuntimeWarning,
                stacklevel=2,
            )

    def _set_acquisition_manifest(self, m_type: str, records) -> None:
        """Store one immutable-in-practice, date-level acquisition record."""
        self._acquisition_manifests[m_type] = pd.DataFrame(
            records,
            columns=["date", "mobility_type", "status", "coverage", "local_path", "error"],
        )
        self._acquisition_manifests[m_type]["parse_status"] = "not_processed"
        getattr(self, "_od_processing_outcomes", {}).pop(m_type, None)

    def _donwload_helper(self, m_type:str):
        local_list = []
        records = []
        if self.version == 2:
            for d in self.dates:
                d_first = d[:7]
                d_second = d.replace("-", "")
                if m_type == 'Personas':
                    download_url = f"https://movilidad-opendata.mitma.es/estudios_basicos/por-{self.zones}/{m_type.lower()}/ficheros-diarios/{d_first}/{d_second}_{m_type}_dia_{self.zones}.csv.gz"
                else:
                    download_url = f"https://movilidad-opendata.mitma.es/estudios_basicos/por-{self.zones}/{m_type.lower()}/ficheros-diarios/{d_first}/{d_second}_{m_type}_{self.zones}.csv.gz"

                print('Downloading file from', download_url)
                local_path = os.path.join(
                    self.output_path, f"{d_second}_{m_type}_{self.zones}_v{self.version}.csv.gz"
                )
                try:
                    utils.download_file_if_not_existing(download_url, local_path)
                    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                        local_list.append(local_path)
                        records.append(
                            [d, m_type, "available", "unverified", local_path, None]
                        )
                    else:
                        records.append([d, m_type, "empty", "unknown", local_path, None])
                except Exception as exc:
                    print(f"[warn] Failed to download {download_url}: {exc}")
                    records.append([d, m_type, "failed", "unknown", None, str(exc)])
                    continue
        elif self.version == 1:

            if self.zones == 'gaus':
                raise Exception('gaus is not a valid zone for version 1. Please use version 2 or use a different zone')

            for d in self.dates:
                d_first = d[:7]
                d_second = d.replace("-", "")
                local_path = os.path.join(
                    self.output_path, f"{d_second}_{m_type}_{self.zones}_v{self.version}.txt.gz"
                )
                try:
                    url_base = f"https://opendata-movilidad.mitma.es/{m_type}-mitma-{self.zones}/ficheros-diarios/{d_first}/{d_second}_{m_type[:-1]}_{m_type[-1]}_mitma_{self.zones[:-1]}.txt.gz"
                    utils.download_file_if_not_existing(url_base, local_path)
                    if os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                        local_list.append(local_path)
                        records.append(
                            [d, m_type, "available", "unverified", local_path, None]
                        )
                    else:
                        records.append([d, m_type, "empty", "unknown", local_path, None])
                except Exception as exc:
                    print(f"[warn] Failed to download {url_base}: {exc}")
                    records.append([d, m_type, "failed", "unknown", None, str(exc)])
                    continue
        self._set_acquisition_manifest(m_type, records)
        return local_list
