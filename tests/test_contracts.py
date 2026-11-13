import pandas as pd
import pytest

from freshretail import config, contracts

RAW_AVAILABLE = config.TRAIN_PATH.exists() and config.EVAL_PATH.exists()
requires_raw = pytest.mark.skipif(
    not RAW_AVAILABLE,
    reason=(
        "需要原始数据 data/raw/freshretailnet50k/{train,eval}.parquet；"
        "请按 data/README.md 下载并校验，或设置 FRESH_RETAIL_RAW_DIR"
    ),
)


@pytest.mark.requires_raw
@requires_raw
def test_file_metadata_matches_manifest():
    tr = contracts.check_file_metadata(config.TRAIN_PATH, config.EXPECTED_FILES["train.parquet"])
    ev = contracts.check_file_metadata(config.EVAL_PATH, config.EXPECTED_FILES["eval.parquet"])
    assert tr["rows"] == 4_500_000 and tr["columns"] == 19
    assert ev["rows"] == 350_000 and ev["columns"] == 19


@pytest.mark.requires_raw
@requires_raw
def test_schema_names_and_order():
    import pyarrow.parquet as pq
    schema = pq.ParquetFile(config.TRAIN_PATH).schema_arrow
    assert schema.names == config.COLUMNS


def test_train_eval_split_is_time_ordered():
    train = pd.to_datetime(["2024-03-28", "2024-06-25"])
    ev = pd.to_datetime(["2024-06-26", "2024-07-02"])
    info = contracts.check_split(train, ev)
    assert info["gap_days"] == 1
    assert info["overlap"] == 0


def test_split_overlap_raises():
    with pytest.raises(contracts.DataContractError):
        contracts.check_split(pd.to_datetime(["2024-06-01", "2024-06-25"]),
                              pd.to_datetime(["2024-06-25", "2024-06-30"]))
