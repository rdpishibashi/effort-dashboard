# -*- coding: utf-8 -*-
"""
data_merger.py - 工数データマージ処理

Effort-analyzerのjob_organizer.pyから移植したロジック
"""

import pandas as pd
import numpy as np
import re
import unicodedata
import traceback
from datetime import datetime


# 業務内容分割用の定数
COMPANY_NAMES = ['アドテック', 'オムロン', 'オンテック', 'キオクシア', 'キューセス', 'コムズ',
                 'ダイトロン', 'マイクロン', 'シマデン', '富士電機']
BUSINESS_TERMS = ['L室電動リフター', 'セミナー', 'その他', '安全規格対応', '機能安全',
                  '検図', '主事補研修', '生産中止', '打合せ', '会議']


def extract_year_month_from_date(date_str):
    """作業日から年と月を抽出する"""
    try:
        if pd.isna(date_str) or date_str == '':
            return None, None

        # 日付文字列をパース
        if isinstance(date_str, str):
            # 様々な日付形式に対応
            date_formats = ['%Y/%m/%d', '%Y-%m-%d', '%Y年%m月%d日']
            for fmt in date_formats:
                try:
                    date_obj = datetime.strptime(date_str, fmt)
                    return int(date_obj.year), int(date_obj.month)
                except ValueError:
                    continue
        elif hasattr(date_str, 'year'):  # datetime object
            return int(date_str.year), int(date_str.month)

        return None, None
    except:
        return None, None


def process_monthly_data(monthly_file_input, sheet_name='日報データ'):
    """
    月次工数データファイルの日報データシートを処理してmerged_efforts形式に変換
    monthly_file_input: ファイルパス（文字列）またはBytesIOオブジェクト
    """
    try:
        # ファイル入力の種類を判定して適切に読み込み
        if hasattr(monthly_file_input, 'read'):
            # BytesIOオブジェクトの場合
            df = pd.read_excel(monthly_file_input, sheet_name=sheet_name, engine='openpyxl')
        else:
            # ファイルパスの場合
            df = pd.read_excel(monthly_file_input, sheet_name=sheet_name, engine='openpyxl')

        print(f"月次データ読み込み完了: {len(df)}行")
        print(f"元データのカラム: {list(df.columns)}")

        # 必要なカラムのマッピング
        column_mapping = {
            '従業員名': '従業員名',
            '作業時間': '作業時間_分',  # 一時的な名前
            'USER_FIELD_01': 'USER_FIELD_01',
            'USER_FIELD_02': 'USER_FIELD_02',
            'USER_FIELD_03': 'USER_FIELD_03',
            'USER_FIELD_04': 'USER_FIELD_04',
            'USER_FIELD_05': 'USER_FIELD_05',
            '第1分類': '第1分類',
            '第2分類': '第2分類',
            '第3分類': '第3分類',
            'UNIT': 'UNIT',
            'MODULE': 'MODULE',
            '業務内容': '業務内容'
        }

        # 新しいデータフレームを作成
        processed_df = pd.DataFrame()

        # 作業日から年と月を抽出
        years = []
        months = []
        for date_val in df['作業日']:
            year, month = extract_year_month_from_date(date_val)
            years.append(year)  # 数字として格納
            months.append(month)  # 数字として格納

        processed_df['年'] = years
        processed_df['月'] = months

        # 他のカラムをマッピング
        for original_col, new_col in column_mapping.items():
            if original_col in df.columns:
                if original_col == '作業時間':
                    # 作業時間を60で割って時間単位に変換
                    processed_df['作業時間(h)'] = pd.to_numeric(df[original_col], errors='coerce') / 60
                else:
                    processed_df[new_col] = df[original_col]
            else:
                # カラムが存在しない場合は空文字で埋める
                if original_col == '作業時間':
                    processed_df['作業時間(h)'] = 0
                else:
                    processed_df[new_col] = ''

        # merged_effortsの期待されるカラム順序に合わせる
        expected_columns = [
            '年', '月', '従業員名', '作業時間(h)',
            'USER_FIELD_01', 'USER_FIELD_02', 'USER_FIELD_03', 'USER_FIELD_04', 'USER_FIELD_05',
            '第1分類', '第2分類', '第3分類', 'UNIT', 'MODULE', '業務内容'
        ]

        # 不足しているカラムを空文字で追加
        for col in expected_columns:
            if col not in processed_df.columns:
                processed_df[col] = ''

        # カラム順序を合わせる
        processed_df = processed_df[expected_columns]

        # 無効なデータを除外
        # 1. 年または月が抽出できなかった行
        # 2. 作業時間(h)が0以下の行
        valid_rows = (processed_df['年'].notna()) & (processed_df['月'].notna()) & \
                    (pd.to_numeric(processed_df['作業時間(h)'], errors='coerce') > 0)

        before_filter = len(processed_df)
        processed_df = processed_df[valid_rows]
        after_filter = len(processed_df)

        print(f"フィルタリング: {before_filter}行 → {after_filter}行 ({before_filter - after_filter}行除外)")

        return processed_df

    except Exception as e:
        print(f"月次データ処理エラー: {e}")
        print(f"エラー詳細: {traceback.format_exc()}")
        return None


