# main.py

import argparse
import json
from modules.data_loader import import_to_raw, clean_reviews, export_reviews
from modules.ai_service import run_analysis, run_extraction
from modules.storage import list_reviews, get_review_by_id
from modules.analytics import get_overall_stats, check_negative_surge_alert
from modules.visualize import generate_all_charts
from modules.report import build_report_text, save_report


def load_config(config_path="config.json"):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------
# 서브커맨드별 실행 함수
# ------------------------------------------------------------

def cmd_import(args):
    total, saved = import_to_raw(args.file)
    print(f"[INFO] 파일 로드: {args.file}")
    print(f"[INFO] 총 {total}건 감지, raw 저장소에 {saved}건 저장 완료")


def cmd_clean(args):
    config = load_config()
    min_length = config["clean_rules"]["min_review_length"]
    duplicate_mode = args.mode or config["import_policy"]["duplicate_mode"]

    stats = clean_reviews(min_length=min_length, duplicate_mode=duplicate_mode)

    print(f"[INFO] 정제 대상(raw): {stats['total']}건")
    print(f"[INFO] 정제 통과: {stats['valid']}건")
    print(f"[INFO] 필수 필드 검증 실패(빈 리뷰): {stats['invalid_required']}건")
    print(f"[INFO] 짧은 리뷰 필터링: {stats['invalid_short']}건")
    print(f"[INFO] 중복 skip: {stats['duplicate_skipped']}건")
    print(f"[INFO] 중복 upsert(갱신): {stats['duplicate_upserted']}건")
    print(f"[INFO] clean 저장소 최종 저장/갱신: {stats['saved']}건 (모드: {duplicate_mode})")


def cmd_analyze(args):
    if args.id is not None:
        target, review_id = "id", args.id
    elif args.all:
        target, review_id = "all", None
    else:
        target, review_id = "unanalyzed", None

    stats = run_analysis(target=target, review_id=review_id, limit=args.limit)

    print(f"[INFO] 분석 대상: {stats['total']}건")
    print(f"[INFO] 분석 완료: {stats['success']}건 성공, {stats['failed']}건 실패")


def cmd_extract(args):
    result = run_extraction(
        sentiment=args.sentiment,
        date_from=args.date_from,
        date_to=args.date_to,
        product=args.product,
    )

    print(f"[INFO] 추출 대상: {result['filter_desc']} {result['review_count']}건")
    print(f"[INFO] AI 분석 요청 중...")
    print(f"[INFO] 추출 완료\n")

    print("=== 리뷰 키워드 분석 ===")
    print(f"[긍정 키워드]\n{', '.join(result['positive_keywords']) if result['positive_keywords'] else '없음'}\n")
    print(f"[부정 키워드]\n{', '.join(result['negative_keywords']) if result['negative_keywords'] else '없음'}\n")
    print(f"[전체 요약]\n{result['summary']}\n")
    print(f"[개선 제안]")
    for suggestion in result['improvement_suggestions']:
        print(f"- {suggestion}")


def cmd_list(args):
    result = list_reviews(
        sentiment=args.sentiment,
        rating=args.rating,
        date_from=args.date_from,
        date_to=args.date_to,
        page=args.page,
        size=args.size,
        sort_by=args.sort_by,
        order=args.order,
    )

    filter_desc = args.sentiment or "전체"
    print(f"=== 리뷰 목록 (감정: {filter_desc}, {result['page']}/{result['total_pages']} 페이지) ===")

    for row in result["items"]:
        stars = "★" * (row["rating"] or 0) + "☆" * (5 - (row["rating"] or 0))
        sentiment_part = f"{row['sentiment']} ({row['sentiment_score']:.2f})" if row["sentiment"] else "미분석"
        text_preview = row["review_text"][:20] + ("..." if len(row["review_text"]) > 20 else "")
        print(f"[{row['id']}] {stars} | {row['review_date'] or '날짜없음'} | {text_preview} | {sentiment_part}")

    print(f"\n총 {result['total']}건")


def cmd_show(args):
    row = get_review_by_id(args.id)

    if row is None:
        print(f"[ERROR] ID={args.id} 리뷰를 찾을 수 없습니다.")
        return

    stars = "★" * (row["rating"] or 0) + "☆" * (5 - (row["rating"] or 0))
    print(f"=== 리뷰 상세 (ID={row['id']}) ===")
    print(f"제품명   : {row['product_name'] or '정보없음'}")
    print(f"별점     : {stars}")
    print(f"작성일   : {row['review_date'] or '정보없음'}")
    print(f"원문     : {row['review_text']}")
    print(f"감정분석 : {row['sentiment'] or '미분석'}", end="")
    if row["sentiment_score"] is not None:
        print(f" (신뢰도 {row['sentiment_score']:.2f})")
    else:
        print()
    print(f"분석일시 : {row['analyzed_at'] or '-'}")


def cmd_stats(args):
    stats = get_overall_stats()

    print("=== 리뷰 분석 통계 ===")
    print(f"총 리뷰 수: {stats['total']}건")
    print(f"분석 완료: {stats['analyzed']}건 ({stats['analyzed_rate']:.1f}%)\n")

    print("[감정 분포]")
    labels = {"positive": "긍정", "negative": "부정", "neutral": "중립"}
    for key in ["positive", "neutral", "negative"]:
        count = stats["sentiment_dist"].get(key, 0)
        pct = (count / stats["analyzed"] * 100) if stats["analyzed"] > 0 else 0
        print(f"- {labels[key]}: {count}건 ({pct:.1f}%)")

    print("\n[별점 분포]")
    for rating in [5, 4, 3, 2, 1]:
        count = stats["rating_dist"].get(rating, 0)
        rated_total = sum(stats["rating_dist"].values())
        pct = (count / rated_total * 100) if rated_total > 0 else 0
        stars = "★" * rating + "☆" * (5 - rating)
        print(f"- {stars}: {count}건 ({pct:.1f}%)")

    print(f"\n평균 별점: {stats['avg_rating']:.2f}")
    print(f"평균 감정 점수: {stats['avg_score']:.2f}")

    alert = check_negative_surge_alert()
    print(f"\n[부정 리뷰 급증 알림]")
    print(alert["message"])


