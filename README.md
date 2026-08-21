# AI 기반 고객 리뷰 감정 분석 대시보드

쿠팡 1인 셀러(욕실 틈새 청소솔 판매)를 위한 CLI 기반 고객 리뷰 감정 분석 도구입니다.
리뷰 데이터를 수집·정제하고 AI로 감정을 분석한 뒤, 시간에 따른 감정 변화 추이·불만 키워드·별점과 감정의 상관관계 등 비즈니스 의사결정에 활용 가능한 인사이트를 대시보드와 리포트 형태로 제공합니다.

> GitHub: `github.com/***/A2-3-C`

---

## 1. 프로젝트 목적과 주요 사용자

### 목적
수백~수천 건의 고객 리뷰를 사람이 일일이 읽지 않고도, AI를 활용해 감정을 자동 분류하고 핵심 키워드·트렌드를 빠르게 파악할 수 있도록 합니다. 단순 감정 분류에서 그치지 않고, 시간대별 감정 추이와 부정 리뷰 급증 여부까지 자동으로 감지하여 선제적인 대응이 가능하도록 설계했습니다.

### 주요 사용자
- **온라인 쇼핑몰 1인 셀러**: 별도의 데이터 분석 인력 없이도 리뷰 데이터를 빠르게 파악하고 싶은 소규모 판매자
- **품질/CS 담당자**: 반복되는 불만 패턴을 조기에 발견해 개선 조치를 취하고 싶은 담당자

### 샘플 데이터 구성
테스트용 샘플 리뷰 데이터(`data/sample_reviews.csv`, 40건)는 **쿠팡 1인 셀러의 '욕실 틈새 청소솔' 판매 상품에 달린 고객 리뷰**를 시나리오로 구성했습니다. 정상적인 리뷰뿐 아니라, 정제(clean) 로직 검증을 위해 빈 리뷰·짧은 리뷰·날짜 형식 불일치·완전 중복 리뷰 등 의도적인 결함 데이터도 함께 포함했으며, 부정 리뷰 급증 알림 기능 검증을 위해 특정 기간(1/22~1/28)에 부정 리뷰가 몰리도록 설계했습니다.

---

## 2. 환경 세팅 (설치 방법)

이 프로젝트를 실행하기 전, 아래 환경이 준비되어 있어야 합니다.

### 1) Python 설치
- Python 3.10 이상 필요
- https://www.python.org/downloads/ 에서 다운로드 후 설치
- 설치 시 **"Add Python to PATH"** 옵션을 반드시 체크
- 설치 확인:
  ```bash
  python --version
  ```

### 2) Git 설치 (버전 관리 및 GitHub 연동용)
- https://git-scm.com/downloads 에서 운영체제에 맞는 버전 다운로드 후 설치 (기본 옵션 그대로 진행해도 무방)
- 설치 확인:
  ```bash
  git --version
  ```

