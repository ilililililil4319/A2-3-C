# modules/report.py

import os
import json
from datetime import datetime
from modules.storage import get_connection, load_config
from modules.analytics import get_overall_stats, check_negative_surge_alert
from modules.ai_service import logger


def get_latest_extraction(sentiment_filter):
    """extractions 테이블에서 특정 감정 조건의 가장 최근 추출 결과를 가져온다.
    없으면 None을 반환한다.
    """
    conn = get_connection()
    cursor = conn.cursor()
    row = cursor.execute("""
        SELECT * FROM extractions
        WHERE filter_condition LIKE ?
        ORDER BY created_at DESC
        LIMIT 1
    """, (f"%sentiment={sentiment_filter}%",)).fetchone()
    conn.close()

    if row is None:
        return None

    return {
        "positive_keywords": json.loads(row["positive_keywords"]),
        "negative_keywords": json.loads(row["negative_keywords"]),
        "summary": row["summary"],
        "improvement_suggestions": json.loads(row["improvement_suggestions"]),
        "review_count": row["review_count"],
    }


def compute_keyword_top_n(keywords, top_n=5):
    """키워드 목록을 받아, 전체 clean_reviews 원문에서 각 키워드가 등장한 횟수를 세어
    상위 N개를 (키워드, 횟수) 튜플 리스트로 반환한다.
    """
    if not keywords:
        return []

    conn = get_connection()
    cursor = conn.cursor()
    texts = [row["review_text"] for row in cursor.execute("SELECT review_text FROM clean_reviews").fetchall()]
    conn.close()

    counts = {}
    for kw in keywords:
        counts[kw] = sum(1 for t in texts if kw in t)

    ranked = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_n]


def build_report_text():
    """전체 리포트를 문자열로 구성하여 반환한다."""
    stats = get_overall_stats()
    alert = check_negative_surge_alert()

    positive_extraction = get_latest_extraction("positive")
    negative_extraction = get_latest_extraction("negative")

    positive_top = compute_keyword_top_n(
        positive_extraction["positive_keywords"] if positive_extraction else []
    )
    negative_top = compute_keyword_top_n(
        negative_extraction["negative_keywords"] if negative_extraction else []
    )

    lines = []
    lines.append("=" * 55)
    lines.append(" 고객 리뷰 감정 분석 대시보드")
    lines.append(f" 생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 55)
    lines.append("")

    # 1) 핵심 지표 (품질 지표)
    lines.append("[핵심 지표]")
    positive_count = stats["sentiment_dist"].get("positive", 0)
    positive_rate = (positive_count / stats["analyzed"] * 100) if stats["analyzed"] > 0 else 0
    lines.append(f"- 총 리뷰 수: {stats['total']}건")
    lines.append(f"- 분석 완료율: {stats['analyzed_rate']:.1f}%")
    lines.append(f"- 긍정 비율: {positive_rate:.1f}%")
    lines.append(f"- 평균 별점: {stats['avg_rating']:.2f}")
    lines.append(f"- 평균 감정 점수: {stats['avg_score']:.2f}")
    lines.append("")

    # 2) TOP N 긍정/부정 키워드
    lines.append("[TOP 5 긍정 키워드]")
    if positive_top:
        for i, (kw, cnt) in enumerate(positive_top, start=1):
            lines.append(f"{i}. {kw} ({cnt}회)")
    else:
        lines.append("(추출 결과 없음 - 'python main.py extract --sentiment positive' 먼저 실행 필요)")
    lines.append("")

    lines.append("[TOP 5 부정 키워드]")
    if negative_top:
        for i, (kw, cnt) in enumerate(negative_top, start=1):
            lines.append(f"{i}. {kw} ({cnt}회)")
    else:
        lines.append("(추출 결과 없음 - 'python main.py extract --sentiment negative' 먼저 실행 필요)")
    lines.append("")

    # 3) AI 인사이트 요약 (부정 리뷰 추출 결과의 요약/개선제안 활용)
    lines.append("[AI 인사이트 요약]")
    if negative_extraction:
        lines.append(negative_extraction["summary"])
        lines.append("")
        lines.append("[개선 제안]")
        for suggestion in negative_extraction["improvement_suggestions"]:
            lines.append(f"- {suggestion}")
    else:
        lines.append("(추출 결과 없음 - extract 명령을 먼저 실행해 주세요)")
    lines.append("")

    # 4) 부정 리뷰 급증 알림
    lines.append("[부정 리뷰 급증 알림]")
    lines.append(alert["message"])
    lines.append("")

    # 5) 생성된 차트 파일
    config = load_config()
    chart_dir = config["visualization"]["output_dir"]
    lines.append("[생성된 차트 파일]")
    lines.append(f"- {chart_dir}/sentiment_distribution.png")
    lines.append(f"- {chart_dir}/sentiment_trend.png")
    lines.append(f"- {chart_dir}/rating_sentiment_matrix.png")
    lines.append("")
    lines.append("=" * 55)

    return "\n".join(lines)


def save_report(report_text):
    """리포트를 TXT와 MD 파일로 저장하고, 저장된 경로 리스트를 반환한다."""
    config = load_config()
    output_dir = config["report"]["output_dir"]
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    txt_path = os.path.join(output_dir, f"report_{timestamp}.txt")
    md_path = os.path.join(output_dir, f"report_{timestamp}.md")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("```\n" + report_text + "\n```")

    logger.info(f"리포트 생성 완료: {txt_path}, {md_path}")

    return [txt_path, md_path]
