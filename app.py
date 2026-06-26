# -*- coding: utf-8 -*-
"""
Effort-Dashboard - 工数データマージ・分析ツール

複数の月次工数データをマージし、様々な視点から分析・可視化する
"""

import io
import os
import traceback
from datetime import datetime

import pandas as pd
import streamlit as st

from utils.data_merger import process_multiple_monthly_files
from utils.visualization import (
    create_chart_data_table,
    create_unified_chart,
    filter_data_by_period,
    get_available_business_content_columns,
    sort_with_config,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps UI display names to DataFrame column names
FIELD_MAPPING: dict[str, str] = {
    '年月':      '年月',
    '作業大分類': 'USER_FIELD_01',
    '作業中分類': 'USER_FIELD_02',
    '作業小分類': 'USER_FIELD_03',
    '指番':      '指番',
    '総合効率':   'USER_FIELD_05',
    '個人':      '従業員名',
}

USER_FIELDS = [
    'USER_FIELD_01', 'USER_FIELD_02', 'USER_FIELD_03',
    'USER_FIELD_04', 'USER_FIELD_05',
]

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def render_sidebar_overview(placeholder) -> None:
    """Render application instructions in the sidebar."""
    placeholder.empty()
    with placeholder.container():
        with st.expander("ℹ️ 使い方ガイド", expanded=False):
            st.markdown(
                "**＜データ登録＞**\n"
                "工数データを登録（アップロード）します。２つの登録方法があります。\n"
                "\n"
                "- 総工数ファイルをアップロード：月次工数データを１つにまとめた総工数ファイルを登録する\n"
                "- 月次データを統合：新たな月次工数データを追加して総工数ファイルを更新し登録する\n"
            )
            st.markdown(
                "**＜工数分析グラフ＞**\n"
                "総工数ファイルのデータを使って様々な分析グラフを作成します。\n"
                "\n"
                "- フィルター設定（左側のウィンドウ）：分析対象データを絞り込む\n"
                "- X軸：X軸に採用するデータ種別を選択する\n"
                "- グルーピング方法：グラフの凡例（系列）を選択する\n"
            )


def render_data_status() -> None:
    """Show the current dataset status in the sidebar."""
    merged_df = st.session_state.get('merged_data')
    st.sidebar.subheader("データの状態")
    if merged_df is not None:
        st.sidebar.markdown(f"総データ件数：**{len(merged_df):,}**")
        st.sidebar.markdown(f"総作業時間：**{merged_df['作業時間(h)'].sum():.1f} h**")
        st.sidebar.caption("現在登録されている総工数ファイルの概要です。")
    else:
        st.sidebar.info("総工数ファイルがまだ登録されていません。")


def preprocess_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """Coerce types, drop invalid rows, and fill USER_FIELD NaNs with '未入力'."""
    df = raw_df.copy()
    df['年'] = pd.to_numeric(df['年'], errors='coerce').astype('Int64')
    df['月'] = pd.to_numeric(df['月'], errors='coerce').astype('Int64')
    df['作業時間(h)'] = pd.to_numeric(df['作業時間(h)'], errors='coerce')
    df = df[(df['年'].notna()) & (df['月'].notna()) & (df['作業時間(h)'] > 0)]
    for field in USER_FIELDS:
        if field in df.columns:
            df[field] = df[field].fillna('未入力')
    if 'WBS要素(代入)' in df.columns or 'UNIT' in df.columns:
        wbs = df['WBS要素(代入)'] if 'WBS要素(代入)' in df.columns else pd.Series('', index=df.index)
        unit = df['UNIT'] if 'UNIT' in df.columns else pd.Series('', index=df.index)
        wbs_blank = wbs.isna() | (wbs.astype(str).str.strip() == '')
        unit_blank = unit.isna() | (unit.astype(str).str.strip() == '')
        # WBS要素(代入)とUNITの両方が空白でない場合はWBS要素(代入)を採用する
        df['指番'] = wbs.where(~wbs_blank, unit.where(~unit_blank))
    return df


def make_stats_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """Return a 年月 × USER_FIELD_01 pivot table of work hours."""
    tmp = df.copy()
    tmp['USER_FIELD_01'] = tmp['USER_FIELD_01'].fillna('未入力')
    tmp['作業時間(h)'] = pd.to_numeric(tmp['作業時間(h)'], errors='coerce').fillna(0)
    tmp = tmp[tmp['作業時間(h)'] > 0]
    tmp['年月'] = tmp['年'].astype(str) + '-' + tmp['月'].astype(str).str.zfill(2)
    pivot = (
        tmp.groupby(['年月', 'USER_FIELD_01'])['作業時間(h)']
        .sum()
        .reset_index()
        .pivot(index='年月', columns='USER_FIELD_01', values='作業時間(h)')
        .fillna(0)
    )
    col_order = sort_with_config(pivot.columns.tolist(), 'USER_FIELD_01')
    pivot = pivot[col_order].map(lambda x: f"{x:.1f}")
    pivot.columns.name = '作業時間[h]'
    pivot.index.name = '年月'
    return pivot


# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="工数ダッシュボード",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("工数分析ダッシュボード")
st.write("月次工数データを統合して多角的な工数分析を行います")

# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------

if 'merged_data' not in st.session_state:
    st.session_state.merged_data = None
if 'merged_excel_bytes' not in st.session_state:
    st.session_state.merged_excel_bytes = None
if 'merged_excel_filename' not in st.session_state:
    st.session_state.merged_excel_filename = None
if 'grouping' not in st.session_state:
    st.session_state['grouping'] = '作業大分類'

# Auto-load default file (first run only)
if 'default_loaded' not in st.session_state:
    st.session_state.default_loaded = False

if not st.session_state.default_loaded and st.session_state.merged_data is None:
    _default_path = os.path.join(os.path.dirname(__file__), 'merged_efforts.xlsx')
    if os.path.exists(_default_path):
        try:
            _default_df = pd.read_excel(_default_path)
            st.session_state.merged_data = _default_df
            st.toast(f"✅ merged_efforts.xlsx を読み込みました ({len(_default_df):,}行)")
        except Exception as _e:
            st.warning(f"デフォルトファイルの読み込みに失敗しました: {_e}")
    st.session_state.default_loaded = True

sidebar_overview_placeholder = st.sidebar.empty()
render_sidebar_overview(sidebar_overview_placeholder)

st.divider()

tab_data_entry, tab_analysis = st.tabs(["データ登録", "工数分析グラフ"])

# ---------------------------------------------------------------------------
# Tab: データ登録
# ---------------------------------------------------------------------------

with tab_data_entry:
    st.header("データ登録")

    upload_mode = st.radio(
        "登録方法を選択してください",
        ['総工数ファイルをアップロード', '月次データを統合'],
        horizontal=True,
        key='upload_mode_selector',
    )

    if upload_mode == '総工数ファイルをアップロード':
        st.subheader("既存の総工数データファイルをアップロード")
        analysis_file = st.file_uploader(
            "総工数データファイルをアップロード",
            type=['xlsx'],
            key="analysis_upload",
        )
        if analysis_file:
            try:
                analysis_df = pd.read_excel(analysis_file)
                # YubiNippo形式（作業日あり・年月なし）の場合は自動変換
                if '年' not in analysis_df.columns and '作業日' in analysis_df.columns:
                    analysis_df['作業日'] = pd.to_datetime(analysis_df['作業日'], errors='coerce')
                    analysis_df['年'] = analysis_df['作業日'].dt.year
                    analysis_df['月'] = analysis_df['作業日'].dt.month
                    st.info("'作業日' 列から '年'・'月' 列を自動生成しました。")
                st.session_state.merged_data = analysis_df
                st.success(f"✅ ファイル読み込み完了: {len(analysis_df):,}行")
            except Exception as e:
                st.error(f"ファイル読み込みエラー: {e}")

    else:  # 月次データを統合
        st.subheader("月次工数データの統合")

        with st.expander("📁 ファイルアップロード", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("既存の総工数データファイル")
                existing_file = st.file_uploader(
                    "総工数データファイルをアップロード（新規作成時は不要）",
                    type=['xlsx'],
                    key="existing",
                )
                if existing_file:
                    st.success(f"✅ {existing_file.name}")
                    try:
                        existing_df = pd.read_excel(existing_file)
                        st.write(f"行数: {len(existing_df):,}")
                        ym_stats = existing_df.groupby(['年', '月']).size().reset_index(name='件数')
                        st.dataframe(ym_stats, height=200)
                    except Exception as e:
                        st.error(f"ファイル読み込みエラー: {e}")

            with col2:
                st.subheader("月次工数記録データファイル")
                monthly_files = st.file_uploader(
                    "月次工数データファイルをアップロード（複数選択可）",
                    type=['xlsx'],
                    accept_multiple_files=True,
                    key="monthly",
                )
                if monthly_files:
                    st.success(f"✅ {len(monthly_files)}ファイル選択済み")
                    for i, f in enumerate(monthly_files, 1):
                        st.write(f"{i}. {f.name}")

        st.divider()

        if monthly_files:
            if st.button("データマージ・業務内容分割を実行", type="primary"):
                try:
                    progress_bar = st.progress(0.0)
                    status_text = st.empty()

                    def update_progress(progress, status):
                        progress_bar.progress(float(max(0.0, min(1.0, progress))))
                        status_text.text(status)

                    if existing_file:
                        existing_file.seek(0)
                    for f in monthly_files:
                        f.seek(0)

                    final_data = process_multiple_monthly_files(
                        monthly_files, existing_file, progress_callback=update_progress
                    )

                    if final_data is not None:
                        st.session_state.merged_data = final_data

                        buf = io.BytesIO()
                        final_data.to_excel(buf, index=False, engine='xlsxwriter')
                        buf.seek(0)
                        st.session_state.merged_excel_bytes = buf.getvalue()
                        st.session_state.merged_excel_filename = (
                            f"merged_efforts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                        )

                        st.success("✅ マージ・業務内容分割が完了しました！")
                        st.subheader("📊 統計情報")
                        st.dataframe(make_stats_pivot(final_data), width='stretch')
                    else:
                        st.error("❌ 処理に失敗しました")

                except Exception as e:
                    st.error(f"処理エラー: {e}")
                    st.text(traceback.format_exc())
        else:
            st.info("月次工数データファイルを選択してください")

        if st.session_state.merged_excel_bytes is not None:
            st.divider()
            st.subheader("ファイル保存")
            st.download_button(
                label="総工数データファイルをダウンロード",
                data=st.session_state.merged_excel_bytes,
                file_name=st.session_state.merged_excel_filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width='stretch',
            )
            st.caption(
                "ダウンロードしたファイルを merged_efforts.xlsx にリネームしてアプリフォルダに置くと、"
                "次回起動時に自動読み込みされます。"
            )

# ---------------------------------------------------------------------------
# Tab: 工数分析グラフ
# ---------------------------------------------------------------------------

with tab_analysis:
    if st.session_state.merged_data is None:
        st.info(
            "データを登録してください。「データ登録」タブで総工数ファイルをアップロードするか、"
            "月次データを統合してください。"
        )
    else:
        st.header("工数データの分析")

        df = preprocess_df(st.session_state.merged_data)

        # --- Sidebar: global filters ----------------------------------------
        st.sidebar.markdown("---")
        st.sidebar.header("🔍 フィルター設定")

        available_year_months = sorted(df[['年', '月']].drop_duplicates().values.tolist())
        if available_year_months:
            ym_labels = [f"{int(y)}-{int(m):02d}" for y, m in available_year_months]
            ym_dts = pd.to_datetime(ym_labels, format='%Y-%m')
            default_end_idx = len(ym_dts) - 1
            default_start_idx = max(0, default_end_idx - 5)

            start_dt, end_dt = st.sidebar.slider(
                "期間",
                min_value=ym_dts[0].to_pydatetime(),
                max_value=ym_dts[-1].to_pydatetime(),
                value=(
                    ym_dts[default_start_idx].to_pydatetime(),
                    ym_dts[default_end_idx].to_pydatetime(),
                ),
                format="YYYY-MM",
                key="period_slider",
            )
            start_year, start_month = start_dt.year, start_dt.month
            end_year, end_month = end_dt.year, end_dt.month
            df_filtered = filter_data_by_period(
                df, (start_year, start_month), (end_year, end_month)
            )
            period_label = f"{start_year}-{start_month:02d} 〜 {end_year}-{end_month:02d}"
        else:
            df_filtered = df
            period_label = None
            st.sidebar.warning("データに年月情報がありません")

        # Cascading classification filters
        field1_opts = ['すべて'] + sort_with_config(
            df_filtered['USER_FIELD_01'].dropna().unique().tolist(), 'USER_FIELD_01'
        )

        def _reset_field2():
            st.session_state['global_field2'] = []

        global_field1 = st.sidebar.selectbox(
            "作業大分類", field1_opts, key="global_field1", on_change=_reset_field2
        )

        field2_base = (
            df_filtered[df_filtered['USER_FIELD_01'] == global_field1]
            if global_field1 != 'すべて' else df_filtered
        )
        field2_opts = sort_with_config(
            field2_base['USER_FIELD_02'].dropna().unique().tolist(), 'USER_FIELD_02'
        )
        global_field2_mode = st.sidebar.radio(
            "作業中分類フィルター方式", ["含む", "除外"], key="global_field2_mode", horizontal=True
        )
        global_field2 = st.sidebar.multiselect("作業中分類", field2_opts, key="global_field2")

        person_opts = sorted(df_filtered['従業員名'].dropna().unique().tolist())
        global_person_mode = st.sidebar.radio(
            "個人フィルター方式", ["含む", "除外"], key="global_person_mode", horizontal=True
        )
        global_person = st.sidebar.multiselect("個人", person_opts, key="global_person")

        sashiban_opts = sorted(df_filtered['指番'].dropna().unique().tolist())
        global_sashiban_mode = st.sidebar.radio(
            "指番フィルター方式", ["含む", "除外"], key="global_sashiban_mode", horizontal=True
        )
        global_sashiban = st.sidebar.multiselect("指番", sashiban_opts, key="global_sashiban")

        # Apply filters
        if global_field1 != 'すべて':
            df_filtered = df_filtered[df_filtered['USER_FIELD_01'] == global_field1]
        if global_field2:
            if global_field2_mode == "含む":
                df_filtered = df_filtered[df_filtered['USER_FIELD_02'].isin(global_field2)]
            else:
                df_filtered = df_filtered[~df_filtered['USER_FIELD_02'].isin(global_field2)]
        if global_person:
            if global_person_mode == "含む":
                df_filtered = df_filtered[df_filtered['従業員名'].isin(global_person)]
            else:
                df_filtered = df_filtered[~df_filtered['従業員名'].isin(global_person)]
        if global_sashiban:
            if global_sashiban_mode == "含む":
                df_filtered = df_filtered[df_filtered['指番'].isin(global_sashiban)]
            else:
                df_filtered = df_filtered[~df_filtered['指番'].isin(global_sashiban)]

        st.sidebar.info(f"フィルター後: {len(df_filtered):,}件 / {len(df):,}件")
        render_data_status()

        # --- Chart controls -------------------------------------------------
        available_business_cols = get_available_business_content_columns(df_filtered)
        sashiban_option = ['指番'] if '指番' in df_filtered.columns else []
        axis_choices = (
            ['年月', '作業大分類', '作業中分類', '作業小分類']
            + sashiban_option
            + ['総合効率', '個人']
            + available_business_cols
        )

        col1, col2 = st.columns(2)
        with col1:
            x_axis = st.selectbox("X軸", axis_choices, key="x_axis")
        with col2:
            grouping = st.selectbox("グルーピング方法", axis_choices, key="grouping")

        if len(df_filtered) > 0:
            x_field = FIELD_MAPPING.get(x_axis, x_axis)
            group_field = FIELD_MAPPING.get(grouping, grouping)

            # Ensure 年月 column exists when used as axis or grouping
            if '年月' in (x_field, group_field) and '年月' not in df_filtered.columns:
                df_filtered = df_filtered.copy()
                df_filtered['年月'] = (
                    df_filtered['年'].astype(str)
                    + '-'
                    + df_filtered['月'].astype(str).str.zfill(2)
                )

            fig = create_unified_chart(
                df_filtered,
                x_field=x_field,
                group_field=group_field,
                x_axis_label=x_axis,
                grouping_label=grouping,
                range_label=period_label,
            )
            st.plotly_chart(fig, width='stretch', config=None)

            with st.expander("データテーブル：作業時間[h]", expanded=False):
                st.dataframe(
                    create_chart_data_table(df_filtered, x_field, group_field, x_axis, grouping),
                    width='stretch',
                )
        else:
            st.warning("フィルター条件に一致するデータがありません")
