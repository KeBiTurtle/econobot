# 경제지표 발송·해석 텔레그램 봇

별 3개(★★★)급 미국 경제지표를 텔레그램으로 자동 발송하는 봇입니다.

- 발표 당일 아침, 오늘 어떤 지표가 나오는지 사전 공지
- 발표 직후 실제치 vs 예상치(컨센서스) 비교 (상회/부합/하회)
- 연준(Fed)이 중요하게 보는 지표(CPI, PCE, 고용지표, GDP, FOMC 등)는 몇 분 뒤 세부 해석 추가 발송
- 완전 무료 구성(GitHub Actions + cron-job.org + FRED 무료 API)

---

## 1. 전체 구조 한눈에 보기

```
cron-job.org(무료, 1~5분 간격) --HTTP 요청--> GitHub API(repository_dispatch)
        --> GitHub Actions 워크플로우 실행 --> bot/main.py 실행
        --> ForexFactory 캘린더 + FRED API 조회 --> 텔레그램 발송
        --> state.json 갱신 후 리포지토리에 커밋(중복발송 방지)
```

봇 자체는 "서버"가 아니라, **외부에서 주기적으로 깨워주면 그때만 실행되는 스크립트**입니다.
그래서 24/7 서버 없이도 무료로 돌릴 수 있습니다.

### ⚠️ 타이밍에 대한 솔직한 한계
- "발표 후 몇 분 이내" 요구사항을 만족시키려면 최소 1~5분 간격으로 봇을 깨워야 합니다.
- GitHub Actions 자체의 `schedule` cron은 **혼잡할 때 수십 분~수 시간까지 지연**되는 경우가 실제로 보고되고 있어(특히 정시), 이것만 믿고 쓰면 요구사항 6번("몇 분 이내")을 못 지킬 수 있습니다.
- 그래서 이 프로젝트는 **cron-job.org가 GitHub API를 직접 호출(`repository_dispatch`)해서 즉시 실행을 트리거**하는 방식을 기본으로 합니다. 이 방식은 GitHub 자체 스케줄 큐를 거치지 않아 훨씬 빠르고 안정적입니다. (schedule cron은 보조 백업으로만 15분 간격으로 남겨뒀습니다.)
- 그래도 100% 실시간 보장은 아닙니다(무료 인프라의 태생적 한계). 정말 초단위 정밀도가 필요하면 유료 VPS+상시 프로세스가 필요한데, 말씀하신 조건(1초 단위 아님, 몇 분 이내 OK)에는 이 구성이 적합합니다.

---

## 2. 준비물 체크리스트

- [ ] GitHub 계정 (무료)
- [ ] 이미 만들어두신 텔레그램 봇의 **토큰**과, 알림을 받을 **chat_id**
- [ ] FRED(세인트루이스 연은) 무료 API 키
- [ ] cron-job.org 계정 (무료)

---

## 3. 텔레그램 chat_id 알아내기

BotFather로 봇은 이미 만드셨고, 봇과 대화(메시지 1개 전송)까지 하신 상태라고 하셨습니다. 이제 chat_id만 알아내면 됩니다.

1. 텔레그램 앱에서 만드신 봇을 열고, 아무 메시지나 하나 보냅니다 (예: "안녕").
2. 브라우저 주소창에 아래 주소를 입력합니다 (YOUR_BOT_TOKEN 자리에 BotFather가 준 토큰을 넣으세요):
   ```
   https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates
   ```
3. 응답 JSON에서 `"chat":{"id":123456789, ...}` 부분의 숫자가 chat_id 입니다.
4. 만약 `"result":[]`처럼 비어 있다면, 1번(봇에게 메시지 보내기)을 다시 하고 새로고침하세요.
5. 그룹방으로 받고 싶다면, 봇을 그룹에 초대하고 그룹에서 메시지를 보낸 뒤 같은 방법으로 chat_id를 확인하세요(그룹은 음수 id).

> 토큰은 비밀번호와 같습니다. 다른 사람에게 노출되지 않도록 주의하세요.

---

## 4. FRED API 키 발급 (무료, 즉시 발급)

