"""仕様: 月次データ統合の重複年月は「年月まるごと」上書き/維持を選べる（2026-10-07 確定）。"""
import pandas as pd

from utils.data_merger import merge_effort_data, summarize_year_month_overlap


def _df(rows):
    return pd.DataFrame(rows, columns=['年', '月', '従業員名', '作業時間(h)', 'UNIT'])


def test_overwrite_is_year_month_wide_not_row_level():
    """Given 既存8月に月次8月と「キーが一致しない行」がある
    When 上書きON（既定）でマージ
    Then 一致しない既存8月行も含め、既存8月は全て消え月次8月だけが残る
    （旧仕様の行単位上書きでは既存の別人行が残っていた。年月置換への回帰を防ぐ）"""
    ex = _df([(2026, 8, 'A', 1.0, 'u1'), (2026, 8, 'Z', 1.0, 'u9')])
    mo = _df([(2026, 8, 'A', 2.0, 'u1')])
    out = merge_effort_data(ex, mo)
    assert list(out['従業員名']) == ['A'] and list(out['作業時間(h)']) == [2.0]


def test_overwrite_off_keeps_existing_and_overlap_counts_shown():
    """Given 重複8月（既存2件・月次1件）
    When 8月の上書きをOFF
    Then 件数表は既存2/上書き1を示し、結果の8月は既存2件のまま、非重複の9月は追加される"""
    ex = _df([(2026, 8, 'A', 1.0, 'u'), (2026, 8, 'Z', 1.0, 'u')])
    mo = _df([(2026, 8, 'A', 2.0, 'u'), (2026, 9, 'A', 2.0, 'u')])
    s = summarize_year_month_overlap(ex, mo)
    assert s.to_dict('records') == [{'年': 2026, '月': 8, '既存データ件数': 2, '上書きするデータ件数': 1}]
    out = merge_effort_data(ex, mo, skip_year_months={(2026, 8)})
    assert out.groupby('月').size().to_dict() == {8: 2, 9: 1}
    assert set(out[out['月'] == 8]['作業時間(h)']) == {1.0}
