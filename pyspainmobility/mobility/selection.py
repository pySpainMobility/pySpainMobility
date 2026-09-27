"""Lazy selection and additive aggregation of processed OD tables."""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path

import pandas as pd
import polars as pl


def select_od(data, *, filters=None, group_by=None) -> pl.LazyFrame:
    """Select processed OD rows, optionally summing flows by chosen columns.

    ``data`` may be a processed Parquet file, a pandas DataFrame, or a Polars
    DataFrame/LazyFrame. ``filters`` maps existing column names to exact values
    or collections of values (including ``None`` for
    missing categories). Both OD measures remain additive when ``group_by`` is
    provided. The result stays lazy; call ``collect()`` when needed.
    """
    if isinstance(data, pl.LazyFrame):
        frame = data
    elif isinstance(data, pl.DataFrame):
        frame = data.lazy()
    elif isinstance(data, pd.DataFrame):
        try:
            frame = pl.from_pandas(data, include_index=False).lazy()
        except ImportError:
            frame = pl.DataFrame(
                {
                    str(name): data[name]
                    .astype(object)
                    .where(data[name].notna(), None)
                    .tolist()
                    for name in data.columns
                }
            ).lazy()
    elif isinstance(data, (str, Path)):
        path = Path(data)
        if path.is_file() and path.suffix.lower() == ".parquet":
            frame = pl.scan_parquet(path)
        else:
            raise ValueError("OD paths must point to a Parquet file.")
    else:
        raise TypeError("data must be a Parquet path or a pandas/Polars frame.")

    columns = set(frame.collect_schema().names())
    measures = ("n_trips", "trips_total_length_km")
    missing_measures = set(measures) - columns
    if missing_measures:
        raise ValueError("OD measures are unavailable: %s" % sorted(missing_measures))
    if filters is not None:
        if not isinstance(filters, Mapping):
            raise TypeError("filters must map column names to values.")
        for name, values in filters.items():
            if name not in columns:
                raise ValueError("OD column %r is unavailable." % name)
            if isinstance(values, Mapping):
                raise TypeError("Filter values must be scalars or collections.")
            if isinstance(values, (str, bytes)) or not isinstance(values, Iterable):
                values = [values]
            else:
                values = list(values)
            non_null = [value for value in values if value is not None]
            condition = pl.col(name).is_in(non_null) if non_null else pl.lit(False)
            if any(value is None for value in values):
                condition = condition | pl.col(name).is_null()
            frame = frame.filter(condition)

    if group_by is not None:
        if isinstance(group_by, (str, bytes)) or not isinstance(group_by, Sequence):
            raise TypeError("group_by must be a sequence of column names.")
        if any(not isinstance(name, str) for name in group_by):
            raise TypeError("group_by must contain only column names.")
        if len(group_by) != len(set(group_by)):
            raise ValueError("group_by must not contain duplicates.")
        missing = set(group_by) - columns
        if missing:
            raise ValueError("OD columns are unavailable: %s" % sorted(missing))
        if set(group_by) & set(measures):
            raise ValueError("OD measures cannot be grouping columns.")
        totals = [pl.col(name).sum().alias(name) for name in measures]
        frame = (
            frame.group_by(list(group_by)).agg(totals)
            if group_by
            else frame.select(totals)
        )
    return frame


__all__ = ["select_od"]
