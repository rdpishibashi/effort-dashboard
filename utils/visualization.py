# -*- coding: utf-8 -*-
"""
visualization.py - データ可視化機能

Plotly Express を使用した工数データの可視化
"""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_config_file = Path(__file__).parent.parent / 'group_order_config.json'
_SORT_ORDER: dict = {}
if _config_file.exists():
    with open(_config_file, 'r', encoding='utf-8') as _f:
        _SORT_ORDER = json.load(_f)

# Maps DataFrame column names to Japanese display labels (used in legends/axes)
FIELD_LABELS: dict[str, str] = {
    'USER_FIELD_01': '作業大分類',
    'USER_FIELD_02': '作業中分類',
    'USER_FIELD_03': '作業小分類',
    '従業員名':       '個人',
    'UNIT':          'UNIT',
    '年月':           '年月',
}

# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def sort_with_config(values: list, field_name: str) -> list:
    """
    Sort values using the configured order for field_name.

    Values listed in group_order_config.json appear first in that order;
    remaining values are appended in alphabetical order.
    """
    if field_name not in _SORT_ORDER:
        return sorted(values)
    order = _SORT_ORDER[field_name]
    ordered = [v for v in order if v in values]
    remaining = sorted(v for v in values if v not in ordered)
    return ordered + remaining


def get_available_business_content_columns(df: pd.DataFrame) -> list[str]:
    """
    Return 業務内容 columns (業務内容1–10) that contain at least one non-empty value.

    Stops at the first empty column so that sparse higher-numbered columns
    are not included (e.g. if 業務内容3 is empty, 業務内容4–10 are skipped).
    """
    cols = []
    for i in range(1, 11):
        col = f'業務内容{i}'
        if col not in df.columns:
            break
        non_null = df[col].notna()
        if non_null.any() and df[col][non_null].ne('').any():
            cols.append(col)
        else:
            break
    return cols


def filter_data_by_period(
    df: pd.DataFrame,
    start_year_month: tuple[int, int],
    end_year_month: tuple[int, int],
) -> pd.DataFrame:
    """Filter rows to the inclusive [start_year_month, end_year_month] range."""
    if start_year_month is None or end_year_month is None:
        return df
    start_ym = start_year_month[0] * 100 + start_year_month[1]
    end_ym   = end_year_month[0]   * 100 + end_year_month[1]
    tmp = df.copy()
    tmp['_ym'] = tmp['年'] * 100 + tmp['月']
    return tmp[(tmp['_ym'] >= start_ym) & (tmp['_ym'] <= end_ym)].drop(columns='_ym')


# ---------------------------------------------------------------------------
# Chart data table
# ---------------------------------------------------------------------------

def create_chart_data_table(
    df: pd.DataFrame,
    x_field: str,
    group_field: str,
    x_axis_label: str,
    grouping_label: str,
) -> pd.DataFrame:
    """
    Return a formatted pivot DataFrame mirroring the chart data.

    Rows = x_field values, columns = group_field values (or a single
    '作業時間[h]' column when x_field == group_field).
    All values are formatted as strings with one decimal place.
    """
    if x_field == group_field:
        agg = df.groupby([x_field])['作業時間(h)'].sum().reset_index()
        x_values = (
            sorted(agg[x_field].unique().tolist())
            if x_field == '年月'
            else sort_with_config(agg[x_field].dropna().unique().tolist(), x_field)
        )
        agg[x_field] = pd.Categorical(agg[x_field], categories=x_values, ordered=True)
        agg = agg.sort_values(x_field).set_index(x_field)
        agg.index.name = x_axis_label
        agg.columns = ['作業時間[h]']
        return agg.map(lambda v: f"{v:.1f}")

    agg = df.groupby([x_field, group_field])['作業時間(h)'].sum().reset_index()
    x_values = (
        sorted(agg[x_field].unique().tolist())
        if x_field == '年月'
        else sort_with_config(agg[x_field].dropna().unique().tolist(), x_field)
    )
    group_values = sort_with_config(agg[group_field].dropna().unique().tolist(), group_field)

    pivot = (
        agg.pivot(index=x_field, columns=group_field, values='作業時間(h)')
        .reindex(index=x_values, columns=group_values)
        .fillna(0.0)
        .map(lambda v: f"{v:.1f}")
    )
    pivot.index.name = x_axis_label
    pivot.columns.name = '作業時間[h]'
    return pivot


# ---------------------------------------------------------------------------
# Unified chart
# ---------------------------------------------------------------------------

