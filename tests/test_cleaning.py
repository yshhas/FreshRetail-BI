import pandas as pd

from freshretail import cleaning, config


def _frame():
    return pd.DataFrame({
        "sale_amount": [0.0, 1.0, 2.5],
        "discount": [0.0, 1.0, 0.8],
        "holiday_flag": [0, 1, 0],
        "stock_hour6_22_cnt": [0, 8, 16],
    })


def test_original_columns_are_not_modified():
    df = _frame()
    out = cleaning.clean_frame(df)
    assert out["discount"].tolist() == [0.0, 1.0, 0.8]
    assert out["sale_amount"].tolist() == [0.0, 1.0, 2.5]
    assert df["discount"].tolist() == [0.0, 1.0, 0.8]


def test_derived_flags():
    out = cleaning.clean_frame(_frame())
    assert out["sales_index"].tolist() == [0.0, 1.0, 2.5]
    assert out["discount_missing"].tolist() == [True, False, False]
    assert out["discount_out_of_range"].tolist() == [False, False, False]
    assert out["discount_valid"].tolist() == [False, True, True]
    assert out["promo_flag"].tolist() == [False, False, True]
    assert out["holiday_proxy"].tolist() == [0, 1, 0]
    assert out["stockout_hours_6_22"].tolist() == [0, 8, 16]
    assert out["stockout_day_flag"].tolist() == [False, True, True]
    assert out["stockout_rate_6_22"].tolist() == [0.0, 0.5, 1.0]
    assert out["sales_zero_flag"].tolist() == [True, False, False]


def test_discount_out_of_range():
    df = pd.DataFrame({"sale_amount": [1.0], "discount": [1.088],
                       "holiday_flag": [0], "stock_hour6_22_cnt": [0]})
    out = cleaning.clean_frame(df)
    assert bool(out.loc[0, "discount_out_of_range"]) is True
    assert bool(out.loc[0, "discount_valid"]) is False
    assert bool(out.loc[0, "promo_flag"]) is False


def test_rule_payload_has_traceability():
    payload = cleaning.rules_payload()
    assert payload["rule_version"] == config.RULE_VERSION
    ids = [r["id"] for r in payload["rules"]]
    assert len(ids) == len(set(ids))
    for r in payload["rules"]:
        assert r["field"] and r["action"] and r["note"]
