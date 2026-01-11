# -*- coding: utf-8 -*-
"""
visualization.py - データ可視化機能

Plotlyを使用した工数データの可視化
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
from pathlib import Path

# Load sort order configuration
_config_file = Path(__file__).parent.parent / 'group_order_config.json'
_SORT_ORDER = {}
if _config_file.exists():
    with open(_config_file, 'r', encoding='utf-8') as f:
        _SORT_ORDER = json.load(f)


def sort_with_config(values, field_name):
    """
    Sort values based on configuration order.

    Args:
        values: List of values to sort
        field_name: Field name (e.g., 'USER_FIELD_01')

    Returns:
        Sorted list following config order, then alphabetically for unspecified values
    """
    if field_name not in _SORT_ORDER:
        return sorted(values)

    order = _SORT_ORDER[field_name]
    ordered = [v for v in order if v in values]
    remaining = [v for v in values if v not in ordered]
    return ordered + sorted(remaining)


# Mapping from display names to actual column names
GROUPING_DISPLAY_TO_COLUMN = {
    '個人別': '従業員名',
    'UNIT別': 'UNIT',
    '作業内容別': 'USER_FIELD_03'
}

# Field label mapping for legends
FIELD_LABELS = {
    'USER_FIELD_01': '作業大分類',
    'USER_FIELD_02': '作業中分類',
    'USER_FIELD_03': '作業小分類',
    '従業員名': '個人',
    'UNIT': 'UNIT'
}


def map_grouping_to_column(grouping_display_name):
    """
    Map grouping display name to actual dataframe column name.

    Args:
        grouping_display_name: Display name like '個人別', 'UNIT別', '作業内容別', or '業務内容X'

    Returns:
        Actual column name in dataframe
    """
    return GROUPING_DISPLAY_TO_COLUMN.get(grouping_display_name, grouping_display_name)


def get_available_business_content_columns(df):
    """
    業務内容1〜10のうち、データが存在するカラムのリストを返す

    重要: この関数は業務内容1から順番にチェックし、
    最初に空のカラムが見つかった時点でそれ以降のカラムは含めない
    （例: 業務内容3が空の場合、業務内容4以降もチェックしない）

    Args:
        df: データフレーム

    Returns:
        データが存在する業務内容カラムのリスト (例: ['業務内容1', '業務内容2'])
        空のカラムが見つかった時点でその前までのカラムのみ返す
    """
    business_cols = []
    for i in range(1, 11):
        col_name = f'業務内容{i}'
        if col_name in df.columns:
            # カラムにデータが存在するかチェック（空でない値が1つでもあればOK）
            # None値を除外してから空文字チェック
            non_null = df[col_name].notna()
            if non_null.any() and df[col_name][non_null].ne('').any():
                business_cols.append(col_name)
            else:
                # 空のカラムが見つかったら、それ以降は追加しない
                break
    return business_cols


def filter_data_by_period(df, start_year_month, end_year_month):
    """
    期間フィルター: 指定された年月の範囲でデータを絞り込む

    Args:
        df: データフレーム
        start_year_month: 開始年月のタプル (year, month)
        end_year_month: 終了年月のタプル (year, month)

    Returns:
        フィルター済みデータフレーム
    """
    if start_year_month is None or end_year_month is None:
        return df

    start_year, start_month = start_year_month
    end_year, end_month = end_year_month

    # 年月を比較用の整数に変換 (例: 2024年1月 → 202401)
    df_copy = df.copy()
    df_copy['年月'] = df_copy['年'] * 100 + df_copy['月']
    start_ym = start_year * 100 + start_month
    end_ym = end_year * 100 + end_month

    filtered = df_copy[(df_copy['年月'] >= start_ym) & (df_copy['年月'] <= end_ym)]
    filtered = filtered.drop('年月', axis=1)

    return filtered


def filter_data_by_hierarchy(df, level1_value, level2_value):
    """
    Filter data by hierarchical classification levels.
    Local filter - works independently of any prior global filtering.

    Args:
        df: Full dataframe
        level1_value: USER_FIELD_01 value or 'すべて'
        level2_value: USER_FIELD_02 value or 'すべて'

    Returns:
        (filtered_df, x_field, group_field_for_work_content)
    """
    filtered = df.copy()

    if level1_value != 'すべて':
        filtered = filtered[filtered['USER_FIELD_01'] == level1_value]
        x_field = 'USER_FIELD_02'
        if level2_value != 'すべて':
            filtered = filtered[filtered['USER_FIELD_02'] == level2_value]
            group_field = 'USER_FIELD_03'
        else:
            group_field = 'USER_FIELD_03'
    else:
        x_field = 'USER_FIELD_01'  # Always use FIELD_01 when level1 is すべて
        if level2_value != 'すべて':
            filtered = filtered[filtered['USER_FIELD_02'] == level2_value]
            group_field = 'USER_FIELD_03'
        else:
            group_field = 'USER_FIELD_02'

    return filtered, x_field, group_field


def create_work_content_chart(df, group_by, x_field, group_field_for_work_content, range_label=None, both_filters_selected=False):
    """
    作業内容の棒グラフを作成（スタック棒グラフまたはグループ棒グラフ）

    Args:
        df: フィルター済みデータフレーム
        group_by: グルーピング方法 ('作業内容別', '個人別', '業務内容1', '業務内容2', ..., 'UNIT別')
        x_field: X軸に使用するフィールド名
        group_field_for_work_content: "作業内容別"選択時のグルーピングフィールド
        range_label: 期間ラベル（オプション）
        both_filters_selected: True if both 作業大分類 and 作業中分類 are not すべて

    Returns:
        Plotly図オブジェクト
    """
    # X軸ラベルの日本語化
    FIELD_LABELS = {
        'USER_FIELD_01': '作業大分類',
        'USER_FIELD_02': '作業中分類',
        'USER_FIELD_03': '作業小分類'
    }

    # グルーピングフィールドの決定 - Use mapping function
    if group_by == 'すべて' or group_by == '作業内容別':
        # Use group_field_for_work_content to avoid conflicts with x_field
        group_field = group_field_for_work_content
    elif group_by.startswith('業務内容'):
        # 業務内容1, 業務内容2, ... のいずれか
        group_field = group_by
    else:
        # Map display name to actual column name (個人別 → 従業員名, UNIT別 → UNIT)
        group_field = map_grouping_to_column(group_by)

    # When both filters are selected and grouping is not 作業内容別, use grouped bar chart
    if both_filters_selected and group_by != '作業内容別':
        # Grouped bar chart logic - use group_field (mapped column name)
        aggregated = df.groupby([x_field, group_field])['作業時間(h)'].sum().reset_index()

        # X軸の値を取得してソート（設定順）
        x_unique = aggregated[x_field].unique().tolist()
        x_values = sort_with_config(x_unique, x_field)

        # グループ値をソート（設定順）
        group_unique = aggregated[group_field].dropna().unique().tolist()
        group_values = sort_with_config(group_unique, group_field)

        # Sort aggregated data by the categorical order before plotting
        # Make a copy to avoid modifying the original
        aggregated = aggregated.copy()
        aggregated[x_field] = pd.Categorical(aggregated[x_field], categories=x_values, ordered=True)
        aggregated[group_field] = pd.Categorical(aggregated[group_field], categories=group_values, ordered=True)
        aggregated = aggregated.sort_values([x_field, group_field])

        # タイトル作成
        title = f"{FIELD_LABELS.get(x_field, x_field)}別 作業時間"
        if range_label:
            title += f"（{range_label}）"

        # Plotly Expressでグループ棒グラフを作成
        fig = px.bar(
            aggregated,
            x=x_field,
            y='作業時間(h)',
            color=group_field,
            barmode='group',  # Grouped, not stacked
            title=title,
            labels={x_field: FIELD_LABELS.get(x_field, x_field)}
        )
    else:
        # Stacked bar chart logic (existing)
        aggregated = df.groupby([x_field, group_field])['作業時間(h)'].sum().reset_index()

        # X軸の値を取得してソート（設定順）
        x_unique = aggregated[x_field].unique().tolist()
        x_values = sort_with_config(x_unique, x_field)

        # グループ値をソート（設定順）
        group_unique = aggregated[group_field].dropna().unique().tolist()
        group_values = sort_with_config(group_unique, group_field)

        # Sort aggregated data by the categorical order before plotting
        # Make a copy to avoid modifying the original
        aggregated = aggregated.copy()
        aggregated[x_field] = pd.Categorical(aggregated[x_field], categories=x_values, ordered=True)
        aggregated[group_field] = pd.Categorical(aggregated[group_field], categories=group_values, ordered=True)
        aggregated = aggregated.sort_values([x_field, group_field])

        # タイトル作成
        title = f"{FIELD_LABELS.get(x_field, x_field)}別 作業時間"
        if range_label:
            title += f"（{range_label}）"

        # Plotly Expressでスタック棒グラフを作成
        fig = px.bar(
            aggregated,
            x=x_field,
            y='作業時間(h)',
            color=group_field,
            barmode='stack',
            title=title,
            labels={x_field: FIELD_LABELS.get(x_field, x_field)}
        )

    # Update hover template for all cases
    x_label = FIELD_LABELS.get(x_field, x_field)
    group_label = FIELD_LABELS.get(group_field, group_field)

    fig.update_traces(
        hovertemplate=(
            f"{x_label}：%{{x}}<br>"
            f"{group_label}：%{{fullData.name}}<br>"
            "作業時間(h)：%{y:.1f}<extra></extra>"
        )
    )

    # Update legend title
    fig.update_layout(
        height=500,
        legend_title_text=group_label
    )
    return fig


def create_time_series_chart(df, grouping_method, range_label=None):
    """
    Create time series line chart.

    Args:
        df: Filtered dataframe
        grouping_method: 'すべて', '作業内容別', '個人別', '業務内容X', or 'UNIT別'
        range_label: Optional period label for title

    Returns:
        Plotly figure
    """
    # Determine grouping field
    if grouping_method == 'すべて':
        # Line chart by USER_FIELD_02
        group_field = 'USER_FIELD_02'
    elif grouping_method == '作業内容別':
        # Line chart by USER_FIELD_03
        group_field = 'USER_FIELD_03'
    else:
        # Other grouping methods (個人別, UNIT別, 業務内容X)
        # Map display name to actual column name
        group_field = map_grouping_to_column(grouping_method)

    # Aggregate by year-month and group field
    groupby_fields = ['年', '月', group_field]
    agg_data = (
        df.groupby(groupby_fields)['作業時間(h)']
        .sum()
        .reset_index()
    )

    # Create year-month label in yyyy-mm format
    agg_data['年月'] = agg_data['年'].astype(str) + '-' + agg_data['月'].astype(str).str.zfill(2)

    # Sort groups by config
    group_unique = agg_data[group_field].dropna().unique().tolist()
    group_values = sort_with_config(group_unique, group_field)

    # Convert to categorical to control order and sort data
    # Make a copy to avoid modifying the original
    agg_data = agg_data.copy()
    agg_data[group_field] = pd.Categorical(agg_data[group_field], categories=group_values, ordered=True)
    agg_data = agg_data.sort_values(['年月', group_field])

    # Create line chart
    fig = px.line(
        agg_data,
        x='年月',
        y='作業時間(h)',
        color=group_field,
        markers=True,
        title=f"時間推移 ({range_label})" if range_label else "時間推移",
        custom_data=[group_field]
    )

    # Update hover template
    group_label = FIELD_LABELS.get(group_field, group_field)
    fig.update_traces(
        hovertemplate=(
            "年月：%{x}<br>"
            f"{group_label}：%{{customdata[0]}}<br>"
            "作業時間(h)：%{y:.1f}<extra></extra>"
        )
    )

    # Always show all months including start month
    unique_months = sorted(agg_data['年月'].unique())
    fig.update_xaxes(
        tickmode='array',
        tickvals=unique_months,
        ticktext=unique_months,
        tickangle=-45,
        title='年月'
    )

    # Update legend title
    fig.update_layout(
        height=500,
        legend_title_text=FIELD_LABELS.get(group_field, group_field)
    )
    return fig


def create_person_chart(df, selected_person, grouping_method, range_label=None):
    """Create person-specific time series chart."""
    # Filter for selected person
    person_data = df[df['従業員名'] == selected_person].copy()

    # Map display name to actual column name
    if grouping_method == 'すべて':
        actual_column = 'USER_FIELD_02'
    elif grouping_method == '作業内容別':
        actual_column = 'USER_FIELD_03'
    else:
        actual_column = map_grouping_to_column(grouping_method)

    # Aggregate
    agg_data = (
        person_data.groupby(['年', '月', actual_column])['作業時間(h)']
        .sum()
        .reset_index()
    )

    # Create year-month label in yyyy-mm format
    agg_data['年月'] = agg_data['年'].astype(str) + '-' + agg_data['月'].astype(str).str.zfill(2)

    # Sort groups
    group_unique = agg_data[actual_column].dropna().unique().tolist()
    group_values = sort_with_config(group_unique, actual_column)

    # Convert to categorical to control order and sort data
    # Make a copy to avoid modifying the original
    agg_data = agg_data.copy()
    agg_data[actual_column] = pd.Categorical(agg_data[actual_column], categories=group_values, ordered=True)
    agg_data = agg_data.sort_values(['年月', actual_column])

    # Create stacked bar chart
    fig = px.bar(
        agg_data,
        x='年月',
        y='作業時間(h)',
        color=actual_column,
        barmode='stack',
        title=f"{selected_person} の作業時間推移 ({range_label})" if range_label else f"{selected_person} の作業時間推移",
        custom_data=[actual_column]
    )

    # Update hover template with タイトル：値 format
    group_label = FIELD_LABELS.get(actual_column, actual_column)
    fig.update_traces(
        hovertemplate=(
            "年月：%{x}<br>"
            f"{group_label}：%{{customdata[0]}}<br>"
            "作業時間(h)：%{y:.1f}<extra></extra>"
        )
    )

    # Always show all months
    unique_months = sorted(agg_data['年月'].unique())
    fig.update_xaxes(
        tickmode='array',
        tickvals=unique_months,
        ticktext=unique_months,
        tickangle=-45,
        title='年月'
    )

    # Update legend title
    fig.update_layout(
        height=500,
        legend_title_text=group_label
    )
    return fig


def create_unit_chart(df, selected_unit, grouping_method, range_label=None):
    """Create UNIT-specific time series chart."""
    # Filter for selected unit
    unit_data = df[df['UNIT'] == selected_unit].copy()

    # Map display name to actual column name
    if grouping_method == 'すべて':
        actual_column = 'USER_FIELD_02'
    elif grouping_method == '作業内容別':
        actual_column = 'USER_FIELD_03'
    else:
        actual_column = map_grouping_to_column(grouping_method)

    # Aggregate
    agg_data = (
        unit_data.groupby(['年', '月', actual_column])['作業時間(h)']
        .sum()
        .reset_index()
    )

    # Create year-month label in yyyy-mm format
    agg_data['年月'] = agg_data['年'].astype(str) + '-' + agg_data['月'].astype(str).str.zfill(2)

    # Sort groups
    group_unique = agg_data[actual_column].dropna().unique().tolist()
    group_values = sort_with_config(group_unique, actual_column)

    # Convert to categorical to control order and sort data
    # Make a copy to avoid modifying the original
    agg_data = agg_data.copy()
    agg_data[actual_column] = pd.Categorical(agg_data[actual_column], categories=group_values, ordered=True)
    agg_data = agg_data.sort_values(['年月', actual_column])

    # Create stacked bar chart
    fig = px.bar(
        agg_data,
        x='年月',
        y='作業時間(h)',
        color=actual_column,
        barmode='stack',
        title=f"{selected_unit} の作業時間推移 ({range_label})" if range_label else f"{selected_unit} の作業時間推移",
        custom_data=[actual_column]
    )

    # Update hover template with タイトル：値 format
    group_label = FIELD_LABELS.get(actual_column, actual_column)
    fig.update_traces(
        hovertemplate=(
            "年月：%{x}<br>"
            f"{group_label}：%{{customdata[0]}}<br>"
            "作業時間(h)：%{y:.1f}<extra></extra>"
        )
    )

    # Always show all months
    unique_months = sorted(agg_data['年月'].unique())
    fig.update_xaxes(
        tickmode='array',
        tickvals=unique_months,
        ticktext=unique_months,
        tickangle=-45,
        title='年月'
    )

    # Update legend title
    fig.update_layout(
        height=500,
        legend_title_text=group_label
    )
    return fig


def create_unified_chart(df, x_field, group_field, x_axis_label, grouping_label, range_label=None):
    """
    Create a unified chart based on x_field and group_field selection.

    Chart type logic:
    - If x_field == '年月': Line chart
    - If x_field == group_field: Bar chart (ungrouped)
    - If x_field != group_field: Stacked bar chart

    Args:
        df: Filtered dataframe
        x_field: Actual column name for x-axis
        group_field: Actual column name for grouping
        x_axis_label: Display label for x-axis
        grouping_label: Display label for grouping
        range_label: Optional period label for title

    Returns:
        Plotly figure
    """
    # Aggregate data
    # When x_field == group_field, only group by one field to avoid duplicate columns
    if x_field == group_field:
        agg_data = (
            df.groupby([x_field])['作業時間(h)']
            .sum()
            .reset_index()
        )
    else:
        agg_data = (
            df.groupby([x_field, group_field])['作業時間(h)']
            .sum()
            .reset_index()
        )

    # Sort x-axis values
    if x_field == '年月':
        # For time series, sort chronologically
        x_values = sorted(agg_data[x_field].unique().tolist())
    else:
        # For other fields, use config order
        x_values = sort_with_config(agg_data[x_field].dropna().unique().tolist(), x_field)

    # Sort grouping values (only if different from x_field)
    if x_field != group_field:
        group_values = sort_with_config(agg_data[group_field].dropna().unique().tolist(), group_field)

    # Convert to categorical for proper ordering
    agg_data = agg_data.copy()
    agg_data[x_field] = pd.Categorical(agg_data[x_field], categories=x_values, ordered=True)

    if x_field != group_field:
        agg_data[group_field] = pd.Categorical(agg_data[group_field], categories=group_values, ordered=True)
        agg_data = agg_data.sort_values([x_field, group_field])
    else:
        agg_data = agg_data.sort_values([x_field])

    # Create title
    title = f"工数分析"
    if range_label:
        title += f" ({range_label})"

    # Determine chart type and create figure
    if x_field == '年月':
        # Line chart for time series
        fig = px.line(
            agg_data,
            x=x_field,
            y='作業時間(h)',
            color=group_field,
            markers=True,
            title=title,
            custom_data=[group_field]
        )

        # Update hover template with comma formatting
        fig.update_traces(
            hovertemplate=(
                f"{x_axis_label}：%{{x}}<br>"
                f"{grouping_label}：%{{customdata[0]}}<br>"
                "作業時間(h)：%{y:,.1f}<extra></extra>"
            )
        )

        # Update x-axis with forced ordering
        fig.update_xaxes(
            categoryorder='array',
            categoryarray=x_values,
            tickmode='array',
            tickvals=x_values,
            ticktext=x_values,
            tickangle=-45,
            title=x_axis_label
        )

    elif x_field == group_field:
        # Bar chart (ungrouped) when same field
        fig = px.bar(
            agg_data,
            x=x_field,
            y='作業時間(h)',
            title=title
        )

        # Update hover template with comma formatting
        fig.update_traces(
            hovertemplate=(
                f"{x_axis_label}：%{{x}}<br>"
                "作業時間(h)：%{y:,.1f}<extra></extra>"
            )
        )

        # Force x-axis ordering
        fig.update_xaxes(
            categoryorder='array',
            categoryarray=x_values,
            title=x_axis_label
        )

    else:
        # Stacked bar chart when different fields
        fig = px.bar(
            agg_data,
            x=x_field,
            y='作業時間(h)',
            color=group_field,
            barmode='stack',
            title=title,
            custom_data=[group_field]
        )

        # Update hover template with comma formatting
        fig.update_traces(
            hovertemplate=(
                f"{x_axis_label}：%{{x}}<br>"
                f"{grouping_label}：%{{customdata[0]}}<br>"
                "作業時間(h)：%{y:,.1f}<extra></extra>"
            )
        )

        # Force x-axis ordering
        fig.update_xaxes(
            categoryorder='array',
            categoryarray=x_values,
            title=x_axis_label
        )

    # Common layout settings
    fig.update_layout(
        height=500,
        yaxis_title='作業時間(h)',
        yaxis=dict(tickformat=',')
    )

    # Add legend title if grouped
    if x_field != group_field:
        fig.update_layout(legend_title_text=grouping_label)

    return fig
