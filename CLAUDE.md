# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This is the **Effort-Dashboard** project for ULVAC Electric Design Management - a Streamlit application for merging multiple monthly effort data files and performing multi-dimensional analysis and visualization.

## Architecture Overview

### Single-Page Streamlit Application

This is a unified application with two equal-level operation modes:
1. **既存ファイル分析** (Default) - Analyze existing merged effort data file
2. **月次データ統合** - Merge monthly effort data files and create unified effort data

Both modes provide access to the same multi-dimensional analysis features. The app automatically loads `merged_efforts.xlsx` from the application directory on startup if available.

### Key Components

#### 1. `app.py` - Main Application
- Single-page Streamlit app with operation mode selector (既存ファイル分析/月次データ統合)
- Session state management for merged data
- Default file loading (merged_efforts.xlsx) on first run
- File upload handling (multiple monthly files + optional existing merged file)
- Global and local hierarchical filters (作業大分類/作業中分類)
- Display type switching (4 types: 作業内容, 時間推移, 個人, UNIT)
- Dynamic business content column detection and grouping

#### 2. `utils/data_merger.py` - Data Merging Logic
Ported from `Effort-analyzer/job_organizer.py` with the following functions:
- `process_monthly_data()`: Convert monthly report data to merged_efforts format
- `merge_effort_data()`: Merge new data with existing merged data
- `split_business_content()`: Split 業務内容 into 業務内容1〜10 columns
- `process_multiple_monthly_files()`: Process multiple monthly files at once
- Japanese text processing functions (normalize_text, extract_parentheses_content, split_tasks, etc.)

