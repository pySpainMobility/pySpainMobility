import os

import pytest

from pyspainmobility import Mobility


RUN_LIVE = os.getenv("PYSPAINMOBILITY_RUN_LIVE_TESTS") == "1"


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="Live MITMA pipeline tests are disabled by default. Set PYSPAINMOBILITY_RUN_LIVE_TESTS=1 to run.",
)
def test_live_od_pipeline_sevilla_jerez_sum_not_inflated(tmp_path):
    out_dir = tmp_path / "live_pipeline"
    mobility = Mobility(
        version=2,
        zones="municipalities",
        start_date="2024-01-01",
        end_date="2024-01-01",
        output_directory=str(out_dir),
        backend="pandas",
    )

    df = mobility.get_od_data(return_df=True)
    assert df is not None
    assert not df.empty
    assert {"date", "hour", "id_origin", "id_destination", "n_trips", "trips_total_length_km"}.issubset(df.columns)

    sevilla = "41091"
    jerez = "11020"
    sev_to_jerez = float(
        df.loc[(df["id_origin"] == sevilla) & (df["id_destination"] == jerez), "n_trips"].sum()
    )

    # Historical MITMA data for this route/day should be around ~1.3k, not ~1.3M.
    assert sev_to_jerez > 500
    assert sev_to_jerez < 5000


@pytest.mark.skipif(
    not RUN_LIVE,
    reason="Live MITMA pipeline tests are disabled by default. Set PYSPAINMOBILITY_RUN_LIVE_TESTS=1 to run.",
)
def test_live_number_of_trips_pipeline_smoke(tmp_path):
    out_dir = tmp_path / "live_pipeline_nt"
    mobility = Mobility(
        version=2,
        zones="municipalities",
        start_date="2024-01-01",
        end_date="2024-01-01",
        output_directory=str(out_dir),
        backend="pandas",
    )

    df = mobility.get_number_of_trips_data(return_df=True)
    assert df is not None
    assert not df.empty
    assert {"date", "overnight_stay_area", "age", "gender", "number_of_trips", "people"}.issubset(df.columns)
    assert df["people"].dropna().ge(0).all()
