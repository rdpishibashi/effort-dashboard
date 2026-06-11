# TECHNICAL.md — Effort-Dashboard

最終更新: 2026-06-11

## 概要

複数月の工数データをマージ・蓄積し、様々な軸で分析グラフを表示する Streamlit ダッシュボード。
Plotly Express による対話的グラフと、フィルタ・X 軸・グルーピングの組み合わせで多角的な工数分析が可能。

---

## ディレクトリ構成

```
Effort-Dashboard/
├── app.py                      # Streamlit エントリポイント
├── requirements.txt
├── group_order_config.json     # 大分類・中分類等の表示順設定
├── merged_efforts.xlsx         # 蓄積済み工数データ（ローカル保存用）
├── utils/
│   ├── data_merger.py          # 月次データのマージ・正規化処理
│   └── visualization.py        # Plotly グラフ生成・フィルタリング
```

---

## アーキテクチャ

### データ登録フロー（2 種類）

```
① 総工数ファイル直接アップロード
   → Excel アップロード（merged_efforts.xlsx 互換 または YubiNippo 直接エクスポート）
   → YubiNippo 形式の場合: 作業日 → 年・月 を自動生成
   → st.session_state['merged_data'] に格納

② 月次データをマージして登録
   → 月次ファイル複数アップロード
   → process_multiple_monthly_files()  # data_merger.py
   → 既存 merged_data とマージ
   → st.session_state['merged_data'] に格納
   → 統計情報（年月 × 作業大分類ピボット）を画面表示
   → merged_efforts.xlsx としてダウンロード可能
```

### 分析グラフフロー

```
merged_data (DataFrame)
  → preprocess_df()             # 型変換・無効行除去・USER_FIELD NaN→"未入力"
  → filter_data_by_period()     # 期間フィルタ
  → [大分類・中分類・個人・UNIT フィルタ適用]
  → create_unified_chart()      # チャート種別自動判定・Plotly グラフ生成
  → create_chart_data_table()   # データテーブル（折りたたみ表示）
```

---

## データスキーマ（merged_efforts.xlsx）

主要列:

| 列名 | 説明 |
|------|------|
| `年` | 作業年（整数）|
| `月` | 作業月（整数）|
| `従業員名` | 作業者名 |
| `UNIT` | 所属ユニット |
| `作業時間(h)` | 工数（時間）|
| `USER_FIELD_01` | 作業大分類 |
| `USER_FIELD_02` | 作業中分類 |
| `USER_FIELD_03` | 作業小分類 |
| `USER_FIELD_04` | ユーザー定義フィールド 4 |
| `USER_FIELD_05` | ユーザー定義フィールド 5 |
| `業務内容` | 業務内容（生テキスト）|
| `業務内容1`〜`業務内容10` | 業務内容を分割した列 |
| `WBS要素(代入)` | WBS 要素コード |

**NaN の扱い:**
- `USER_FIELD_01〜05` の NaN は前処理で `"未入力"` に置換 → グラフ集計に含まれる
- `WBS要素(代入)` / `業務内容X` の NaN は置換しない → それらを軸に選んだ場合は除外される（設計上の仕様）

---

## app.py — モジュール定数・ヘルパー関数

### 定数

| 定数 | 内容 |
|------|------|
| `FIELD_MAPPING` | UI 表示名 → DataFrame 列名のマッピング |
| `USER_FIELDS` | `USER_FIELD_01〜05` のリスト |

### ヘルパー関数

| 関数 | 説明 |
|------|------|
| `preprocess_df(raw_df)` | 型変換・無効行除去・USER_FIELD NaN→"未入力" |
| `make_stats_pivot(df)` | 年月 × USER_FIELD_01 ピボットテーブルを返す |
| `render_sidebar_overview(placeholder)` | サイドバーの使い方ガイドを描画 |
| `render_data_status()` | サイドバーのデータ状態を描画 |

---

## `utils/data_merger.py`

月次工数データ（日報データシート）を merged_efforts 形式に変換する。

主要関数:

| 関数 | 説明 |
|------|------|
| `process_monthly_data(file, sheet_name)` | 単一月次ファイルを処理、シート名は自動検出 |
| `process_multiple_monthly_files(files)` | 複数月次ファイルを順次処理してマージ |
| `extract_year_month_from_date(date_str)` | 複数日付フォーマット対応の年月抽出 |