def merge_effort_data(existing_file_input, new_data_df):
    """
    既存のmerged_effortsファイルに新しいデータを追加
    existing_file_input: ファイルパス（文字列）またはBytesIOオブジェクト
    new_data_df: 新しいデータのDataFrame

    existing_file_inputがNoneの場合は、新規作成として扱う
    """
    try:
        # 既存ファイルが指定されていない場合は新規作成
        if existing_file_input is None:
            print("既存ファイルなし - 新規作成モード")
            merged_df = new_data_df.copy()
        else:
            # ファイル入力の種類を判定して適切に読み込み
            if hasattr(existing_file_input, 'read'):
                # BytesIOオブジェクトの場合
                existing_df = pd.read_excel(existing_file_input, engine='openpyxl')
            else:
                # ファイルパスの場合
                existing_df = pd.read_excel(existing_file_input)

            print(f"既存データ読み込み完了: {len(existing_df)}行")

            # 既存データのクリーニング
            # 1. 年と月を数字に統一
            existing_df['年'] = pd.to_numeric(existing_df['年'], errors='coerce').astype('Int64')
            existing_df['月'] = pd.to_numeric(existing_df['月'], errors='coerce').astype('Int64')

            # 2. 作業時間が0以下のデータを除外
            before_existing = len(existing_df)
            existing_df = existing_df[
                (pd.to_numeric(existing_df['作業時間(h)'], errors='coerce') > 0) &
                (existing_df['年'].notna()) & (existing_df['月'].notna())
            ]
            after_existing = len(existing_df)

            print(f"既存データクリーニング: {before_existing}行 → {after_existing}行 ({before_existing - after_existing}行除外)")

            # 重複チェック（年月の組み合わせ）
            new_year_months = set(zip(new_data_df['年'], new_data_df['月']))
            existing_year_months_set = set(zip(existing_df['年'], existing_df['月']))

            overlapping = new_year_months.intersection(existing_year_months_set)
            if overlapping:
                print(f"警告: 重複する年月があります: {overlapping}")
                # Streamlit実行時は重複データを上書き
                for year, month in overlapping:
                    mask = (existing_df['年'] == year) & (existing_df['月'] == month)
                    existing_df = existing_df[~mask]
                    print(f"既存データから {year}-{month} のデータを削除しました")

            # データを結合
            merged_df = pd.concat([existing_df, new_data_df], ignore_index=True)

        # 年月でソート
        merged_df = merged_df.sort_values(['年', '月', '従業員名'])

        print(f"マージ完了: {len(merged_df)}行")

        return merged_df

    except Exception as e:
        print(f"データマージエラー: {e}")
        print(f"エラー詳細: {traceback.format_exc()}")
        return None


# 業務内容分割関連の関数
def normalize_text(s: str) -> str:
    """Convert fullwidth alphanumeric and symbols to halfwidth."""
    if pd.isna(s):
        return ""
    return unicodedata.normalize('NFKC', str(s))