CHART_LINE = '折れ線グラフ'
CHART_STACKED_LINE = '積算折れ線グラフ'
CHART_STACKED_BAR = '積算棒グラフ'
CHART_TYPES = [CHART_LINE, CHART_STACKED_LINE, CHART_STACKED_BAR]


def default_chart_type(x_field: str) -> str:
    """X軸が年月なら折れ線グラフ、それ以外は積算棒グラフ。"""
    return CHART_LINE if x_field == '年月' else CHART_STACKED_BAR


def create_unified_chart(
    df: pd.DataFrame,
    x_field: str,
    group_field: str,
    x_axis_label: str,
    grouping_label: str,
    range_label: str | None = None,
    chart_type: str | None = None,
) -> 'plotly.graph_objs.Figure':
    """
    Create a Plotly chart for x_field / group_field.

    chart_type (None → default_chart_type(x_field)):
    - 折れ線グラフ   : line chart (markers); single line when x_field == group_field
    - 積算折れ線グラフ: stacked area; missing (x, group) cells are filled with 0
    - 積算棒グラフ   : stacked bar; plain bar when x_field == group_field
    """
    if chart_type is None:
        chart_type = default_chart_type(x_field)
    if chart_type not in CHART_TYPES:
        raise ValueError(f"unknown chart_type: {chart_type}")

    title = f"工数分析 ({range_label})" if range_label else "工数分析"
    ungrouped = x_field == group_field

    # --- Aggregate ---------------------------------------------------------
    if ungrouped:
        agg = df.groupby([x_field])['作業時間(h)'].sum().reset_index()
    else:
        agg = df.groupby([x_field, group_field])['作業時間(h)'].sum().reset_index()

    # --- Sort orders -------------------------------------------------------
    x_values = (
        sorted(agg[x_field].unique().tolist())
        if x_field == '年月'
        else sort_with_config(agg[x_field].dropna().unique().tolist(), x_field)
    )
    group_values = (
        x_values if ungrouped
        else sort_with_config(agg[group_field].dropna().unique().tolist(), group_field)
    )

    # Stacked area needs every (x, group) cell, otherwise stacks are drawn wrongly
    if chart_type == CHART_STACKED_LINE and not ungrouped:
        full = pd.MultiIndex.from_product([x_values, group_values], names=[x_field, group_field])
        agg = (
            agg.set_index([x_field, group_field])['作業時間(h)']
            .reindex(full, fill_value=0.0)
            .reset_index()
        )

    # Apply categorical ordering for correct sort in Plotly
    agg = agg.copy()
    agg[x_field] = pd.Categorical(agg[x_field], categories=x_values, ordered=True)
    if not ungrouped:
        agg[group_field] = pd.Categorical(agg[group_field], categories=group_values, ordered=True)
        agg = agg.sort_values([x_field, group_field])
    else:
        agg = agg.sort_values(x_field)

    # --- Build figure ------------------------------------------------------
    common = dict(x=x_field, y='作業時間(h)', title=title)
    grouped_kwargs = dict(
        color=group_field,
        custom_data=[group_field],
        category_orders={x_field: x_values, group_field: group_values},
    )

    if chart_type == CHART_LINE:
        fig = px.line(agg, markers=True, **common, **(grouped_kwargs if not ungrouped else {}))
    elif chart_type == CHART_STACKED_LINE:
        fig = px.area(agg, **common, **(grouped_kwargs if not ungrouped else {}))
    else:
        fig = px.bar(
            agg, **common,
            **(dict(barmode='stack', **grouped_kwargs) if not ungrouped else {}),
        )

    if ungrouped:
        hover = f"{x_axis_label}：%{{x}}<br>作業時間(h)：%{{y:,.1f}}<extra></extra>"
    else:
        hover = (
            f"{x_axis_label}：%{{x}}<br>"
            f"{grouping_label}：%{{customdata[0]}}<br>"
            "作業時間(h)：%{y:,.1f}<extra></extra>"
        )
    fig.update_traces(hovertemplate=hover)

    fig.update_xaxes(categoryorder='array', categoryarray=x_values, title=x_axis_label)
    if x_field == '年月':
        fig.update_xaxes(tickmode='array', tickvals=x_values, ticktext=x_values, tickangle=-45)

    fig.update_layout(
        height=500,
        yaxis_title='作業時間(h)',
        yaxis=dict(tickformat=','),
    )
    if not ungrouped:
        fig.update_layout(legend_title_text=grouping_label)

    return fig
