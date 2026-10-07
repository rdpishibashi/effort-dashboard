# tests/regression

## spec（仕様確認）
| 受入条件 | テスト |
|---|---|
| 重複年月は年月単位で置換される（行単位ではない） | `spec/test_overwrite_spec.py::test_overwrite_is_year_month_wide_not_row_level` |
| 上書きOFFの年月は既存を維持し、件数表は既存/上書き件数を示す | `spec/test_overwrite_spec.py::test_overwrite_off_keeps_existing_and_overlap_counts_shown` |

## bugfix（不具合再発防止）
なし
