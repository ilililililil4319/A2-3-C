# modules/visualize.py

import os
import matplotlib
matplotlib.use("Agg")  # GUI 없이 파일로만 저장하는 백엔드 (서버/CLI 환경에 적합)
import matplotlib.pyplot as plt
from modules.storage import get_connection, load_config


def setup_korean_font():
    """config.json에 설정된 폰트로 matplotlib 한글 폰트를 적용한다."""
    config = load_config()
    font_family = config["visualization"]["font_family"]

    plt.rcParams["font.family"] = font_family
    plt.rcParams["axes.unicode_minus"] = False  # 마이너스 기호 깨짐 방지


def get_output_dir():
    config = load_config()
    output_dir = config["visualization"]["output_dir"]
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def draw_sentiment_distribution():
    """감정 분포 파이 차트를 그려 PNG로 저장한다."""
    setup_korean_font()
    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute(
        "SELECT sentiment, COUNT(*) as cnt FROM clean_reviews WHERE sentiment IS NOT NULL GROUP BY sentiment"
    ).fetchall()
    conn.close()

    labels_map = {"positive": "긍정", "negative": "부정", "neutral": "중립"}
    colors_map = {"positive": "#4CAF50", "negative": "#F44336", "neutral": "#9E9E9E"}

    labels = [labels_map[row["sentiment"]] for row in rows]
    values = [row["cnt"] for row in rows]
    colors = [colors_map[row["sentiment"]] for row in rows]

    plt.figure(figsize=(6, 6))
    plt.pie(values, labels=labels, autopct="%1.1f%%", colors=colors, startangle=90)
    plt.title("감정 분포")

    output_path = os.path.join(get_output_dir(), "sentiment_distribution.png")
    plt.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close()

    return output_path


def draw_sentiment_trend():
    """날짜별 감정 추이 선 그래프를 그려 PNG로 저장한다."""
    setup_korean_font()
    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT review_date, sentiment, COUNT(*) as cnt
        FROM clean_reviews
        WHERE review_date IS NOT NULL AND sentiment IS NOT NULL
        GROUP BY review_date, sentiment
        ORDER BY review_date
    """).fetchall()
    conn.close()

    # 날짜별로 긍정/부정/중립 건수를 정리
    date_data = {}
    for row in rows:
        date = row["review_date"]
        if date not in date_data:
            date_data[date] = {"positive": 0, "negative": 0, "neutral": 0}
        date_data[date][row["sentiment"]] = row["cnt"]

    dates = sorted(date_data.keys())
    positive_counts = [date_data[d]["positive"] for d in dates]
    negative_counts = [date_data[d]["negative"] for d in dates]
    neutral_counts = [date_data[d]["neutral"] for d in dates]

    plt.figure(figsize=(12, 6))
    plt.plot(dates, positive_counts, marker="o", label="긍정", color="#4CAF50")
    plt.plot(dates, negative_counts, marker="o", label="부정", color="#F44336")
    plt.plot(dates, neutral_counts, marker="o", label="중립", color="#9E9E9E")

    plt.title("시간별 감정 추이")
    plt.xlabel("날짜")
    plt.ylabel("리뷰 건수")
    plt.xticks(rotation=45, ha="right")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()

    output_path = os.path.join(get_output_dir(), "sentiment_trend.png")
    plt.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close()

    return output_path


def draw_rating_sentiment_matrix():
    """별점별 감정 분포를 누적 막대 그래프로 그려 PNG로 저장한다."""
    setup_korean_font()
    conn = get_connection()
    cursor = conn.cursor()

    rows = cursor.execute("""
        SELECT rating, sentiment, COUNT(*) as cnt
        FROM clean_reviews
        WHERE rating IS NOT NULL AND sentiment IS NOT NULL
        GROUP BY rating, sentiment
    """).fetchall()
    conn.close()

    rating_data = {r: {"positive": 0, "negative": 0, "neutral": 0} for r in range(1, 6)}
    for row in rows:
        rating_data[row["rating"]][row["sentiment"]] = row["cnt"]

    ratings = list(range(1, 6))
    positive_counts = [rating_data[r]["positive"] for r in ratings]
    negative_counts = [rating_data[r]["negative"] for r in ratings]
    neutral_counts = [rating_data[r]["neutral"] for r in ratings]

    x_labels = [f"{r}점" for r in ratings]

    plt.figure(figsize=(8, 6))
    plt.bar(x_labels, positive_counts, label="긍정", color="#4CAF50")
    plt.bar(x_labels, negative_counts, bottom=positive_counts, label="부정", color="#F44336")
    bottom_neutral = [p + n for p, n in zip(positive_counts, negative_counts)]
    plt.bar(x_labels, neutral_counts, bottom=bottom_neutral, label="중립", color="#9E9E9E")

    plt.title("별점별 감정 분포")
    plt.xlabel("별점")
    plt.ylabel("리뷰 건수")
    plt.legend()
    plt.tight_layout()

    output_path = os.path.join(get_output_dir(), "rating_sentiment_matrix.png")
    plt.savefig(output_path, dpi=100, bbox_inches="tight")
    plt.close()

    return output_path


def generate_all_charts():
    """3종 차트를 모두 생성하고 저장된 경로 리스트를 반환한다."""
    paths = [
        draw_sentiment_distribution(),
        draw_sentiment_trend(),
        draw_rating_sentiment_matrix(),
    ]
    return paths
