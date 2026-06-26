# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **Effort-Dashboard** project for ULVAC Electric Design Management - a Streamlit application for merging multiple monthly effort data files and performing multi-dimensional analysis and visualization.

For a more detailed technical reference (data schema, dedup rules, derived columns, session state keys), see `TECHNICAL.md` in this directory.

## Architecture Overview

### Single-Page Streamlit Application with Two Tabs

The app has two tabs, rendered via `st.tabs(["データ登録", "工数分析グラフ"])`:

1. **データ登録** - Register effort data. Has its own mode radio with two options:
   - **総工数ファイルをアップロード** (Default) - Upload/use an existing merged effort data file directly
   - **月次データを統合** - Merge one or more monthly effort data files into the existing merged data
2. **工数分析グラフ** - Multi-dimensional analysis charts over whatever data is currently registered

The app automatically loads `merged_efforts.xlsx` from the application directory on startup if available (`st.session_state.merged_data`).

### Key Components

#### 1. `app.py` - Main Application
- Two tabs (データ登録 / 工数分析グラフ) via `st.tabs()`; the upload-mode radio lives inside the データ登録 tab
- Session state management for merged data (`merged_data`, `merged_excel_bytes`, `merged_excel_filename`, `default_loaded`)
- Default file loading (`merged_efforts.xlsx`) on first run
- File upload handling (multiple monthly files + optional existing merged file), using `BytesIO`-backed `UploadedFile` objects
- `preprocess_df()`: type coercion, invalid-row removal, USER_FIELD NaN→"未入力", and generates the derived **指番** column (see below)
- A single unified chart in 工数分析グラフ — there are no longer separate "display types" (作業内容/時間推移/個人/UNIT); instead the user picks **X軸** and **グルーピング方法** independently from the same option list, and `create_unified_chart()` decides chart type automatically
- Sidebar filters (global, always applied before the chart is built):
  - 期間 (period) slider — default range is the last 6 year-months in the data
  - 作業大分類 — single-select (`selectbox` with "すべて"); when changed, 作業中分類 selection is reset via `on_change=_reset_field2`
  - 作業中分類 — `st.multiselect` with a paired "含む／除外" radio button (`isin` / `~isin`); options narrow based on the selected 作業大分類; empty selection means no filtering
  - 個人 / 指番 — `st.multiselect` with a paired "含む／除外" radio button (`isin` / `~isin`); empty selection means no filtering
- Dynamic business content column detection (`業務内容1`〜`業務内容10`, via `get_available_business_content_columns()`) feeds into the X軸/グルーピング option list

#### 2. `utils/data_merger.py` - Data Merging Logic
Ported from `Effort-analyzer/job_organizer.py` with the following functions:
- `process_monthly_data()`: Convert a monthly report file's **`YubiNippoDB`** sheet (auto-detected: when a file has multiple sheets, `'YubiNippoDB'` is used; a single-sheet file uses that sheet directly) to merged_efforts format
- `merge_effort_data()`: Merge new monthly data with existing merged data. Rows are matched by a composite key (`DEDUP_KEY_COLUMNS`: 年・月・従業員名・UNIT・USER_FIELD_01〜05, built via `_build_dedup_keys()`); any existing row whose key matches a new row is dropped before concatenation, so the monthly file's data wins **row by row** (not a whole year-month wipe)
- `split_business_content()`: Split 業務内容 into 業務内容1〜10 columns
- `process_multiple_monthly_files()`: Process multiple monthly files at once, then merge and split business content
- Japanese text processing functions (normalize_text, extract_parentheses_content, split_tasks, etc.)

#### 3. `utils/visualization.py` - Visualization Logic
Plotly Express-based chart generation and data prep:
- `sort_with_config()`: Sorts values per `group_order_config.json`, falling back to alphabetical order for unregistered fields (e.g. `UNIT`, `WBS要素(代入)`, `指番`)
- `get_available_business_content_columns()`: Detect non-empty 業務内容 columns (stops at the first empty one)
- `filter_data_by_period()`: Period filtering
- `create_chart_data_table()`: Pivot table mirroring the chart's aggregation, shown in a collapsible expander
- `create_unified_chart()`: Picks chart type automatically — line chart when `x_field == '年月'`, plain (ungrouped) bar when `x_field == group_field`, otherwise a stacked bar chart

There is no `filter_data_by_hierarchy()` and no per-display-type chart functions (`create_work_content_chart`, `create_time_series_chart`, `create_person_chart`, `create_unit_chart`) — those belonged to an earlier version of the app and were removed during the dashboard refactor.

### The "指番" derived column