def extract_parentheses_content(text):
    """
    括弧内の内容を抽出し、括弧外のテキストと分離する（スタックベース実装）。
    入れ子括弧に対応し、最も外側の括弧の内容を1単位として抽出する。
    """
    if not text:
        return "", []

    stack = []
    matches = []
    opening_brackets = {'(': ')', '（': '）', '【': '】'}
    closing_brackets = {')': '(', '）': '（', '】': '【'}

    for i, char in enumerate(text):
        if char in opening_brackets:
            stack.append((i, char))
        elif char in closing_brackets:
            if stack and stack[-1][1] == closing_brackets[char]:
                start_index, _ = stack.pop()
                matches.append((start_index, i))

    if not matches:
        return text, []

    matches.sort(key=lambda x: (x[0], -x[1]))
    top_level_matches = []
    covered_indices = set()

    for start, end in matches:
        current_range_set = set(range(start, end + 1))
        if not current_range_set.intersection(covered_indices):
            top_level_matches.append((start, end))
            covered_indices.update(current_range_set)

    paren_content = [text[start + 1 : end] for start, end in top_level_matches if text[start + 1 : end]]
    indices_to_remove = set().union(*(set(range(start, end + 1)) for start, end in top_level_matches))

    cleaned_buffer = []
    space_added = False

    for i, char in enumerate(text):
        if i not in indices_to_remove:
            cleaned_buffer.append(char)
            space_added = False
        elif not space_added:
            cleaned_buffer.append(' ')
            space_added = True

    cleaned_text = "".join(cleaned_buffer)
    cleaned_text = re.sub(r'\s+', ' ', cleaned_text).strip()
    cleaned_text = re.sub(r"^[()\（\）\[\]【】{}<>《》]+|[()\（\）\[\]【】{}<>《》]+$", '', cleaned_text).strip()

    return cleaned_text, paren_content


def is_special_mixed_pattern(text):
    """特殊な日本語と英語の混在パターンをチェック"""
    if not text or len(text) < 2:
        return False

    jp_chars = re.findall(r'[ぁ-んァ-ヶー一-龠々]', text)
    en_chars = re.findall(r'[A-Za-z]', text)

    if not jp_chars or not en_chars:
        return False
    if re.match(r'^[A-Za-z][ぁ-んァ-ヶー一-龠々]', text):
        return True
    if re.match(r'^[ぁ-んァ-ヶー一-龠々]+[A-Za-z]$', text):
        return True

    return False


def split_english_japanese(text):
    """
    特定の接続記号で繋がっているか、特殊なパターンかをチェックする。
    それ以外の場合、基本的には分割しない。
    """
    if not text:
        return []

    connectors_pattern = r"[-/\uff0f→・･.\uff0e《》?\uff1f⇔ー]"

    if re.search(connectors_pattern, text):
        return [text]
    if is_special_mixed_pattern(text):
        return [text]

    return [text]


def split_tasks(cell_value, user_fields):
    """業務内容セルをタスクに分割"""
    if pd.isna(cell_value):
        return []

    text = normalize_text(str(cell_value))
    main_text, paren_contents = extract_parentheses_content(text)
    initial_parts = re.split(r'[_ 　]+', main_text)

    main_tasks = []
    for part in initial_parts:
        part = part.strip()
        if not part:
            continue

        subparts = split_english_japanese(part)
        for subpart in subparts:
            subpart = subpart.strip()
            if subpart and subpart not in user_fields and subpart not in main_tasks:
                main_tasks.append(subpart)

    paren_tasks = []
    for content in paren_contents:
        content = content.strip()
        if content and content not in paren_tasks:
            paren_tasks.append(content)

    combined_tasks = main_tasks + paren_tasks
    final_filtered_tasks = []
    i = 0

    while i < len(combined_tasks):
        task = combined_tasks[i]
        if task == '会議' and i + 1 < len(combined_tasks) and combined_tasks[i+1] in ('Non-Essential', 'Essential'):
            i += 2
        else:
            final_filtered_tasks.append(task)
            i += 1

    final_tasks = []
    seen_tasks = set()
    punctuation_pattern = r'^[,、.。．:;\'"]+|[,、.。．:;\'"]+$'

    for task in final_filtered_tasks:
        task = re.sub(punctuation_pattern, '', task)
        task = task.strip()
        if task and task not in seen_tasks:
            final_tasks.append(task)
            seen_tasks.add(task)

    return final_tasks


