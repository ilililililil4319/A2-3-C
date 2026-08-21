# modules/storage.py

import sqlite3
import json
import os

def load_config(config_path="config.json"):
    """config.json을 읽어서 딕셔너리로 반환한다."""
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_connection(db_path=None):
    """SQLite 데이터베이스 연결을 반환한다.
    db_path를 지정하지 않으면 config.json의 storage.db_path를 사용한다.
    """
    if db_path is None:
        config = load_config()
        db_path = config["storage"]["db_path"]

    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 컬럼명으로 접근 가능하게 설정
    return conn


def init_db(db_path=None):
    """raw_reviews, clean_reviews, extractions 테이블을 생성한다.
    이미 존재하면 아무 동작도 하지 않는다 (IF NOT EXISTS).
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()

    # 1) raw_reviews: import 단계에서 원본 그대로 저장
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS raw_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_text TEXT,
            rating TEXT,
            review_date TEXT,
            product_name TEXT,
            imported_at TEXT NOT NULL,
            source_file TEXT
        )
    """)

    # 2) clean_reviews: clean 단계에서 검증/정규화된 데이터 저장
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS clean_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            raw_id INTEGER,
            review_text TEXT NOT NULL,
            rating INTEGER,
            review_date TEXT,
            product_name TEXT,
            dedup_key TEXT NOT NULL,
            cleaned_at TEXT NOT NULL,

            sentiment TEXT,
            sentiment_score REAL,
            analyzed_at TEXT,

            FOREIGN KEY (raw_id) REFERENCES raw_reviews (id)
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_clean_dedup
        ON clean_reviews (dedup_key)
    """)

    # 3) extractions: extract 단계에서 생성되는 종합 분석 결과 저장
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS extractions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filter_condition TEXT,
            review_count INTEGER,
            positive_keywords TEXT,
            negative_keywords TEXT,
            summary TEXT,
            improvement_suggestions TEXT,
            created_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()
    print("[INFO] 데이터베이스 초기화 완료 (raw_reviews, clean_reviews, extractions 테이블 생성)")


# ------------------------------------------------------------
# STEP 8: 조회 기능 (list, show)
# ------------------------------------------------------------

def list_reviews(sentiment=None, rating=None, date_from=None, date_to=None,
                  page=1, size=10, sort_by="review_date", order="desc"):
    """조건에 맞는 리뷰 목록을 페이지네이션하여 조회한다.

    반환값: dict {"items": [...], "total": 전체건수, "page": 현재페이지, "total_pages": 전체페이지수}
    """
    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []

    if sentiment:
        conditions.append("sentiment = ?")
        params.append(sentiment)
    if rating:
        conditions.append("rating = ?")
        params.append(rating)
    if date_from:
        conditions.append("review_date >= ?")
        params.append(date_from)
    if date_to:
        conditions.append("review_date <= ?")
        params.append(date_to)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    total = cursor.execute(f"SELECT COUNT(*) FROM clean_reviews {where_clause}", params).fetchone()[0]

    # 정렬 컬럼 화이트리스트 검증 (SQL 인젝션 방지)
    allowed_sort_columns = ["review_date", "rating", "sentiment_score", "id"]
    if sort_by not in allowed_sort_columns:
        sort_by = "review_date"
    order = "ASC" if order.lower() == "asc" else "DESC"

    offset = (page - 1) * size
    query = f"""
        SELECT * FROM clean_reviews {where_clause}
        ORDER BY {sort_by} {order}
        LIMIT ? OFFSET ?
    """
    items = cursor.execute(query, params + [size, offset]).fetchall()

    conn.close()

    total_pages = (total + size - 1) // size if total > 0 else 1

    return {
        "items": items,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


def get_review_by_id(review_id):
    """특정 리뷰 하나의 상세 정보를 조회한다."""
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("SELECT * FROM clean_reviews WHERE id = ?", (review_id,)).fetchone()
    conn.close()
    return row


if __name__ == "__main__":
    # 이 파일을 직접 실행하면 DB 초기화만 테스트할 수 있도록 함
    init_db()
    