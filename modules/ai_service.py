# modules/ai_service.py

import json
import os
import logging
from datetime import datetime
from openai import OpenAI
from modules.storage import get_connection, load_config


def setup_logger():
    """logs/app.log에 INFO 이상 레벨 로그를 기록하는 로거를 설정한다."""
    logger = logging.getLogger("review_dashboard")
    if logger.handlers:
        # 이미 설정된 경우 중복 설정 방지
        return logger

    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


logger = setup_logger()


def get_ai_client():
    """config.json에 지정된 환경변수 이름으로 API 키를 읽어 OpenAI 클라이언트를 생성한다."""
    config = load_config()
    api_key_env = config["api"]["api_key_env"]
    api_key = os.environ.get(api_key_env)

    if not api_key:
        raise ValueError(f"환경변수 '{api_key_env}'가 설정되어 있지 않습니다.")

    return OpenAI(api_key=api_key)


# ------------------------------------------------------------
# STEP 6: 개별 리뷰 감정 분석
# ------------------------------------------------------------

def analyze_sentiment(client, model, review_text):
    """리뷰 텍스트 하나를 AI에게 보내 감정과 신뢰도 점수를 받아온다.
    반환값: {"sentiment": "positive"/"negative"/"neutral", "score": 0.0~1.0}
    """
    prompt = f"""다음은 온라인 쇼핑몰에서 판매하는 욕실 틈새 청소솔에 대한 고객 리뷰입니다.
이 리뷰의 감정을 분석해주세요.

리뷰: "{review_text}"

반드시 아래 JSON 형식으로만 응답하세요. 다른 설명이나 문장은 절대 추가하지 마세요.
{{"sentiment": "positive 또는 negative 또는 neutral 중 하나", "score": 0.0에서 1.0 사이의 신뢰도 숫자}}
"""

    response = client.chat.completions.create(
        model=model,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content.strip()
    result = json.loads(raw_text)

    sentiment = result["sentiment"]
    score = float(result["score"])

    if sentiment not in ("positive", "negative", "neutral"):
        raise ValueError(f"예상치 못한 sentiment 값: {sentiment}")
    if not (0.0 <= score <= 1.0):
        raise ValueError(f"score 범위 초과: {score}")

    return {"sentiment": sentiment, "score": score}


def run_analysis(target="unanalyzed", review_id=None, limit=None):
    """clean_reviews를 대상으로 감정분석을 실행하고 결과를 저장한다.

    target: "all" / "unanalyzed" / "id"
    review_id: target="id"일 때 사용할 리뷰 ID
    limit: 분석할 최대 건수 (None이면 제한 없음)

    반환값: dict {"total": 대상건수, "success": 성공건수, "failed": 실패건수}
    """
    config = load_config()
    model = config["api"]["model"]
    client = get_ai_client()

    conn = get_connection()
    cursor = conn.cursor()

    if target == "id":
        rows = cursor.execute(
            "SELECT * FROM clean_reviews WHERE id = ?", (review_id,)
        ).fetchall()
    elif target == "all":
        rows = cursor.execute("SELECT * FROM clean_reviews").fetchall()
    else:  # unanalyzed (기본값)
        rows = cursor.execute(
            "SELECT * FROM clean_reviews WHERE sentiment IS NULL"
        ).fetchall()

    if limit:
        rows = rows[:limit]

    stats = {"total": len(rows), "success": 0, "failed": 0}

    for i, row in enumerate(rows, start=1):
        try:
            result = analyze_sentiment(client, model, row["review_text"])

            cursor.execute("""
                UPDATE clean_reviews
                SET sentiment = ?, sentiment_score = ?, analyzed_at = ?
                WHERE id = ?
            """, (result["sentiment"], result["score"], datetime.now().isoformat(), row["id"]))
            conn.commit()

            print(f"[INFO] [{i}/{len(rows)}] ID={row['id']} 분석 완료: {result['sentiment']} ({result['score']:.2f})")
            stats["success"] += 1

        except Exception as e:
            logger.error(f"리뷰 ID={row['id']} 감정분석 실패: {e}")
            print(f"[ERROR] [{i}/{len(rows)}] ID={row['id']} 분석 실패: {e}")
            stats["failed"] += 1
            continue

    conn.close()
    return stats


# ------------------------------------------------------------
# STEP 7: 여러 리뷰 종합 - 키워드/요약/개선제안 추출
# ------------------------------------------------------------

def extract_insights(client, model, reviews, filter_desc):
    """여러 리뷰를 종합하여 AI에게 키워드/요약/개선제안을 요청한다.

    reviews: clean_reviews에서 가져온 row 리스트
    filter_desc: 이 추출이 어떤 조건으로 이루어졌는지 설명하는 문자열 (예: "sentiment=negative")

    반환값: dict {
        "positive_keywords": [...],
        "negative_keywords": [...],
        "summary": "...",
        "improvement_suggestions": [...]
    }
    """
    review_lines = []
    for i, r in enumerate(reviews, start=1):
        rating_part = f"(별점 {r['rating']})" if r["rating"] else ""
        review_lines.append(f"{i}. {r['review_text']} {rating_part}")
    reviews_text = "\n".join(review_lines)

    prompt = f"""다음은 온라인 쇼핑몰에서 판매하는 욕실 틈새 청소솔에 대한 고객 리뷰 {len(reviews)}건입니다.
조건: {filter_desc}

리뷰 목록:
{reviews_text}

위 리뷰들을 종합 분석하여 아래 JSON 형식으로만 응답하세요. 다른 설명이나 문장은 절대 추가하지 마세요.
{{
  "positive_keywords": ["긍정 키워드 최대 5개 문자열 리스트, 긍정 리뷰가 없으면 빈 리스트"],
  "negative_keywords": ["부정 키워드 최대 5개 문자열 리스트, 부정 리뷰가 없으면 빈 리스트"],
  "summary": "전체 리뷰 경향을 2~3문장으로 요약한 문자열",
  "improvement_suggestions": ["셀러가 취할 수 있는 구체적 개선 제안 최대 3개 문자열 리스트"]
}}
"""

    response = client.chat.completions.create(
        model=model,
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content.strip()
    result = json.loads(raw_text)

    return {
        "positive_keywords": result.get("positive_keywords", []),
        "negative_keywords": result.get("negative_keywords", []),
        "summary": result.get("summary", ""),
        "improvement_suggestions": result.get("improvement_suggestions", []),
    }


def run_extraction(sentiment=None, date_from=None, date_to=None, product=None):
    """조건에 맞는 clean_reviews를 모아 AI 추출을 실행하고 extractions 테이블에 저장한다.

    반환값: dict (추출 결과 + review_count + filter_desc)
    """
    config = load_config()
    model = config["api"]["model"]
    client = get_ai_client()

    conn = get_connection()
    cursor = conn.cursor()

    conditions = []
    params = []
    filter_parts = []

    if sentiment:
        conditions.append("sentiment = ?")
        params.append(sentiment)
        filter_parts.append(f"sentiment={sentiment}")

    if date_from:
        conditions.append("review_date >= ?")
        params.append(date_from)
        filter_parts.append(f"date_from={date_from}")

    if date_to:
        conditions.append("review_date <= ?")
        params.append(date_to)
        filter_parts.append(f"date_to={date_to}")

    if product:
        conditions.append("product_name = ?")
        params.append(product)
        filter_parts.append(f"product={product}")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    filter_desc = ", ".join(filter_parts) if filter_parts else "전체 리뷰"

    query = f"SELECT * FROM clean_reviews {where_clause}"
    reviews = cursor.execute(query, params).fetchall()

    if not reviews:
        conn.close()
        raise ValueError("조건에 맞는 리뷰가 없습니다.")

    result = extract_insights(client, model, reviews, filter_desc)

    cursor.execute("""
        INSERT INTO extractions
            (filter_condition, review_count, positive_keywords, negative_keywords,
             summary, improvement_suggestions, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        filter_desc,
        len(reviews),
        json.dumps(result["positive_keywords"], ensure_ascii=False),
        json.dumps(result["negative_keywords"], ensure_ascii=False),
        result["summary"],
        json.dumps(result["improvement_suggestions"], ensure_ascii=False),
        datetime.now().isoformat(),
    ))
    conn.commit()
    conn.close()

    result["review_count"] = len(reviews)
    result["filter_desc"] = filter_desc
    return result