1. https://fredaccount.stlouisfed.org/apikeys 접속 후 무료 계정 생성/로그인
2. "Request API Key" 클릭, 용도는 "개인 프로젝트/봇" 정도로 간단히 기입
3. 발급된 키 문자열을 복사해둡니다.

이 키가 없어도 봇은 동작하지만(발표 수치 알림까지는 됨), **연준 핵심지표 세부 해석 기능(요구사항 4, 5번)은 이 키가 있어야 정상 동작**합니다.

---

## 5. GitHub 리포지토리에 올리기

1. GitHub에서 새 저장소 생성 (예: `econ-indicator-bot`).
   - **Public(공개)으로 만드는 것을 추천**합니다. Public 저장소는 GitHub Actions 실행 시간이 사실상 무제한 무료입니다. (봇 코드 자체에는 토큰/키가 들어있지 않고 전부 Secrets로 분리되어 있어 공개해도 안전합니다.)
   - Private로 해도 되지만, 월 2,000분 무료 한도가 있어 5분 간격으로 자주 돌리면 한도를 초과할 수 있습니다.
2. 이 프로젝트 폴더(zip 압축 해제한 것) 전체를 그 저장소에 업로드합니다. 방법은 편하신 대로:
   - GitHub 웹에서 "Add file → Upload files"로 폴더 내용 드래그 앤 드롭, 또는
   - 로컬에 git이 있다면:
     ```bash
     git init
     git add .
     git commit -m "init: 경제지표 텔레그램 봇"
     git branch -M main
     git remote add origin https://github.com/YOUR_ID/econ-indicator-bot.git
     git push -u origin main
     ```

---

## 6. GitHub Secrets 등록

저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서 아래 3개를 등록하세요.

| Name | 값 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather가 준 토큰 |
| `TELEGRAM_CHAT_ID` | 3단계에서 확인한 chat_id |
| `FRED_API_KEY` | 4단계에서 발급받은 키 |

(선택) 같은 화면의 **Variables** 탭에서 `DAILY_DIGEST_TIME_KST`(기본 `07:00`), `DAILY_DIGEST_WINDOW_MINUTES`(기본 `10`)를 원하는 값으로 바꿀 수 있습니다.

---

## 7. Actions 권한 확인

저장소 → **Settings → Actions → General → Workflow permissions** 에서
**"Read and write permissions"** 를 선택 후 저장하세요. (state.json을 봇이 스스로 커밋하기 위해 필요합니다.)

---

## 8. cron-job.org로 "1~5분마다 깨우기" 설정 (핵심)

1. https://cron-job.org 무료 가입
2. GitHub에서 **Personal Access Token(PAT)** 발급: GitHub 우측상단 프로필 → Settings → Developer settings → Personal access tokens → Fine-grained tokens →
   - Repository access: 방금 만든 저장소만 선택
   - Permissions: **Contents: Read and write**, **Actions: Read and write** 부여
   - 생성된 토큰(`github_pat_...`)을 복사
3. cron-job.org에서 **Create cronjob**:
   - URL: `https://api.github.com/repos/YOUR_ID/econ-indicator-bot/dispatches`
   - Request method: `POST`
   - Headers 추가:
     - `Authorization: Bearer github_pat_여기에_붙여넣기`
     - `Accept: application/vnd.github+json`
     - `Content-Type: application/json`
   - Body(raw JSON): `{"event_type": "poll"}`
   - Schedule: **매 3~5분마다** (Every 3 minutes / Every 5 minutes 선택)
   - Save & Enable

이제 cron-job.org가 3~5분마다 GitHub에 "지금 실행해!" 라고 신호를 보내고, GitHub Actions가 즉시 `bot/main.py`를 실행합니다.

---

## 9. 동작 테스트