def cmd_dashboard(args):
    print("[INFO] 대시보드 차트 생성 중...")
    chart_paths = generate_all_charts()
    print("[INFO] 차트 생성 완료")
    for path in chart_paths:
        print(f"- {path}")

    print("\n[INFO] 리포트 생성 중...")
    report_text = build_report_text()
    report_paths = save_report(report_text)

    print("\n" + report_text)

    print("\n[INFO] 리포트 파일 저장 완료")
    for path in report_paths:
        print(f"- {path}")


def cmd_export(args):
    output_path, count = export_reviews(
        output_format=args.format,
        sentiment=args.sentiment,
        rating_min=args.rating_min,
    )
    print(f"[INFO] 내보내기 완료: {count}건")
    print(f"[INFO] 저장 위치: {output_path}")


# ------------------------------------------------------------
# argparse 서브커맨드 구성
# ------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="AI 기반 고객 리뷰 감정 분석 대시보드 CLI"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # import 서브커맨드
    import_parser = subparsers.add_parser("import", help="리뷰 파일을 raw 저장소로 가져오기")
    import_parser.add_argument("--file", required=True, help="CSV 또는 Excel 파일 경로")
    import_parser.set_defaults(func=cmd_import)

    # clean 서브커맨드
    clean_parser = subparsers.add_parser("clean", help="raw 데이터를 정제하여 clean 저장소에 저장")
    clean_parser.add_argument(
        "--mode", choices=["skip", "upsert"], default=None,
        help="중복 처리 방식 (지정하지 않으면 config.json 기본값 사용)"
    )
    clean_parser.set_defaults(func=cmd_clean)

    # analyze 서브커맨드
    analyze_parser = subparsers.add_parser("analyze", help="AI 감정 분석 실행")
    analyze_parser.add_argument("--all", action="store_true", help="전체 리뷰 재분석")
    analyze_parser.add_argument("--id", type=int, default=None, help="특정 리뷰 ID만 분석")
    analyze_parser.add_argument("--unanalyzed", action="store_true", help="미분석 리뷰만 분석 (기본값)")
    analyze_parser.add_argument("--limit", type=int, default=None, help="분석할 최대 건수")
    analyze_parser.set_defaults(func=cmd_analyze)

    # extract 서브커맨드
    extract_parser = subparsers.add_parser("extract", help="AI 키워드/요약 추출")
    extract_parser.add_argument("--sentiment", choices=["positive", "negative", "neutral"], default=None, help="감정 조건 필터")
    extract_parser.add_argument("--date-from", default=None, help="시작일 (YYYY-MM-DD)")
    extract_parser.add_argument("--date-to", default=None, help="종료일 (YYYY-MM-DD)")
    extract_parser.add_argument("--product", default=None, help="제품명 필터")
    extract_parser.set_defaults(func=cmd_extract)

    # list 서브커맨드
    list_parser = subparsers.add_parser("list", help="리뷰 목록 조회")
    list_parser.add_argument("--sentiment", choices=["positive", "negative", "neutral"], default=None)
    list_parser.add_argument("--rating", type=int, default=None, help="별점 필터 (1~5)")
    list_parser.add_argument("--date-from", default=None, help="시작일 (YYYY-MM-DD)")
    list_parser.add_argument("--date-to", default=None, help="종료일 (YYYY-MM-DD)")
    list_parser.add_argument("--page", type=int, default=1, help="페이지 번호 (기본 1)")
    list_parser.add_argument("--size", type=int, default=10, help="페이지당 건수 (기본 10)")
    list_parser.add_argument("--sort-by", default="review_date", help="정렬 기준 컬럼 (기본 review_date)")
    list_parser.add_argument("--order", choices=["asc", "desc"], default="desc", help="정렬 방향 (기본 desc)")
    list_parser.set_defaults(func=cmd_list)

    # show 서브커맨드
    show_parser = subparsers.add_parser("show", help="특정 리뷰 상세 조회")
    show_parser.add_argument("--id", type=int, required=True, help="조회할 리뷰 ID")
    show_parser.set_defaults(func=cmd_show)

    # stats 서브커맨드
    stats_parser = subparsers.add_parser("stats", help="전체 통계 요약 (부정 리뷰 급증 알림 포함)")
    stats_parser.set_defaults(func=cmd_stats)

    # dashboard 서브커맨드 (차트 생성 + 리포트 생성 통합)
    dashboard_parser = subparsers.add_parser("dashboard", help="대시보드 차트 및 리포트 생성")
    dashboard_parser.set_defaults(func=cmd_dashboard)

    # export 서브커맨드
    export_parser = subparsers.add_parser("export", help="리뷰 데이터 내보내기")
    export_parser.add_argument("--format", choices=["csv", "jsonl", "excel"], default="csv", help="내보내기 형식")
    export_parser.add_argument("--sentiment", choices=["positive", "negative", "neutral"], default=None, help="감정 필터")
    export_parser.add_argument("--rating-min", type=int, default=None, help="이 별점 이상만 포함")
    export_parser.set_defaults(func=cmd_export)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
    