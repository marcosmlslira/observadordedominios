import pytest
from unittest.mock import MagicMock, patch

from ingestion.orchestrator.pipeline import _load_tld_from_r2
from ingestion.loader.delta_loader import load_delta

def test_pipeline_r2_contract_violation_marker_without_parquets():
    # Setup R2 with a marker but NO parquet files
    # The list_prefix will return no keys for the parquet, so we need to mock layout.delta_key
    mock_storage = MagicMock()
    mock_storage.list_prefix.return_value = []
    
    # We must mock `_find_latest_marker_date` to return `2024-01-01`
    with patch("ingestion.orchestrator.pipeline._find_latest_marker_date", return_value="2024-01-01"):
        # We also mock _list_parquet_keys from loader directly if pipeline imports it
        with patch("ingestion.loader.delta_loader._list_parquet_keys", return_value=[]):
            result = _load_tld_from_r2(
                source="openintel",
                tld="test",
                today_str="2024-01-01",
                cfg=MagicMock(),
                storage=mock_storage,
                layout=MagicMock(),
                check_marker=True
            )
            
            assert result.status == "error"
            assert "R2 marker present" in result.error
            assert "databricks_contract_violation" in result.error


@patch("ingestion.loader.delta_loader.psycopg2.connect")
@patch("ingestion.loader.delta_loader._list_parquet_keys")
@patch("ingestion.loader.delta_loader._parallel_load_shards")
def test_load_delta_partial_load_recovery(mock_load_shards, mock_list_keys, mock_connect):
    # Simulate DB where added succeeds, but removed fails
    
    mock_list_keys.side_effect = [
        ["added.parquet"], # added
        ["removed.parquet"]  # removed
    ]

    # First call (added) succeeds returning 100 rows
    # Second call (removed) fails
    # Third call (removed sanitised retry) fails
    mock_load_shards.side_effect = [
        100,
        Exception("Simulated load error on removed"),
        Exception("Simulated retry error")
    ]

    result = load_delta(
        database_url="postgresql://dummy",
        storage=MagicMock(),
        settings=MagicMock(),
        layout=MagicMock(),
        source="openintel",
        tld="test",
        snapshot_date="2024-01-01"
    )
    
    assert result["status"] == "partial"
    assert result["added_loaded"] == 100
    assert result["removed_loaded"] == 0
