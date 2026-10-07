"""グラフ種別（utils/visualization.py create_unified_chart）のテスト。"""
import pandas as pd
import pytest

from utils.visualization import (
    CHART_LINE, CHART_STACKED_BAR, CHART_STACKED_LINE, CHART_TYPES,
    create_unified_chart, default_chart_type,
)


@pytest.fixture
def df():
    # (2026-02, 設計) は存在しない → 積算折れ線では0補完が必要
    return pd.DataFrame({
        '年月': ['2026-01', '2026-01', '2026-02'],
        'USER_FIELD_01': ['標準作業', '設計', '標準作業'],
        '従業員名': ['A', 'B', 'A'],
        '作業時間(h)': [10.0, 5.0, 8.0],
    })


# (x_field, group_field): 4つの軸パターン
AXES = {
    'x=年月,x!=g': ('年月', 'USER_FIELD_01'),
    'x=年月,x=g': ('年月', '年月'),
    'x!=年月,x!=g': ('USER_FIELD_01', '従業員名'),
    'x!=年月,x=g': ('USER_FIELD_01', 'USER_FIELD_01'),
}
EXPECTED_TRACE = {CHART_LINE: 'scatter', CHART_STACKED_LINE: 'scatter', CHART_STACKED_BAR: 'bar'}


@pytest.mark.parametrize('chart_type', CHART_TYPES)
@pytest.mark.parametrize('axes', list(AXES))
def test_all_chart_types_build_for_all_axis_patterns(df, chart_type, axes):
    """3種別 × 4つの軸パターンの全てで図が作れ、トレース種別と総工数が保たれる。"""
    x, g = AXES[axes]
    fig = create_unified_chart(df, x, g, x, g, chart_type=chart_type)
    assert all(t.type == EXPECTED_TRACE[chart_type] for t in fig.data)
    assert sum(sum(t.y) for t in fig.data) == pytest.approx(23.0)


def test_default_chart_type_follows_x_axis():
    """X軸=年月は折れ線、それ以外は積算棒グラフ。"""
    assert default_chart_type('年月') == CHART_LINE
    assert default_chart_type('USER_FIELD_01') == CHART_STACKED_BAR


@pytest.mark.parametrize('axes', ['x=年月,x!=g', 'x!=年月,x!=g', 'x!=年月,x=g'])
def test_none_chart_type_matches_previous_auto_behaviour(df, axes):
    """chart_type 省略時は従来の自動判定（年月=折れ線、他=棒）と同じ種類になる。"""
    x, g = AXES[axes]
    fig = create_unified_chart(df, x, g, x, g)
    assert fig.data[0].type == ('scatter' if x == '年月' else 'bar')


def test_stacked_line_fills_missing_cells_with_zero(df):
    """積算折れ線: 欠損の(年月,分類)組を0で補完し、全系列が全X値を持つ。"""
    fig = create_unified_chart(df, '年月', 'USER_FIELD_01', '年月', '作業大分類',
                               chart_type=CHART_STACKED_LINE)
    for t in fig.data:
        assert len(t.x) == 2
    design = next(t for t in fig.data if t.name == '設計')
    assert list(design.y) == [5.0, 0.0]


def test_line_does_not_fill_missing_cells(df):
    """折れ線: 従来どおり欠損は補完しない。"""
    fig = create_unified_chart(df, '年月', 'USER_FIELD_01', '年月', '作業大分類',
                               chart_type=CHART_LINE)
    design = next(t for t in fig.data if t.name == '設計')
    assert len(design.x) == 1


def test_unknown_chart_type_raises(df):
    with pytest.raises(ValueError):
        create_unified_chart(df, '年月', '年月', '年月', '年月', chart_type='円グラフ')