def split_business_content(df):
    """
    データフレーム内の業務内容を分割して業務内容1〜10のカラムに展開
    """
    print("業務内容分割処理開始...")

    # 新しいカラムを準備
    for i in range(1, 11):
        df[f'業務内容{i}'] = ''

    total_rows = len(df)
    processed_rows = 0

    for index, row in df.iterrows():
        # USER_FIELDから重複除外用のリストを作成
        user_fields = []
        for field in ['USER_FIELD_01', 'USER_FIELD_02', 'USER_FIELD_03']:
            if field in row and not pd.isna(row[field]):
                user_field_value = normalize_text(str(row[field]))
                if user_field_value:
                    user_fields.append(user_field_value)

        # 業務内容を分割
        tasks = split_tasks(row['業務内容'], user_fields)

        # 業務内容1〜10に割り当て
        for task_index, task in enumerate(tasks[:10], 1):
            df.at[index, f'業務内容{task_index}'] = task

        # 10を超える場合は新しいカラムを追加
        if len(tasks) > 10:
            for task_index, task in enumerate(tasks[10:], 11):
                col_name = f'業務内容{task_index}'
                if col_name not in df.columns:
                    df[col_name] = ''
                df.at[index, col_name] = task

        processed_rows += 1
        if processed_rows % 1000 == 0:
            print(f"業務内容分割進捗: {processed_rows}/{total_rows}行 ({processed_rows/total_rows*100:.1f}%)")

    print(f"業務内容分割完了: {processed_rows}行処理")

    # 最終的なカラム順序を整理
    base_columns = [
        '年', '月', '従業員名', '作業時間(h)',
        'USER_FIELD_01', 'USER_FIELD_02', 'USER_FIELD_03', 'USER_FIELD_04', 'USER_FIELD_05',
        '第1分類', '第2分類', '第3分類', 'UNIT', 'MODULE', '業務内容'
    ]

    # 業務内容カラムを追加
    task_columns = [col for col in df.columns if col.startswith('業務内容') and col != '業務内容']
    task_columns.sort(key=lambda x: int(re.search(r'\d+', x).group()) if re.search(r'\d+', x) else 0)

    final_columns = base_columns + task_columns

    # 存在するカラムのみを選択
    existing_columns = [col for col in final_columns if col in df.columns]
    df = df[existing_columns]

    return df


def process_multiple_monthly_files(monthly_files, existing_file=None, progress_callback=None):
    """
    複数の月次データファイルを処理して統合工数データを作成

    Args:
        monthly_files: 月次データファイルのリスト（BytesIOオブジェクトまたはファイルパス）
        existing_file: 既存の総工数データファイル（オプション、BytesIOオブジェクトまたはファイルパス）
        progress_callback: 進捗コールバック関数

    Returns:
        処理済みデータフレーム
    """
    try:
        all_monthly_data = []

        # 各月次ファイルを処理
        for i, monthly_file in enumerate(monthly_files):
            if progress_callback:
                progress = 0.1 + (i / len(monthly_files)) * 0.4
                progress_callback(progress, f"月次データ処理中... ({i+1}/{len(monthly_files)})")

            print(f"\n=== 月次データ{i+1}処理開始 ===")
            monthly_data = process_monthly_data(monthly_file)

            if monthly_data is None:
                print(f"月次データ{i+1}の処理に失敗しました")
                continue

            all_monthly_data.append(monthly_data)

        if not all_monthly_data:
            print("処理可能な月次データがありません")
            return None

        # 全ての月次データを結合
        if progress_callback:
            progress_callback(0.5, "月次データ結合中...")

        combined_monthly_data = pd.concat(all_monthly_data, ignore_index=True)
        print(f"\n全月次データ結合完了: {len(combined_monthly_data)}行")

        # 既存データとマージ
        if progress_callback:
            progress_callback(0.6, "既存データとマージ中...")

        merged_data = merge_effort_data(existing_file, combined_monthly_data)

        if merged_data is None:
            print("データマージに失敗しました")
            return None

        # 業務内容分割
        if progress_callback:
            progress_callback(0.8, "業務内容分割中...")

        print("\n=== 業務内容分割開始 ===")
        final_data = split_business_content(merged_data)

        if progress_callback:
            progress_callback(1.0, "処理完了")

        print("\n✅ 全体処理が正常に完了しました！")
        return final_data

    except Exception as e:
        print(f"統合処理エラー: {e}")
        traceback.print_exc()
        return None