**シート名の自動検出ロジック:**
- 複数シートあり → `'日報データ'` シートを使用
- 単一シートのみ → そのシートを使用

**YubiNippo 直接エクスポート対応:**
- `作業日` 列が存在し `年`/`月` 列がない場合、`作業日` から自動生成（`総工数ファイルをアップロード` モード）
- `作業時間(h)` 列が存在する場合はそのまま使用（`作業時間` 列からの分/60 変換は不要）

---

## `utils/visualization.py`

Plotly グラフ生成とデータ前処理を担う。

主要関数・定数:

| 要素 | 説明 |
|------|------|
| `FIELD_LABELS` | DataFrame 列名 → 日本語表示名のマッピング（凡例・軸ラベル用）|
| `sort_with_config(values, field_name)` | `group_order_config.json` に従いソート、未登録はアルファベット順 |
| `filter_data_by_period(df, start, end)` | 年月でのフィルタリング |
| `get_available_business_content_columns(df)` | 利用可能な業務内容列を返す（空列が現れた時点で打ち切り）|
| `create_chart_data_table(df, x_field, group_field, ...)` | グラフと同一集計の pivot テーブルを返す |
| `create_unified_chart(df, x_field, group_field, ...)` | チャート種別を自動判定して Plotly Figure を返す |

### `create_unified_chart` のチャート種別ロジック

| 条件 | チャート種別 |
|------|------------|
| `x_field == '年月'` | 折れ線グラフ（時系列）|
| `x_field == group_field` | 棒グラフ（グルーピングなし）|
| それ以外 | 積み上げ棒グラフ |

凡例の表示順は `category_orders` パラメータで明示的に制御（`sort_with_config` の返り値を使用）。

---

## `group_order_config.json`

各フィールドの表示順を定義する JSON。

```json
{
  "USER_FIELD_01": ["受注前", "標準作業", "指番なし", ...],
  "USER_FIELD_02": ["見積り", "仕様検討", "構想設計", ...]
}
```

- 指定外の値はアルファベット順でリスト末尾に追加される
- `sort_with_config()` が参照する
- `UNIT` や `WBS要素(代入)` は未登録 → アルファベット順

---

## セッション状態

| キー | 型 | 内容 |
|------|-----|------|
| `merged_data` | `DataFrame \| None` | 現在登録されている工数データ |
| `merged_excel_bytes` | `bytes \| None` | ダウンロード用 Excel バイト列 |
| `merged_excel_filename` | `str \| None` | ダウンロード用ファイル名 |
| `default_loaded` | `bool` | デフォルトファイル読み込み済みフラグ |
| `grouping` | `str` | グルーピング方法の選択値（初期値: `'作業大分類'`）|

---

## 依存パッケージ

```
streamlit>=1.40.0
pandas>=2.0.0
openpyxl>=3.1.0
xlsxwriter>=3.0.0
plotly>=5.18.0
```

---

## 既知の制限

| 制限 | 詳細 |
|------|------|
| データの永続化なし | `merged_data` はセッション内のみ保持。ブラウザリロードで消える |
| `merged_efforts.xlsx` のローカル配置 | クラウドデプロイ時は毎回アップロードが必要 |
| 月次ファイルのフォーマット依存 | `'日報データ'` シート名と列名が固定されている |
| 大量データ | 数万行超では Plotly の描画が遅くなる |

---

## 機能拡張ポイント

| テーマ | 実装アプローチ |
|--------|--------------|
| データの自動保存 | Streamlit Cloud 非対応。ローカル運用時は `merged_efforts.xlsx` への自動書き込みを追加 |
| 月次フォーマットの汎化 | `data_merger.py` に列名マッピング設定を追加してフォーマット変更に対応 |
| グラフのダウンロード | Plotly の `fig.write_image()` または `to_html()` でエクスポートボタンを追加 |
| フィルタプリセット保存 | `group_order_config.json` にフィルタ設定セクションを追加 |
| WBS・業務内容の未入力集計 | `preprocess_df()` で `WBS要素(代入)` / `業務内容X` の NaN も `"未入力"` に置換 |