#### 3. `utils/visualization.py` - Visualization Logic
Plotly-based chart generation:
- `get_available_business_content_columns()`: Detect non-empty 業務内容 columns
- `filter_data_by_period()`: Period filtering
- `filter_data_by_hierarchy()`: Hierarchical filter determining X-axis and grouping field
- `create_work_content_chart()`: Stacked bar chart for work content (dynamic X-axis)
- `create_time_series_chart()`: Line chart for time series (X-axis: year-month)
- `create_person_chart()`: Stacked bar chart per person (X-axis: year-month)
- `create_unit_chart()`: Stacked bar chart per UNIT (X-axis: year-month)

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Run the app
streamlit run app.py
```

## Data Flow

### Operation Modes

The application presents two equal-level operation modes via a horizontal radio selector (default: 既存ファイル分析):

#### Mode 1: 既存ファイル分析 (Existing File Analysis)
- Upload an existing merged efforts file OR use the default merged_efforts.xlsx
- Immediately enables all analysis features
- No data processing required

#### Mode 2: 月次データ統合 (Monthly Data Integration)

1. **Input**:
   - Optional: Existing merged efforts file (.xlsx)
   - Required: 1+ monthly effort data files (.xlsx with '日報データ' sheet)

2. **Processing**:
   - Extract year/month from '作業日' column
   - Convert '作業時間' from minutes to hours
   - Merge with existing data (overwrite duplicate year-months)
   - Split '業務内容' into '業務内容1〜10' columns using complex Japanese text processing

3. **Output**:
   - Unified merged_efforts file downloadable as .xlsx
   - Stored in session state for analysis section

### Analysis Section

Available after loading data via either operation mode.

1. **Global Filters** (Sidebar):
   - Period filter: Start year-month to end year-month
   - Hierarchical filter: 作業大分類 (USER_FIELD_01) → 作業中分類 (USER_FIELD_02)
     - Cascading logic: 作業中分類 options depend on 作業大分類 selection
     - "すべて" option available at each level

2. **Display Types**:
   - **作業内容** (Work Content): Stacked bar chart, X-axis determined by local filters
   - **時間推移** (Time Series): Line chart, X-axis = year-month
   - **個人** (Person): Stacked bar chart per selected person, X-axis = year-month
   - **UNIT**: Stacked bar chart per selected UNIT, X-axis = year-month

3. **Local Filters** (Per Display Type):
   - Each display type has its own local 作業大分類/作業中分類 filters
   - Filters are applied on top of global filters
   - Determine X-axis for "作業内容" display type

4. **Grouping Options** (vary by display type):
   - All display types support dynamic 業務内容 columns (業務内容1, 業務内容2, ... up to 業務内容10)
   - Empty 業務内容 columns are automatically excluded from grouping options
   - **作業内容**: 作業内容別／個人別／業務内容X／UNIT別
   - **時間推移**: 作業内容別／個人別／業務内容X／UNIT別
   - **個人**: 作業内容別／業務内容X／UNIT別 (個人別 excluded)
   - **UNIT**: 作業内容別／個人別／業務内容X (UNIT別 excluded)

## Critical Implementation Details

### Hierarchical Filter Logic

The `filter_data_by_hierarchy()` function implements simplified filtering logic that determines both data filtering and X-axis selection:

**Returns:** `(filtered_df, x_field, group_field_for_work_content)`

**Behavior:**
1. **作業大分類 = "すべて"**:
   - No filtering on USER_FIELD_01
   - X-axis = USER_FIELD_01
   - If 作業中分類 = "すべて": group_field = USER_FIELD_02
   - If 作業中分類 = specific value: filter by USER_FIELD_02, group_field = USER_FIELD_03

2. **作業大分類 = specific value**:
   - Filter by USER_FIELD_01
   - X-axis = USER_FIELD_02
   - If 作業中分類 = "すべて": group_field = USER_FIELD_03
   - If 作業中分類 = specific value: filter by USER_FIELD_02, group_field = USER_FIELD_03

The `group_field_for_work_content` is used when grouping method is "作業内容別".

### Dynamic Business Content Detection

The `get_available_business_content_columns()` function automatically detects which 業務内容 columns contain data:
- Checks 業務内容1 through 業務内容10 in order
- Excludes columns that are completely empty (all null or empty strings)
- Stops checking after the first empty column (assumes no data in higher numbers)
- Returns list of available column names (e.g., ['業務内容1', '業務内容2', '業務内容3'])
- Used to populate grouping dropdowns dynamically

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
- Duplicate year-month combinations in merge are overwritten (not error)

### Data Preview

The data preview section displays filtered data with specific columns hidden:
- Hidden columns: USER_FIELD_04, USER_FIELD_05, 第1分類, 第2分類, 第3分類, 業務内容
- Shows 19 of 25 total columns
- Limited to first 100 rows for performance

## File Structure

```
Effort-Dashboard/
├── app.py                    # Main Streamlit application (single page, two sections)
├── utils/
│   ├── __init__.py
│   ├── data_merger.py       # Data merging and business content splitting
│   └── visualization.py     # Plotly chart generation
├── requirements.txt         # Dependencies
├── README.md               # User-facing documentation (Japanese)
└── CLAUDE.md               # This file (developer documentation)
```

## Dependencies

- **streamlit** (>=1.30.0): Web UI framework
- **pandas** (>=2.0.0): Data processing
- **openpyxl** (>=3.1.0): Excel reading
- **xlsxwriter** (>=3.0.0): Excel writing
- **plotly** (>=5.18.0): Interactive visualizations

## Common Development Tasks

### Modifying Filter Logic

Filter logic is in `app.py` (UI) and `utils/visualization.py` (data processing):
- Operation mode selector: app.py (radio widget with 2 options)
- Global filters (sidebar): Period filter and hierarchical filters (作業大分類/作業中分類)
- Local filters (per display type): Independent hierarchical filters for each display type
- Hierarchical filtering: `filter_data_by_hierarchy()` in visualization.py
  - Returns 3 values: (filtered_df, x_field, group_field_for_work_content)
  - X-axis determination logic based on filter selections
- Period filtering: `filter_data_by_period()` in visualization.py

### Adding New Display Types

1. Add new radio option in app.py (`display_type` radio widget)
2. Create new chart generation function in `utils/visualization.py`
   - Accept `group_field_for_work_content` parameter
   - Handle dynamic 業務内容 columns in grouping logic
3. Add new conditional block in app.py for the display type
   - Include local hierarchical filters (作業大分類/作業中分類)
   - Call `get_available_business_content_columns()` for dynamic grouping options
   - Call `filter_data_by_hierarchy()` to get filtered data and field names
4. Follow existing patterns (stacked bar for counts, line chart for time series)

### Modifying Business Content Splitting

The splitting logic is in `utils/data_merger.py`:
- `split_tasks()`: Main splitting function
- `extract_parentheses_content()`: Parentheses handling
- `normalize_text()`: Text normalization
- Constants: `COMPANY_NAMES`, `BUSINESS_TERMS`

Changes here should be tested with real Japanese text data to avoid breaking the complex logic.

### Chart Customization

All charts use Plotly. Common customizations:
- Color schemes: Plotly uses automatic color cycling, override with `marker=dict(color=...)`
- Hover info: All charts use custom `hovertemplate` with format: `'%{x}<br>作業時間(h): %{y:.1f}<extra></extra>'`
  - Shows classification name (X-axis value) and 作業時間(h) with 1 decimal place
  - `<extra></extra>` removes the default trace name box
- Text on bars: Set via `text` and `textposition` parameters (not currently used)
- Height: Set in `fig.update_layout(height=600)`
- X-axis labels: Mapped from field names (USER_FIELD_01 → 作業大分類, USER_FIELD_02 → 作業中分類, USER_FIELD_03 → 作業小分類)

## Important Notes

- This app is designed for **Streamlit Cloud** deployment
- Session state (`st.session_state`) is used to persist merged data and operation mode across interactions
- Default file loading: Attempts to load `merged_efforts.xlsx` from app directory on first run
- File uploads use BytesIO objects (not file paths) for Streamlit compatibility
- Progress callbacks are used during long-running merge operations
- All user-facing text is in Japanese
- Data processing logic is directly ported from `Effort-analyzer/job_organizer.py` and should remain synchronized
- Field name mapping:
  - USER_FIELD_01 ↔ 作業大分類
  - USER_FIELD_02 ↔ 作業中分類
  - USER_FIELD_03 ↔ 作業小分類

## Related Projects

- **Effort-analyzer**: Source of data merging and business content splitting logic
  - Located at: `../Effort-analyzer/`
  - Key file: `job_organizer.py`
  - If modifying splitting logic, consider whether changes should apply to both projects

## Testing

No automated tests are configured. Manual testing workflow:
1. Prepare sample monthly effort data files (.xlsx with '日報データ' sheet)
2. Run app locally: `streamlit run app.py`
3. Verify default file loading (merged_efforts.xlsx) and info message
4. Test operation mode switching (既存ファイル分析 ↔ 月次データ統合)
5. Test merge functionality with multiple files
6. Test all 4 display types with various filter combinations:
   - Verify X-axis changes based on hierarchical filter selections
   - Test all grouping options including dynamic 業務内容 columns
   - Verify hover formatting (classification + 作業時間(h) with 1 decimal)
7. Verify download functionality
8. Test data preview (verify hidden columns are excluded)
9. Test edge cases: empty data, single month, duplicate months, empty 業務内容 columns

## Performance Considerations

- Large datasets (>10,000 rows) may cause slow rendering in Plotly charts
- Business content splitting is O(n) per row and can be slow for large files
- Consider adding caching (`@st.cache_data`) for expensive operations if performance becomes an issue
- Period filtering reduces data size before visualization, improving render speed