### 3) SQLite
- 별도 설치가 필요 없습니다. Python 표준 라이브러리(`sqlite3`)에 기본 내장되어 있어, Python만 설치되어 있으면 바로 사용 가능합니다.
- (선택) DB 내용을 눈으로 직접 확인하고 싶다면 [DB Browser for SQLite](https://sqlitebrowser.org/) 같은 무료 GUI 도구를 추가로 설치하면 편리합니다.

### 4) 프로젝트 의존 패키지 설치 (pip)
프로젝트 루트 폴더(`review-dashboard`)로 이동한 뒤, 아래 명령어로 `requirements.txt`에 정의된 패키지를 한 번에 설치합니다.
```bash
pip install -r requirements.txt
```

#### requirements.txt 구성

| 패키지 | 용도 |
|---|---|
| `pandas` | CSV/Excel 파일 읽기 및 데이터프레임 처리 |
| `openpyxl` | Excel(.xlsx) 파일 읽기/쓰기 |
| `matplotlib` | 대시보드 차트(감정 분포, 추이, 별점-감정) 생성 |
| `openai` | AI 감정 분석 및 키워드/요약 추출 API 호출 |

설치 완료 후 아래로 정상 설치 여부를 확인할 수 있습니다.
```bash
pip show openai
```

---

## 3. API 키 환경변수 설정 방법

API 키는 보안을 위해 코드나 설정 파일에 직접 작성하지 않고, **환경변수**로 관리합니다. `config.json`에는 실제 키 값이 아니라 "어떤 환경변수 이름을 읽어올지"만 지정되어 있습니다.

```json
"api": {
  "provider": "openai",
  "api_key_env": "OPENAI_API_KEY",
  "model": "gpt-4o-mini"
}
```

### Windows (PowerShell)

**임시 등록 (현재 터미널 세션에서만 유효)**
```powershell
$env:OPENAI_API_KEY = "sk-proj-본인의_실제_키"
```

**영구 등록**
```powershell
[System.Environment]::SetEnvironmentVariable("OPENAI_API_KEY", "sk-proj-본인의_실제_키", "User")
```
(영구 등록 후에는 터미널을 새로 열어야 적용됩니다)

### 확인
```powershell
echo $env:OPENAI_API_KEY
```

> ⚠️ **주의**: API 키가 노출된 화면은 캡처/커밋하지 않도록 주의해 주세요. `.gitignore`에 `.env` 파일이 포함되어 있어 별도 환경변수 파일을 사용해도 안전합니다.

---

## 4. 프로젝트 폴더 및 파일 설명

```
review-dashboard/
├── main.py                  # CLI 진입점 (argparse 서브커맨드 정의 및 라우팅)
├── config.json               # 설정 파일 (API 설정, 저장소 경로, 정제/알림 기준값 등)
├── requirements.txt          # 의존 패키지 목록
├── modules/
│   ├── storage.py            # SQLite 연결, 테이블 초기화, list/show 조회 함수
│   ├── data_loader.py        # 파일 로드(import), 정제(clean), 내보내기(export)
│   ├── ai_service.py         # AI 감정 분석(analyze), 키워드/요약 추출(extract), 로거 설정
│   ├── analytics.py          # 통계 집계(stats), 부정 리뷰 급증 알림
│   ├── visualize.py          # matplotlib 차트 3종 생성 (한글 폰트 적용)
│   └── report.py             # 종합 리포트 생성(TXT/MD 저장)
├── data/
│   ├── sample_reviews.csv    # 테스트용 샘플 리뷰 데이터 (40건, 욕실 틈새 청소솔 리뷰)
│   └── reviews.db            # SQLite DB (실행 시 자동 생성, git 추적 제외)
├── logs/
│   └── app.log                # INFO/WARNING/ERROR 로그 기록 (git 추적 제외)
├── output/
│   ├── charts/                 # 대시보드 PNG 차트 3종
│   ├── reports/                # 리포트 TXT/MD 파일
│   └── export_*.*              # 내보내기 결과 (CSV/JSONL/Excel)
├── screenshots/               # 구현 결과 캡처 이미지 모음
└── .gitignore
```

---

## 5. DB 구조와 전체 데이터 처리 흐름

### 저장소: SQLite (`data/reviews.db`)

원본 데이터와 정제된 데이터를 **분리 저장**하여, 정제 로직에 문제가 생기더라도 원본을 보존하고 재처리할 수 있도록 설계했습니다.

#### `raw_reviews` (원본 저장)
| 컬럼 | 설명 |
|---|---|
| id | PK, 자동 증가 |
| review_text, rating, review_date, product_name | 원본 그대로 (검증 전) |
| imported_at, source_file | 가져온 시각, 원본 파일 경로 |

#### `clean_reviews` (정제 + 분석 결과 저장)
| 컬럼 | 설명 |
|---|---|
| id, raw_id | PK, 원본 레코드 참조 |
| review_text, rating, review_date, product_name | 정규화/검증 완료된 값 |
| dedup_key | 중복 판단 기준 (텍스트+날짜+제품명 조합), UNIQUE 제약 |
| sentiment, sentiment_score, analyzed_at | AI 감정 분석 결과 (분석 전 NULL) |

#### `extractions` (AI 종합 추출 결과 저장)
| 컬럼 | 설명 |
|---|---|
| filter_condition, review_count | 추출 조건, 대상 건수 |
| positive_keywords, negative_keywords, summary, improvement_suggestions | AI 추출 결과 (JSON 문자열) |

### 데이터 처리 흐름

```
[CSV/Excel 파일]
      ↓ import
[raw_reviews]  ← 원본 그대로 보존
      ↓ clean (필수필드 검증, 정규화, 별점/날짜 검증, 짧은리뷰 필터링, 중복 skip/upsert)
[clean_reviews]
      ↓ analyze (AI 감정 분석: 긍정/부정/중립 + 신뢰도)
[clean_reviews (sentiment 컬럼 갱신)]
      ↓ extract (여러 리뷰 종합 → 키워드/요약/개선제안)
[extractions]
      ↓ stats / dashboard (통계 집계, 부정 리뷰 급증 알림, 차트/리포트 생성)
[output/charts/*.png, output/reports/*.txt,*.md]
      ↓ export
[output/export_*.csv, *.jsonl, *.xlsx]
```

---

## 6. 9개 CLI 명령어와 주요 사용 예

전체 명령어는 `python main.py <서브커맨드> [옵션]` 형태로 실행합니다.

| 명령어 | 기능 | 주요 옵션 |
|---|---|---|
| `import` | CSV/Excel 파일을 raw 저장소로 가져오기 | `--file` |
| `clean` | raw 데이터를 정제하여 clean 저장소로 저장 | `--mode skip\|upsert` |
| `analyze` | AI 감정 분석 실행 | `--all`, `--id`, `--unanalyzed`, `--limit` |
| `extract` | 조건별 리뷰 종합 → AI 키워드/요약/개선제안 추출 | `--sentiment`, `--date-from`, `--date-to`, `--product` |
| `list` | 리뷰 목록 조회 (필터+페이지네이션+정렬) | `--sentiment`, `--rating`, `--page`, `--size`, `--sort-by`, `--order` |
| `show` | 특정 리뷰 상세 조회 | `--id` |
| `stats` | 전체 통계 요약 + 부정 리뷰 급증 알림 | (없음) |
| `dashboard` | 차트 3종 + 종합 리포트 생성 (TXT/MD) | (없음) |
| `export` | 데이터 내보내기 | `--format csv\|jsonl\|excel`, `--sentiment`, `--rating-min` |

### 사용 예시

```bash
# 1) 샘플 데이터 가져오기
python main.py import --file data/sample_reviews.csv

# 2) 정제
python main.py clean

# 3) 미분석 리뷰 감정 분석
python main.py analyze --unanalyzed

# 4) 부정 리뷰 키워드/요약 추출
python main.py extract --sentiment negative

# 5) 부정 리뷰 목록 조회 (최신순, 5건씩)
python main.py list --sentiment negative --page 1 --size 5

# 6) 특정 리뷰 상세 확인
python main.py show --id 1

# 7) 전체 통계 및 급증 알림 확인
python main.py stats

# 8) 대시보드(차트+리포트) 생성
python main.py dashboard

# 9) 부정 리뷰만 CSV로 내보내기
python main.py export --format csv --sentiment negative
```

---

## 7. 실행 결과 및 생성되는 산출물

| 산출물 | 위치 | 설명 |
|---|---|---|
| SQLite DB | `data/reviews.db` | raw/clean/extractions 3개 테이블 |
| 로그 파일 | `logs/app.log` | INFO/WARNING/ERROR 레벨 기록 |
| 감정 분포 차트 | `output/charts/sentiment_distribution.png` | 파이 차트 |
| 시간별 추이 차트 | `output/charts/sentiment_trend.png` | 날짜별 감정 건수 선그래프 |
| 별점-감정 분포 차트 | `output/charts/rating_sentiment_matrix.png` | 별점별 감정 누적 막대그래프 |
| 종합 리포트 | `output/reports/report_YYYYMMDD_HHMMSS.txt`, `.md` | 핵심 지표, TOP5 키워드, AI 인사이트, 알림 포함 |
| 내보내기 파일 | `output/export_YYYYMMDD_HHMMSS.*` | CSV / JSONL / Excel 3종 지원 |

### 리포트 포함 내용
- 핵심 지표 5종: 총 리뷰 수, 분석 완료율, 긍정 비율, 평균 별점, 평균 감정 점수
- TOP 5 긍정/부정 키워드 (실제 리뷰 원문 내 등장 횟수 기준)
- AI 인사이트 요약 및 개선 제안
- 부정 리뷰 급증 알림 결과

### 대시보드 차트 결과물

#### 감정 분포 (파이 차트)
![감정 분포](https://raw.githubusercontent.com/ilililililil4319/A2-3-C/main/review-dashboard/screenshots/38_챠트2.png)

#### 별점별 감정 분포 (누적 막대그래프)
![별점별 감정 분포](https://raw.githubusercontent.com/ilililililil4319/A2-3-C/main/review-dashboard/screenshots/37_챠트1.png)

#### 시간별 감정 추이 (선그래프)
![시간별 감정 추이](https://raw.githubusercontent.com/ilililililil4319/A2-3-C/main/review-dashboard/screenshots/39_챠트3.png)

### 최종 검증표

전체 PDF 요구사항(필수 13개 항목), 보너스 과제, 제약사항 준수 여부를 정리한 최종 검증표입니다.

![최종 검증표](https://raw.githubusercontent.com/ilililililil4319/A2-3-C/main/review-dashboard/screenshots/48_최종점검.png)

---

## 8. 주요 예외 처리와 한계점

### 예외 처리
| 상황 | 처리 방식 |
|---|---|
| 필수 필드(리뷰 텍스트) 누락/공백 | `clean` 단계에서 제외, WARNING 로그 기록 |
| 별점 범위 초과, 잘못된 형식 | `NULL` 처리 (리뷰 자체는 유지, 별점은 선택 필드) |
| 날짜 형식 불일치 (`YYYY/MM/DD` 등) | 여러 포맷 자동 인식 후 `YYYY-MM-DD`로 통일, 실패 시 `NULL` |
| 중복 리뷰 | `dedup_key` 기준 `skip`(기본) 또는 `upsert` 처리 |
| AI API 호출 실패 | 해당 건만 스킵, ERROR 로그 기록 후 나머지 계속 진행 |
| AI 응답이 JSON 형식이 아닌 경우 | `response_format={"type": "json_object"}`로 강제, 코드블록 마커 제거 후 파싱 |
| 부정 리뷰 급증 알림 표본 부족 (최소 5건 미만) | 알림 생략, WARNING 로그 기록 |

### 한계점
- **AI 응답의 비결정성**: 동일한 데이터라도 재실행 시 감정 점수·키워드 순위가 소폭 달라질 수 있습니다.
- **키워드 추출 품질**: 부정 리뷰 키워드 추출 시, 문맥과 분리된 단어가 뽑히는 경우가 있습니다 (예: "부드러워"가 부정 키워드로 추출된 사례 — 원문은 "너무 부드러워서 세척력이 떨어진다"는 맥락이나, 단어만 추출 시 의미가 왜곡됨). 프롬프트에 "문제의 핵심을 담은 구 단위로 추출"하도록 지시를 보강하면 개선 가능합니다.
- **부정 리뷰 급증 알림 기준**: "오늘" 기준이 아니라 데이터 내 최신 리뷰 작성일 기준으로 최근/직전 구간을 계산합니다. 과거 샘플 데이터 테스트에 적합하나, 실서비스에서는 현재 날짜 기준으로 전환이 필요할 수 있습니다.
- **실시간성 없음**: PDF 제약사항에 따라 정적 PNG 차트와 파일 기반 리포트로만 구성되며, 실시간 웹 대시보드는 지원하지 않습니다.

---

## 9. 사용한 AI 도구 및 프롬프트

- **사용한 AI 도구**: Claude
- **프롬프트**: 저장소에 포함된 `프롬프트.txt` 파일 참고 (KDT AI 분야 스타강사 역할 부여, PDF 분석 → 단계별(STEP-by-STEP) 진행 → 최종 검증표 작성까지의 전체 진행 방식을 정의)

---

## 참고
- AI 모델: OpenAI `gpt-4o-mini` (JSON 강제 응답 모드 사용)
- 개발/검증 환경: Python 3.10+, Windows PowerShell
- 보너스 과제: 감정 변화 알림(부정 리뷰 급증 감지) 구현