1. 저장소 → **Actions** 탭 → `Economic Indicator Bot` 워크플로우 → **Run workflow** 버튼으로 수동 실행해봅니다.
2. 로그에서 에러가 없는지, 텔레그램으로 메시지가 오는지 확인합니다(단, 오늘 별3개 지표가 없는 날이면 조용할 수 있습니다 - 이건 정상입니다).
3. 미국 CPI/고용지표 발표일에 맞춰 실제 알림이 오는지 확인해보세요. (경제지표 발표 일정은 https://www.bls.gov/schedule/ 등에서 미리 확인 가능)

---

## 10. 다루는 지표 (별3개급, `bot/indicators.py`에서 관리)

| 지표 | 연준 핵심지표 세부해석 |
|---|---|
| CPI (헤드라인/근원) | ✅ |
| PCE 물가지수 (헤드라인/근원, 연준 공식 선호지표) | ✅ |
| 비농업고용(NFP)/실업률/평균임금 | ✅ |
| PPI (헤드라인/근원) | ✅ |
| GDP 성장률 | ✅ |
| JOLTS 채용공고 | ✅ |
| 신규 실업수당 청구건수 | ✅ (ForexFactory는 보통 Medium 표기지만 예외로 포함) |
| FOMC 기준금리 결정 | ✅ (금리 자체 변화만; 성명서 톤은 자동분석 X) |
| 소매판매 | 발표치만 |
| ISM 제조업/서비스업 PMI | 발표치만 (FRED 미제공 지표라 캘린더 소스 실측치 사용) |
| 컨퍼런스보드 소비자신뢰지수 | 발표치만 |
| 미시간대 소비자심리지수 | 발표치만 |
| 내구재주문 | 발표치만 |

PPI/GDP/JOLTS/신규 실업수당 청구건수는 CPI·PCE와 마찬가지로 추세·맥락을 포함한 해설형 메시지를 보냅니다
(예: PPI는 CPI/PCE에 선행하는 원가 압력이라는 맥락, GDP는 직전 분기 대비 가속/둔화, JOLTS·청구건수는
노동시장 냉각/과열 해석 등).

지표를 추가/제외하고 싶으면 `bot/indicators.py`의 `INDICATORS` 리스트만 수정하면 됩니다. 지표마다
`min_impact`를 지정해 ForexFactory의 기본 High 필터보다 낮은 등급(Medium 등)도 포함시킬 수 있습니다.

---

## 11. 알려진 한계 / 주의사항

- **데이터 출처**: 캘린더·예상치·실제치는 ForexFactory의 공개 위젯 피드(`nfs.faireconomy.media/ff_calendar_thisweek.json`)를 사용합니다. investing.com은 Cloudflare 등 봇 차단이 잦아 기본 소스로 쓰지 않았습니다. ForexFactory 피드가 일시적으로 막히거나 형식이 바뀌면 그 주기의 알림이 누락될 수 있습니다(다음 폴링에서 자동 복구 시도).
- **FRED 반영 시차**: 발표 직후 FRED가 해당 수치를 실시간 반영하지 못하는 경우가 있어, 세부 해석은 결과 발송 후 최소 2분 대기 후 시도하도록 만들었습니다(`bot/main.py`의 `INTERPRETATION_DELAY_MINUTES`). 그래도 안 맞으면 다음 폴링에서 다시 최신 FRED 값으로 갱신해 보내지는 않고, 처음 보낸 값을 유지합니다(중복 스팸 방지 우선). 필요하면 이 로직은 확장 가능합니다.
- **FOMC 해석**: 금리 인상/인하/동결 여부와 새 목표범위는 자동으로 안내하지만, 성명서 문구나 파월 의장 발언의 "매파적/비둘기적" 뉘앙스는 자연어 분석을 하지 않습니다(신뢰도 낮은 자동판단보다 원문 확인을 권장하는 게 낫다고 판단했습니다).
- **투자 조언 아님**: 해석 문구는 "일반적으로 이렇게 해석되는 경향이 있다"는 참고 설명이며, 매수/매도 추천이 아닙니다.
- **비용**: GitHub Actions(Public repo 무제한) + cron-job.org(무료 플랜) + FRED(무료) 조합으로 정상적인 개인 사용 범위에서는 비용이 발생하지 않습니다.

---

## 12. 로컬에서 테스트하고 싶다면

```bash
pip install -r requirements.txt
cp .env.example .env   # 값 채우기
export $(grep -v '^#' .env | xargs)   # 또는 direnv 등 사용
python -m bot.main
```

캘린더만 따로 확인:
```bash
python -m bot.calendar_source
```
