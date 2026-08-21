# modules/analytics.py

from datetime import datetime, timedelta
from modules.storage import get_connection, load_config
from modules.ai_service import logger


def get_overall_stats():
    """전체 통계 요약을 계산한다.
    반환값: dict (총 리뷰수, 분석완료율, 감정분포, 별점분포, 평균별점, 평균감정점수)
    """
    conn = get_connection()
    cursor = conn.cursor()

    total = cursor.execute("SELECT COUNT(*) FROM clean_reviews").fetchone()[0]
    analyzed = cursor.execute("SELECT COUNT(*) FROM clean_reviews WHERE sentiment IS NOT NULL").fetchone()[0]

    sentiment_rows = cursor.execute(
        "SELECT sentiment, COUNT(*) as cnt FROM clean_reviews WHERE sentiment IS NOT NULL GROUP BY sentiment"
    ).fetchall()
    sentiment_dist = {row["sentiment"]: row["cnt"] for row in sentiment_rows}

    rating_rows = cursor.execute(
        "SELECT rating, COUNT(*) as cnt FROM clean_reviews WHERE rating IS NOT NULL GROUP BY rating ORDER BY rating DESC"
    ).fetchall()
    rating_dist = {row["rating"]: row["cnt"] for row in rating_rows}

    avg_rating = cursor.execute("SELECT AVG(rating) FROM clean_reviews WHERE rating IS NOT NULL").fetchone()[0]
    avg_score = cursor.execute("SELECT AVG(sentiment_score) FROM clean_reviews WHERE sentiment_score IS NOT NULL").fetchone()[0]

    conn.close()

    return {
        "total": total,
        "analyzed": analyzed,
        "analyzed_rate": (analyzed / total * 100) if total > 0 else 0,
        "sentiment_dist": sentiment_dist,
        "rating_dist": rating_dist,
        "avg_rating": avg_rating or 0,
        "avg_score": avg_score or 0,
    }


def check_negative_surge_alert():
    """최근 N일 vs 직전 N일의 부정 리뷰 비율을 비교하여 급증 여부를 판단한다.
    데이터 안의 최신 리뷰 작성일을 기준으로 '최근'을 계산한다.

    반환값: dict {
        "triggered": bool (알림 발생 여부),
        "message": str (알림 여부와 무관하게 표시할 상태 메시지),
        "recent_ratio": float, "previous_ratio": float, "diff": float
    } 또는 표본 부족 시 triggered=False, message에 사유 표시
    """
    config = load_config()
    days = config["alert"]["days"]
    threshold_pp = config["alert"]["threshold_pp"]
    min_sample_size = config["alert"]["min_sample_size"]

    conn = get_connection()
    cursor = conn.cursor()

    # 데이터 안에서 가장 최신 리뷰 날짜를 기준점으로 삼음
    latest_row = cursor.execute(
        "SELECT MAX(review_date) as latest FROM clean_reviews WHERE review_date IS NOT NULL"
    ).fetchone()

    if latest_row["latest"] is None:
        conn.close()
        return {"triggered": False, "message": "리뷰 작성일 데이터가 없어 알림 계산 불가"}

    latest_date = datetime.strptime(latest_row["latest"], "%Y-%m-%d")

    recent_start = (latest_date - timedelta(days=days - 1)).strftime("%Y-%m-%d")
    recent_end = latest_date.strftime("%Y-%m-%d")
    previous_end = (latest_date - timedelta(days=days)).strftime("%Y-%m-%d")
    previous_start = (latest_date - timedelta(days=days * 2 - 1)).strftime("%Y-%m-%d")

    def get_ratio(start, end):
        total = cursor.execute(
            "SELECT COUNT(*) FROM clean_reviews WHERE review_date BETWEEN ? AND ? AND sentiment IS NOT NULL",
            (start, end)
        ).fetchone()[0]
        negative = cursor.execute(
            "SELECT COUNT(*) FROM clean_reviews WHERE review_date BETWEEN ? AND ? AND sentiment = 'negative'",
            (start, end)
        ).fetchone()[0]
        return total, negative

    recent_total, recent_negative = get_ratio(recent_start, recent_end)
    previous_total, previous_negative = get_ratio(previous_start, previous_end)

    conn.close()

    if recent_total < min_sample_size:
        logger.warning(f"부정리뷰 급증 알림 생략: 최근 {days}일 표본 {recent_total}건 (최소 {min_sample_size}건 필요)")
        return {
            "triggered": False,
            "message": f"최근 {days}일간 분석된 리뷰가 {recent_total}건으로 표본이 부족하여 알림을 생략합니다 (최소 {min_sample_size}건 필요)"
        }

    recent_ratio = (recent_negative / recent_total * 100) if recent_total > 0 else 0
    previous_ratio = (previous_negative / previous_total * 100) if previous_total > 0 else 0
    diff = recent_ratio - previous_ratio

    if diff >= threshold_pp:
        message = (
            f"⚠️ 경고: 최근 {days}일간 부정 리뷰 비율이 {recent_ratio:.1f}%로, "
            f"직전 {days}일({previous_ratio:.1f}%) 대비 {diff:.1f}%p 급증했습니다!"
        )
        logger.warning(f"부정리뷰 급증 감지: {previous_ratio:.1f}% -> {recent_ratio:.1f}% ({diff:+.1f}%p)")
        return {
            "triggered": True, "message": message,
            "recent_ratio": recent_ratio, "previous_ratio": previous_ratio, "diff": diff,
        }
    else:
        message = (
            f"최근 {days}일간 부정 리뷰 비율: {recent_ratio:.1f}% "
            f"(직전 {days}일 {previous_ratio:.1f}% 대비 {diff:+.1f}%p, 급증 기준 {threshold_pp}%p 미만)"
        )
        return {
            "triggered": False, "message": message,
            "recent_ratio": recent_ratio, "previous_ratio": previous_ratio, "diff": diff,
        }
    