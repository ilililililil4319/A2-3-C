# modules/data_loader.py

import os
import re
import pandas as pd
from datetime import datetime
from modules.storage import get_connection, init_db
from modules.ai_service import logger


# ------------------------------------------------------------
# STEP 4: 파일 로드 (import 단계에서 사용)
# ------------------------------------------------------------

def load_file(file_path):
    """CSV 또는 Excel 파일을 읽어 DataFrame으로 반환한다."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext == ".csv":
        df = pd.read_csv(file_path)
    elif ext in (".xlsx", ".xls"):
        df = pd.read_excel(file_path)
    else:
        raise ValueError(f"지원하지 않는 파일 형식입니다: {ext}")

    return df


def import_to_raw(file_path):
    """파일을 읽어 raw_reviews 테이블에 저장한다.
    반환값: (총 감지 건수, 저장 성공 건수)
    """
    init_db()

    df = load_file(file_path)

    if "review_text" not in df.columns:
        raise ValueError("필수 컬럼 'review_text'가 파일에 없습니다.")

    for col in ["rating", "review_date", "product_name"]:
        if col not in df.columns:
            df[col] = None

    conn = get_connection()
    cursor = conn.cursor()
    imported_at = datetime.now().isoformat()

    saved_count = 0
    for _, row in df.iterrows():
        cursor.execute("""
            INSERT INTO raw_reviews
                (review_text, rating, review_date, product_name, imported_at, source_file)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            None if pd.isna(row["review_text"]) else str(row["review_text"]),
            None if pd.isna(row["rating"]) else str(row["rating"]),
            None if pd.isna(row["review_date"]) else str(row["review_date"]),
            None if pd.isna(row["product_name"]) else str(row["product_name"]),
            imported_at,
            file_path,
        ))
        saved_count += 1

    conn.commit()
    conn.close()

    logger.info(f"파일 가져오기 완료: {file_path}, 총 {len(df)}건 중 {saved_count}건 raw 저장")

    return len(df), saved_count


# ------------------------------------------------------------
# STEP 5: 정제 규칙 함수들 (clean 단계에서 사용)
# ------------------------------------------------------------

def normalize_text(text):
    """텍스트 정규화: 앞뒤 공백 제거, 연속 공백/줄바꿈을 공백 하나로 통일."""
    if text is None:
        return None
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def validate_rating(rating_raw):
    """별점을 1~5 범위의 정수로 검증한다.
    범위를 벗어나거나 숫자가 아니면 None을 반환한다 (선택 필드이므로 에러 대신 None 처리).
    """
    if rating_raw is None:
        return None
    try:
        rating = int(float(rating_raw))
    except (ValueError, TypeError):
        return None

    if 1 <= rating <= 5:
        return rating
    return None


def normalize_date(date_raw):
    """다양한 날짜 형식(YYYY-MM-DD, YYYY/MM/DD 등)을 YYYY-MM-DD로 통일한다.
    파싱 실패 시 None을 반환한다.
    """
    if date_raw is None:
        return None

    date_str = str(date_raw).strip()
    possible_formats = ["%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y%m%d"]

    for fmt in possible_formats:
        try:
            parsed = datetime.strptime(date_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def make_dedup_key(review_text, review_date, product_name):
    """중복 판단 기준 키 생성: 정규화된 텍스트 + 날짜 + 제품명을 결합.
    셋 중 하나라도 다르면 다른 리뷰로 취급한다.
    """
    text_part = review_text or ""
    date_part = review_date or ""
    product_part = product_name or ""
    return f"{text_part}||{date_part}||{product_part}"


def clean_reviews(min_length=5, duplicate_mode="skip"):
    """raw_reviews의 모든 레코드를 정제 규칙에 따라 검증/정규화한 뒤
    clean_reviews 테이블에 저장한다.

    반환값: dict 형태의 처리 통계
    """
    conn = get_connection()
    cursor = conn.cursor()

    raw_rows = cursor.execute("SELECT * FROM raw_reviews").fetchall()

    stats = {
        "total": len(raw_rows),
        "valid": 0,
        "invalid_required": 0,
        "invalid_short": 0,
        "duplicate_skipped": 0,
        "duplicate_upserted": 0,
        "saved": 0,
    }

    cleaned_at = datetime.now().isoformat()

    for row in raw_rows:
        text = normalize_text(row["review_text"])
        if not text:
            stats["invalid_required"] += 1
            continue

        if len(text) < min_length:
            stats["invalid_short"] += 1
            continue

        rating = validate_rating(row["rating"])
        review_date = normalize_date(row["review_date"])
        product_name = normalize_text(row["product_name"])

        stats["valid"] += 1

        dedup_key = make_dedup_key(text, review_date, product_name)

        existing = cursor.execute(
            "SELECT id FROM clean_reviews WHERE dedup_key = ?", (dedup_key,)
        ).fetchone()

        if existing:
            if duplicate_mode == "skip":
                stats["duplicate_skipped"] += 1
                continue
            elif duplicate_mode == "upsert":
                cursor.execute("""
                    UPDATE clean_reviews
                    SET raw_id = ?, review_text = ?, rating = ?, review_date = ?,
                        product_name = ?, cleaned_at = ?
                    WHERE dedup_key = ?
                """, (row["id"], text, rating, review_date, product_name, cleaned_at, dedup_key))
                stats["duplicate_upserted"] += 1
                stats["saved"] += 1
                continue

        cursor.execute("""
            INSERT INTO clean_reviews
                (raw_id, review_text, rating, review_date, product_name, dedup_key, cleaned_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (row["id"], text, rating, review_date, product_name, dedup_key, cleaned_at))
        stats["saved"] += 1

    conn.commit()
    conn.close()

    if stats["invalid_required"] > 0 or stats["invalid_short"] > 0:
        logger.warning(
            f"정제 중 {stats['invalid_required']}건 필수필드누락, "
            f"{stats['invalid_short']}건 짧은리뷰로 제외됨"
        )
    logger.info(f"정제 완료: raw {stats['total']}건 중 clean {stats['saved']}건 저장 (모드: {duplicate_mode})")

    return stats


# ------------------------------------------------------------
# STEP 11: 데이터 내보내기
# ------------------------------------------------------------

def export_reviews(output_format="csv", sentiment=None, rating_min=None, output_dir="output"):
    """clean_reviews를 조건에 맞게 필터링하여 파일로 내보낸다.

    output_format: "csv" / "jsonl" / "excel"
    반환값: (저장된 파일 경로, 내보낸 건수)
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    if sentiment:
        conditions.append("sentiment = ?")
        params.append(sentiment)
    if rating_min:
        conditions.append("rating >= ?")
        params.append(rating_min)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM clean_reviews {where_clause}"
    rows = cursor.execute(query, params).fetchall()
    conn.close()

    data = [dict(row) for row in rows]
    df = pd.DataFrame(data)

    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if output_format == "csv":
        output_path = os.path.join(output_dir, f"export_{timestamp}.csv")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    elif output_format == "jsonl":
        output_path = os.path.join(output_dir, f"export_{timestamp}.jsonl")
        df.to_json(output_path, orient="records", lines=True, force_ascii=False)
    elif output_format == "excel":
        output_path = os.path.join(output_dir, f"export_{timestamp}.xlsx")
        df.to_excel(output_path, index=False)
    else:
        raise ValueError(f"지원하지 않는 포맷입니다: {output_format}")

    logger.info(f"내보내기 완료: {output_format} 형식, {len(data)}건, 경로={output_path}")

    return output_path, len(data)
