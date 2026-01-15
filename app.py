# -*- coding: utf-8 -*-
"""
Effort-Dashboard - 工数データマージ・分析ツール

複数の月次工数データをマージし、様々な視点から分析・可視化する
"""

import streamlit as st
import pandas as pd
import io
import os
from datetime import datetime
from utils.data_merger import process_multiple_monthly_files
from utils.visualization import (
    filter_data_by_period,
    get_available_business_content_columns,
    sort_with_config,
    create_chart_data_table
)

st.set_page_config(
    page_title="工数ダッシュボード",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("工数分析ダッシュボード")
st.write("月次工数データを統合して多角的な工数分析を行います")

# セッション状態の初期化
if 'merged_data' not in st.session_state:
    st.session_state.merged_data = None

if 'active_tab' not in st.session_state:
    st.session_state.active_tab = 0

# デフォルトファイルの自動読み込み（初回のみ）
if 'default_loaded' not in st.session_state:
    st.session_state.default_loaded = False

if not st.session_state.default_loaded and st.session_state.merged_data is None:
    default_file_path = os.path.join(os.path.dirname(__file__), 'merged_efforts.xlsx')
    if os.path.exists(default_file_path):
        try:
            default_df = pd.read_excel(default_file_path)
            st.session_state.merged_data = default_df
            st.session_state.default_loaded = True
            st.info(f"デフォルトファイル 'merged_efforts.xlsx' を読み込みました ({len(default_df):,}行)")
        except Exception as e:
            st.warning(f"デフォルトファイルの読み込みに失敗しました: {e}")
            st.session_state.default_loaded = True
    else:
        st.session_state.default_loaded = True


# ========================================
# タブレイアウト（セッション状態で管理）
# ========================================
# タブ選択UI
tab_options = ["データ登録", "工数分析グラフ"]
selected_tab = st.radio(
    "表示切替",
    tab_options,
    index=st.session_state.active_tab,
    horizontal=True,
    key="tab_selector"
)

# Update session state based on selection
st.session_state.active_tab = tab_options.index(selected_tab)

st.divider()

if selected_tab == "データ登録":
    st.header("データ登録")

    # 操作モード選択（タブ内）
    upload_mode = st.radio(
        "登録方法を選択してください",
        ['既存ファイルをアップロード', '月次データを統合'],
        index=0,
        horizontal=True,
        key='upload_mode_selector'
    )

    if upload_mode == '既存ファイルをアップロード':
        # ========================================
        # モード1: 既存ファイル分析
        # ========================================
        st.subheader("既存の総工数データファイルをアップロード")

        analysis_file = st.file_uploader(
            "総工数データファイルをアップロード（または merged_efforts.xlsx がデフォルト）",
            type=['xlsx'],
            key="analysis_upload"
        )

        if analysis_file:
            try:
                analysis_df = pd.read_excel(analysis_file)
                st.session_state.merged_data = analysis_df
                st.success(f"✅ ファイル読み込み完了: {len(analysis_df):,}行")
            except Exception as e:
                st.error(f"ファイル読み込みエラー: {e}")

    else:
        # ========================================
        # モード2: 月次データ統合
        # ========================================
        st.subheader("月次工数データの統合")

        with st.expander("📁 ファイルアップロード", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("既存の総工数データファイル")
                existing_file = st.file_uploader(
                    "総工数データファイルをアップロード（新規作成時は不要）",
                    type=['xlsx'],
                    key="existing"
                )

                if existing_file:
                    st.success(f"✅ {existing_file.name}")
                    try:
                        existing_df = pd.read_excel(existing_file)
                        st.write(f"行数: {len(existing_df):,}")

                        # 年月範囲表示
                        year_month_stats = existing_df.groupby(['年', '月']).size().reset_index(name='件数')
                        st.dataframe(year_month_stats, height=200)
                    except Exception as e:
                        st.error(f"ファイル読み込みエラー: {e}")

            with col2:
                st.subheader("月次工数記録データファイル")
                monthly_files = st.file_uploader(
                    "月次工数データファイルをアップロード（複数選択可）",
                    type=['xlsx'],
                    accept_multiple_files=True,
                    key="monthly"
                )

                if monthly_files:
                    st.success(f"✅ {len(monthly_files)}ファイル選択済み")
                    for i, file in enumerate(monthly_files, 1):
                        st.write(f"{i}. {file.name}")

        # マージ処理実行
        st.divider()

        if monthly_files:
            if st.button("🔄 データマージ・業務内容分割を実行", type="primary"):
                try:
                    progress_bar = st.progress(0.0)
                    status_text = st.empty()

                    def update_progress(progress, status):
                        progress = float(max(0.0, min(1.0, progress)))
                        progress_bar.progress(progress)
                        status_text.text(status)

                    # ファイルポインタをリセット
                    if existing_file:
                        existing_file.seek(0)
                    for file in monthly_files:
                        file.seek(0)

                    # マージ処理実行
                    final_data = process_multiple_monthly_files(
                        monthly_files,
                        existing_file,
                        progress_callback=update_progress
                    )

                    if final_data is not None:
                        st.session_state.merged_data = final_data

                        st.success("✅ マージ・業務内容分割が完了しました！")

                        # 統計情報
                        st.subheader("📊 統計情報")
                        stats = final_data.groupby(['年', '月']).agg({
                            '従業員名': 'nunique',
                            '作業時間(h)': 'sum'
                        }).reset_index()
                        stats.columns = ['年', '月', 'ユニーク従業員数', '総作業時間(h)']
                        st.dataframe(stats)

                        # ダウンロードボタン
                        output_buffer = io.BytesIO()
                        final_data.to_excel(output_buffer, index=False, engine='xlsxwriter')
                        output_buffer.seek(0)

                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"merged_efforts_{timestamp}.xlsx"

                        st.download_button(
                            label="📥 総工数データファイルをダウンロード",
                            data=output_buffer,
                            file_name=filename,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    else:
                        st.error("❌ 処理に失敗しました")

                except Exception as e:
                    st.error(f"処理エラー: {e}")
                    import traceback
                    st.text(traceback.format_exc())
        else:
            st.info("月次工数データファイルを選択してください")


elif selected_tab == "工数分析グラフ":
    # ========================================
    # 工数データの分析機能
    # ========================================
    if st.session_state.merged_data is None:
        st.info("データを登録してください。「データ登録」タブで既存ファイルをアップロードするか、月次データを統合してください。")
    else:
        st.header("工数データの分析")

        df = st.session_state.merged_data

        # データの前処理
        df['年'] = pd.to_numeric(df['年'], errors='coerce').astype('Int64')
        df['月'] = pd.to_numeric(df['月'], errors='coerce').astype('Int64')
        df['作業時間(h)'] = pd.to_numeric(df['作業時間(h)'], errors='coerce')

        # 無効データ除外
        df = df[
            (df['年'].notna()) &
            (df['月'].notna()) &
            (df['作業時間(h)'] > 0)
        ]

        # ========================================
        # サイドバー: グローバルフィルター
        # ========================================
        st.sidebar.header("🔍 フィルター設定")

        # 期間フィルター（スライダー形式）
        available_year_months = sorted(df[['年', '月']].drop_duplicates().values.tolist())
        if available_year_months:
            year_month_labels = [f"{int(y)}-{int(m):02d}" for y, m in available_year_months]
            year_month_datetimes = pd.to_datetime(year_month_labels, format='%Y-%m')
    
            default_end_idx = len(year_month_datetimes) - 1
            default_start_idx = max(0, default_end_idx - 5)  # Last 6 months
    
            start_dt, end_dt = st.sidebar.slider(
                "期間",
                min_value=year_month_datetimes[0].to_pydatetime(),
                max_value=year_month_datetimes[-1].to_pydatetime(),
                value=(
                    year_month_datetimes[default_start_idx].to_pydatetime(),
                    year_month_datetimes[default_end_idx].to_pydatetime()
                ),
                format="YYYY-MM",
                key="period_slider"
            )
    
            start_year, start_month = start_dt.year, start_dt.month
            end_year, end_month = end_dt.year, end_dt.month
    
            df_filtered = filter_data_by_period(
                df,
                (start_year, start_month),
                (end_year, end_month)
            )
        else:
            df_filtered = df
            st.sidebar.warning("データに年月情報がありません")

        # グローバル 作業大分類フィルター
        global_field1_options = ['すべて'] + sort_with_config(
            df_filtered['USER_FIELD_01'].dropna().unique().tolist(),
            'USER_FIELD_01'
        )
        global_field1_value = st.sidebar.selectbox(
            "作業大分類",
            global_field1_options,
            key="global_field1"
        )

        # グローバル 作業中分類フィルター（cascading）
        if global_field1_value != 'すべて':
            global_field2_options_filtered = df_filtered[
                df_filtered['USER_FIELD_01'] == global_field1_value
            ]['USER_FIELD_02'].dropna().unique().tolist()
        else:
            global_field2_options_filtered = df_filtered['USER_FIELD_02'].dropna().unique().tolist()

        global_field2_options = ['すべて'] + sort_with_config(
            global_field2_options_filtered,
            'USER_FIELD_02'
        )
        global_field2_value = st.sidebar.selectbox(
            "作業中分類",
            global_field2_options,
            key="global_field2"
        )

        # グローバル 個人フィルター
        global_person_options = ['すべて'] + sorted(df_filtered['従業員名'].dropna().unique().tolist())
        global_person_value = st.sidebar.selectbox(
            "個人",
            global_person_options,
            key="global_person"
        )

        # グローバル UNITフィルター
        global_unit_options = ['すべて'] + sorted(df_filtered['UNIT'].dropna().unique().tolist())
        global_unit_value = st.sidebar.selectbox(
            "UNIT",
            global_unit_options,
            key="global_unit"
        )

        # グローバルフィルター適用
        if global_field1_value != 'すべて':
            df_filtered = df_filtered[df_filtered['USER_FIELD_01'] == global_field1_value]
        if global_field2_value != 'すべて':
            df_filtered = df_filtered[df_filtered['USER_FIELD_02'] == global_field2_value]
        if global_person_value != 'すべて':
            df_filtered = df_filtered[df_filtered['従業員名'] == global_person_value]
        if global_unit_value != 'すべて':
            df_filtered = df_filtered[df_filtered['UNIT'] == global_unit_value]

        st.sidebar.info(f"フィルター後: {len(df_filtered):,}件 / {len(df):,}件")

        # ========================================
        # 統合チャート表示
        # ========================================
#        st.subheader("工数分析グラフ")

        # 業務内容カラムの検出
        available_business_cols = get_available_business_content_columns(df_filtered)

        # X軸とグルーピング方法の選択
        col1, col2 = st.columns(2)

        with col1:
            # X軸選択（年月を含む）
            x_axis_options = (
                ['年月', '作業大分類', '作業中分類', '作業小分類', '個人', 'UNIT'] +
                available_business_cols
            )
            x_axis = st.selectbox(
                "X軸",
                x_axis_options,
                key="x_axis"
            )

        with col2:
            # グルーピング方法選択（年月を除く）
            grouping_options = (
                ['作業大分類', '作業中分類', '作業小分類', '個人', 'UNIT'] +
                available_business_cols
            )
            grouping = st.selectbox(
                "グルーピング方法",
                grouping_options,
                key="grouping"
            )

        # 期間ラベル作成
        if available_year_months:
            period_label = f"{start_year}-{start_month:02d} 〜 {end_year}-{end_month:02d}"
        else:
            period_label = None

        # チャート作成
        if len(df_filtered) > 0:
            # フィールド名のマッピング
            field_mapping = {
                '年月': '年月',
                '作業大分類': 'USER_FIELD_01',
                '作業中分類': 'USER_FIELD_02',
                '作業小分類': 'USER_FIELD_03',
                '個人': '従業員名',
                'UNIT': 'UNIT'
            }

            # X軸とグルーピングのフィールド名を取得
            x_field = field_mapping.get(x_axis, x_axis)  # 業務内容はそのまま
            group_field = field_mapping.get(grouping, grouping)

            # 年月列を作成（X軸が年月の場合）
            if x_field == '年月':
                df_filtered = df_filtered.copy()
                df_filtered['年月'] = df_filtered['年'].astype(str) + '-' + df_filtered['月'].astype(str).str.zfill(2)

            # グルーピング列を作成（グルーピングが年月の可能性はないが念のため）
            if group_field == '年月' and '年月' not in df_filtered.columns:
                df_filtered = df_filtered.copy()
                df_filtered['年月'] = df_filtered['年'].astype(str) + '-' + df_filtered['月'].astype(str).str.zfill(2)

            # チャートタイプの決定と作成
            from utils.visualization import create_unified_chart

            fig = create_unified_chart(
                df_filtered,
                x_field=x_field,
                group_field=group_field,
                x_axis_label=x_axis,
                grouping_label=grouping,
                range_label=period_label
            )

            st.plotly_chart(fig, use_container_width=True, config={})

            # データテーブル（折りたたみ式）
            with st.expander("作業時間[h] リスト", expanded=False):
                data_table = create_chart_data_table(
                    df_filtered,
                    x_field=x_field,
                    group_field=group_field,
                    x_axis_label=x_axis,
                    grouping_label=grouping
                )
                st.dataframe(data_table, use_container_width=True)
        else:
            st.warning("フィルター条件に一致するデータがありません")

        # ========================================
        # サイドバー: 情報表示
        # ========================================
        with st.sidebar:
            st.markdown("---")
            st.metric("総データ件数", f"{len(st.session_state.merged_data):,}")
            st.metric("総作業時間", f"{st.session_state.merged_data['作業時間(h)'].sum():.1f} h")
