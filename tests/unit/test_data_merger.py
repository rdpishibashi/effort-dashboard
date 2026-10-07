"""月次データ統合の年月単位上書き（utils/data_merger.py）のテスト。"""
import pandas as pd
import pytest

from utils.data_merger import merge_effort_data, summarize_year_month_overlap


def _df(rows):
    """rows: [(年, 月, 従業員名, 作業時間(h), 区分)]"""
    return pd.DataFrame(rows, columns=['年', '月', '従業員名', '作業時間(h)', '区分'])


def _ym_counts(df):
    return {(int(y), int(m)): n for (y, m), n in df.groupby(['年', '月']).size().items()}


@pytest.fixture
def existing():
    return _df([
        (2026, 7, 'A', 1.0, 'old'), (2026, 7, 'B', 1.0, 'old'),
        (2026, 8, 'A', 1.0, 'old'), (2026, 8, 'B', 1.0, 'old'), (2026, 8, 'C', 1.0, 'old'),
    ])


@pytest.fixture
def monthly():
    # 2026-08 は重複、2026-09 は新規
    return _df([
        (2026, 8, 'A', 2.0, 'new'),
        (2026, 9, 'A', 2.0, 'new'), (2026, 9, 'B', 2.0, 'new'),
    ])


def test_overlap_summary_counts_only_overlapping_year_months(existing, monthly):
    """重複年月だけが、既存件数・上書き件数つきで年月昇順に返る。"""
    s = summarize_year_month_overlap(existing, monthly)
    assert s.to_dict('records') == [
        {'年': 2026, '月': 8, '既存データ件数': 3, '上書きするデータ件数': 1}
    ]


def test_overlap_summary_empty_without_existing(monthly):
    """既存データなし・重複なしのときは空（表を出さない）。"""
    assert summarize_year_month_overlap(None, monthly).empty
    no_overlap = _df([(2025, 1, 'A', 1.0, 'old')])
    assert summarize_year_month_overlap(no_overlap, monthly).empty


def test_merge_without_existing_creates_new(monthly):
    """既存なし: 月次データがそのまま新規作成される。"""
    out = merge_effort_data(None, monthly)
    assert len(out) == 3 and set(out['区分']) == {'new'}


def test_merge_no_overlap_adds_all():
    """重複なし: 既存は全て残り、月次は全件追加される。"""
    ex = _df([(2026, 7, 'A', 1.0, 'old')])
    mo = _df([(2026, 9, 'A', 2.0, 'new')])
    out = merge_effort_data(ex, mo)
    assert _ym_counts(out) == {(2026, 7): 1, (2026, 9): 1}


def test_merge_overwrite_replaces_whole_year_month(existing, monthly):
    """上書きON（skipなし）: 重複年月は既存3件が消え、月次1件に置き換わる（行単位ではなく年月単位）。"""
    out = merge_effort_data(existing, monthly)
    assert _ym_counts(out) == {(2026, 7): 2, (2026, 8): 1, (2026, 9): 2}
    assert set(out[out['月'] == 8]['区分']) == {'new'}
    assert set(out[out['月'] == 7]['区分']) == {'old'}


def test_merge_skip_keeps_existing_and_drops_new_for_that_month(existing, monthly):
    """上書きOFF: 重複年月は既存を維持し月次分は取り込まない。重複しない9月は追加される。"""
    out = merge_effort_data(existing, monthly, skip_year_months={(2026, 8)})
    assert _ym_counts(out) == {(2026, 7): 2, (2026, 8): 3, (2026, 9): 2}
    assert set(out[out['月'] == 8]['区分']) == {'old'}


def test_merge_mixed_choices_per_year_month():
    """混在: 年月ごとに上書き/維持が分かれる。"""
    ex = _df([(2026, 7, 'A', 1.0, 'old'), (2026, 8, 'A', 1.0, 'old'), (2026, 8, 'B', 1.0, 'old')])
    mo = _df([(2026, 7, 'A', 2.0, 'new'), (2026, 7, 'B', 2.0, 'new'), (2026, 8, 'A', 2.0, 'new')])
    out = merge_effort_data(ex, mo, skip_year_months={(2026, 8)})
    assert _ym_counts(out) == {(2026, 7): 2, (2026, 8): 2}
    assert set(out[out['月'] == 7]['区分']) == {'new'}
    assert set(out[out['月'] == 8]['区分']) == {'old'}


def test_merge_all_skipped_returns_existing_only(existing):
    """月次の全年月がOFF: エラーにならず既存データのみが返る。"""
    mo = _df([(2026, 8, 'A', 2.0, 'new')])
    out = merge_effort_data(existing, mo, skip_year_months={(2026, 8)})
    assert len(out) == len(existing) and set(out['区分']) == {'old'}


def test_merge_cleans_invalid_existing_rows():
    """既存データの作業時間<=0・年月欠損行は結果に残らない（従来のクリーニング維持）。"""
    ex = _df([(2026, 7, 'A', 1.0, 'old'), (2026, 7, 'B', 0.0, 'old'), (None, 7, 'C', 1.0, 'old')])
    mo = _df([(2026, 9, 'A', 2.0, 'new')])
    out = merge_effort_data(ex, mo)
    assert len(out) == 2


def test_merge_accepts_dataframe_or_bytesio(existing, monthly):
    """既存データは DataFrame でも BytesIO でも同じ結果になる。"""
    import io
    buf = io.BytesIO()
    existing.to_excel(buf, index=False)
    buf.seek(0)
    a = merge_effort_data(existing, monthly)
    b = merge_effort_data(buf, monthly)
    assert _ym_counts(a) == _ym_counts(b)