`指番` does not exist in `merged_efforts.xlsx`; it is generated at runtime in `preprocess_df()` (`app.py`):
- If `WBS要素(代入)` is not blank, use its value (this column **is** the 指番 value, despite its name)
- Else if `UNIT` is not blank, use `UNIT` as a substitute
- Else NaN (excluded when used as an axis/filter, same as `WBS要素(代入)`'s own NaN handling)

It is used both as an axis/grouping option in 工数分析グラフ and as the sidebar's "指番" filter (which replaced a now-removed direct `UNIT` filter).

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## Data Flow

### データ登録 tab

#### Mode 1: 総工数ファイルをアップロード (default)
- Upload an existing merged efforts file OR use the auto-loaded default `merged_efforts.xlsx`
- If the uploaded file looks like a direct YubiNippo export (`作業日` present, `年` absent), `年`/`月` are auto-generated from `作業日`
- Immediately enables all analysis features; no further processing required

#### Mode 2: 月次データを統合

1. **Input**:
   - Optional: existing merged efforts file (.xlsx)
   - Required: 1+ monthly effort data files (.xlsx with a `YubiNippoDB` sheet)

2. **Processing** (`process_multiple_monthly_files()`):
   - Extract year/month from each monthly file's `作業日` column
   - Convert `作業時間` from minutes to hours (`作業時間(h)`) if the monthly sheet doesn't already provide `作業時間(h)`
   - Merge with existing data — rows are overwritten **row by row** when 年・月・従業員名・UNIT・USER_FIELD_01〜05 all match (see `merge_effort_data()` above)
   - Split `業務内容` into `業務内容1〜10` columns using the Japanese text-processing logic

3. **Output**:
   - Unified merged_efforts file downloadable as .xlsx (rename to `merged_efforts.xlsx` and place in the app directory to auto-load it next run)
   - Stored in session state for the analysis tab

### 工数分析グラフ tab

Available after loading data via either データ登録 mode.

1. **Sidebar filters** (global, applied in this order before charting):
   - 期間 slider (year-month range)
   - 作業大分類 (single-select, `==`; changing it resets 作業中分類 selection)
   - 作業中分類 (multiselect + 含む/除外 radio, `isin`/`~isin`; options cascade from 作業大分類)
   - 個人 (multiselect + 含む/除外 radio, `isin`/`~isin`)
   - 指番 (multiselect + 含む/除外 radio, `isin`/`~isin`, operates on the derived 指番 column)

2. **X軸 / グルーピング方法**: two independent selectboxes sharing the same option list, built in this fixed order:
   `年月`, `作業大分類`, `作業中分類`, `作業小分類`, `指番` (only if the column is present), `総合効率` (USER_FIELD_05), `個人`, then the dynamically-detected `業務内容1`〜`業務内容10`.

3. **Chart + data table**: `create_unified_chart()` renders the figure; `create_chart_data_table()` renders the same aggregation as a table inside an expander below the chart.

## Critical Implementation Details

### Cascading classification filters (作業大分類 → 作業中分類)

Implemented directly in `app.py` (not a separate utility function):
- 作業大分類: single-select `selectbox` with "すべて"; options come from the period-filtered data
- 作業中分類: `multiselect` + 含む/除外 radio; options narrow to rows matching the selected 作業大分類 (or the full period-filtered data if 作業大分類 is "すべて"); empty selection means no filter
- When 作業大分類 changes, `_reset_field2()` (on_change callback) clears the 作業中分類 session_state to prevent stale selections
- 作業大分類 is "すべて" + 作業中分類 has selections → filters by 作業中分類 regardless of which 作業大分類 they belong to
- 個人/指番 options are *not* narrowed by 作業大分類/作業中分類 — they are computed from the period-filtered data only, independent of the other filters

### Dynamic Business Content Detection

The `get_available_business_content_columns()` function automatically detects which 業務内容 columns contain data:
- Checks 業務内容1 through 業務内容10 in order
- Excludes columns that are completely empty (all null or empty strings)
- Stops checking after the first empty column (assumes no data in higher numbers)
- Returns list of available column names (e.g., ['業務内容1', '業務内容2', '業務内容3'])
- Used to populate the X軸/グルーピング option list dynamically

### Business Content Splitting

The 業務内容 splitting logic (in data_merger.py) is complex:
- Parentheses content extraction (nested brackets supported)
- Underscore and space-based tokenization
- Japanese/English mixed text handling
- Company name recognition (アドテック, オムロン, etc.)
- Business term identification (セミナー, 検図, etc.)
- Fullwidth to halfwidth normalization
- Duplicate removal

### Data Validation

Automatic filtering of invalid data:
- Rows with '作業時間(h)' ≤ 0 are excluded
- Rows with missing '年' or '月' are excluded
- Duplicate rows in merge (matched by 年・月・従業員名・UNIT・USER_FIELD_01〜05) are overwritten by the monthly file's data, row by row — not a whole year-month wipe

## File Structure

```
Effort-Dashboard/
├── app.py                    # Main Streamlit application (two tabs: データ登録 / 工数分析グラフ)
├── utils/
│   ├── __init__.py
│   ├── data_merger.py       # Data merging and business content splitting
│   └── visualization.py     # Plotly chart generation
├── group_order_config.json  # Display-order config for sort_with_config()
├── requirements.txt         # Dependencies
├── TECHNICAL.md             # Detailed technical reference (schema, dedup rules, derived columns)
└── CLAUDE.md                # This file (developer documentation)
```

## Dependencies

- **streamlit** (>=1.30.0): Web UI framework
- **pandas** (>=2.0.0): Data processing
- **openpyxl** (>=3.1.0): Excel reading
- **xlsxwriter** (>=3.0.0): Excel writing
- **plotly** (>=5.18.0): Interactive visualizations

## Common Development Tasks

### Modifying Filter Logic

Filter logic lives in `app.py`; period filtering lives in `utils/visualization.py`:
- Upload-mode selector: `app.py` (radio widget with 2 options, inside the データ登録 tab)
- Sidebar filters (工数分析グラフ tab): 期間 slider, 作業大分類/作業中分類 cascading selectboxes, 個人/指番 multiselect+含む/除外 pairs — all in `app.py`
- Period filtering: `filter_data_by_period()` in `utils/visualization.py`
- To add a new global filter, follow the 個人/指番 multiselect+radio pattern if multi-value include/exclude is needed, or the 作業大分類/作業中分類 selectbox pattern for a simple single-value cascading filter

### Adding a New X軸/グルーピング Option

1. Add the column to `FIELD_MAPPING` in `app.py` (UI label → DataFrame column name)
2. If it's a derived column (like 指番), compute it in `preprocess_df()`
3. Insert the new label into the `axis_choices` list in `app.py` at the desired position
4. If the column should also be registered for non-alphabetical display ordering, add it to `group_order_config.json`

### Modifying Business Content Splitting

The splitting logic is in `utils/data_merger.py`:
- `split_tasks()`: Main splitting function
- `extract_parentheses_content()`: Parentheses handling
- `normalize_text()`: Text normalization
- Constants: `COMPANY_NAMES`, `BUSINESS_TERMS`

Changes here should be tested with real Japanese text data to avoid breaking the complex logic.

### Chart Customization

All charts use Plotly, built in `create_unified_chart()` (`utils/visualization.py`). Common customizations:
- Color schemes: Plotly uses automatic color cycling, override with `marker=dict(color=...)`
- Hover info: All charts use custom `hovertemplate` with format: `'%{x}<br>作業時間(h): %{y:.1f}<extra></extra>'`
  - Shows classification name (X-axis value) and 作業時間(h) with 1 decimal place
  - `<extra></extra>` removes the default trace name box
- Height: Set in `fig.update_layout(height=500)`
- Legend/axis ordering: controlled via `category_orders`, computed from `sort_with_config()`

## Important Notes

- This app is designed for **Streamlit Cloud** deployment
- Session state (`st.session_state`) is used to persist merged data across interactions
- Default file loading: Attempts to load `merged_efforts.xlsx` from app directory on first run
- File uploads use `BytesIO`-backed objects (not file paths) for Streamlit Cloud compatibility
- Progress callbacks are used during long-running merge operations
- All user-facing text is in Japanese
- Data processing logic is directly ported from `Effort-analyzer/job_organizer.py` and should remain synchronized
- Field name mapping:
  - USER_FIELD_01 ↔ 作業大分類
  - USER_FIELD_02 ↔ 作業中分類
  - USER_FIELD_03 ↔ 作業小分類
  - USER_FIELD_05 ↔ 総合効率 (axis/grouping option only; USER_FIELD_04 has no dedicated axis label)

## Related Projects

- **Effort-analyzer**: Source of data merging and business content splitting logic
  - Located at: `../Effort-analyzer/`
  - Key file: `job_organizer.py`
  - If modifying splitting logic, consider whether changes should apply to both projects

## Testing

No automated tests are configured. Manual testing workflow:
1. Prepare sample monthly effort data files (.xlsx with a `YubiNippoDB` sheet)
2. Run app locally: `streamlit run app.py`
3. Verify default file loading (merged_efforts.xlsx) and info message
4. Test upload-mode switching (総工数ファイルをアップロード ↔ 月次データを統合)
5. Test merge functionality with multiple files, including a file that has rows overlapping existing data on 年・月・従業員名・UNIT・USER_FIELD_01〜05 — verify only the matching rows are overwritten, not the whole year-month
6. Test X軸/グルーピング combinations in 工数分析グラフ, including 指番 and 総合効率, and dynamic 業務内容X columns
7. Test 個人/指番 filters in both 含む and 除外 modes, with single and multiple selections
8. Verify download functionality

## Performance Considerations

- Large datasets (>10,000 rows) may cause slow rendering in Plotly charts
- Business content splitting is O(n) per row and can be slow for large files
- Consider adding caching (`@st.cache_data`) for expensive operations if performance becomes an issue
- Period filtering reduces data size before visualization, improving render speed
