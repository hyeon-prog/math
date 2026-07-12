# TradingAgents 자동 분석 설정 기록

> 2026-07-12 설정 완료. 로컬 위치: `C:\claude\TradingAgents`
> 원본: https://github.com/TauricResearch/TradingAgents (소스는 재클론 가능하므로 이 백업에는 커스텀 파일만 포함)

## 1. 설치 과정

```powershell
cd C:\claude
git clone https://github.com/TauricResearch/TradingAgents.git
cd TradingAgents

# conda가 없어서 표준 venv 사용 (Python 3.13.14)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
```

CLI 수동 실행:

```powershell
cd C:\claude\TradingAgents
.\.venv\Scripts\tradingagents.exe
```

## 2. .env 설정 (API 키는 보안상 이 백업에서 제외)

`C:\claude\TradingAgents\.env`의 활성 설정:

```
GOOGLE_API_KEY=<Google AI Studio에서 발급한 키>   # https://aistudio.google.com/apikey
TRADINGAGENTS_LLM_PROVIDER=google
TRADINGAGENTS_DEEP_THINK_LLM=gemini-3.5-flash
TRADINGAGENTS_QUICK_THINK_LLM=gemini-3.1-flash-lite
TRADINGAGENTS_LLM_MAX_RETRIES=6
TRADINGAGENTS_OUTPUT_LANGUAGE=Korean
```

### 왜 Flash 모델인가

- 처음에 `gemini-3.1-pro-preview`를 선택했더니 429 RESOURCE_EXHAUSTED 발생.
  Pro 계열은 **무료 티어 한도가 0** (결제 연결 필요). 소비자용 "제미나이 Pro 구독"은
  API 쿼터와 무관함.
- Flash 계열은 무료 티어 지원. 실측 한도: `gemini-3.5-flash` **하루 20회**,
  flash-lite는 훨씬 여유.
- 1종목 분석당 실사용량: flash 3회 + flash-lite 16회 (약 1분 30초 소요).
  → 하루 1~4종목은 무료 티어로 충분.

## 3. 자동 실행 구성

### scheduled_run.py (이 폴더에 백업됨)

- **매일 1종목씩 순환** 분석: TSLA → NVDA → RKLB → ORCL → META → PLTR → IONQ → 반복
  (7종목이므로 종목당 주 1회)
- 순환 위치는 `rotation_state.txt`(0부터 시작하는 인덱스)에 저장.
  PC가 꺼져 하루를 건너뛰어도 다음 실행 때 밀린 차례부터 이어감.
- 실패해도 인덱스는 전진 (다음 사이클에 재시도), 로그는 `scheduled_runs.log`.
- 리포트 저장: `reports/<티커>/<날짜>/` (1_analysts / 2_research / 3_trading /
  4_risk / 5_portfolio / complete_report.md)
- 완료/실패 시 PowerShell WinRT로 Windows 토스트 알림 (다음 차례 종목 표시).

### 작업 스케줄러 등록 (task-scheduler.xml로 복원 가능)

```powershell
# 새로 등록할 때
schtasks /Create /TN "TradingAgents Weekly Analysis" /TR "\"C:\claude\TradingAgents\.venv\Scripts\pythonw.exe\" \"C:\claude\TradingAgents\scheduled_run.py\"" /SC DAILY /ST 09:00 /F

# 절전 깨우기 / 놓친 실행 보충 / 배터리 실행 허용
$task = Get-ScheduledTask -TaskName "TradingAgents Weekly Analysis"
$task.Settings.WakeToRun = $true
$task.Settings.StartWhenAvailable = $true
$task.Settings.DisallowStartIfOnBatteries = $false
$task.Settings.StopIfGoingOnBatteries = $false
Set-ScheduledTask -TaskName "TradingAgents Weekly Analysis" -Settings $task.Settings

# XML로 복원할 때
schtasks /Create /TN "TradingAgents Weekly Analysis" /XML task-scheduler.xml
```

- 매일 09:00 실행. 절전/최대 절전이면 깨워서 실행, 완전 종료 상태였으면
  다음 로그인 직후 보충 실행. **완전 종료(S5)는 못 깨우므로 절전 권장.**
- "Interactive only" 모드 — 로그인된 사용자 세션에서 실행 (토스트 알림 표시 목적).

## 4. 새 PC에서 복원하는 순서

1. 위 1번대로 클론 + venv + pip install
2. `.env` 작성 (위 2번 내용 + 새 API 키 발급)
3. 이 폴더의 `scheduled_run.py`, `rotation_state.txt`를 프로젝트 루트에 복사
4. 위 3번의 schtasks 명령 실행 (또는 task-scheduler.xml로 복원)

## 5. 종목 변경 방법

`scheduled_run.py`의 `TICKERS` 리스트만 수정하면 됨. 개수가 바뀌어도
순환은 자동 적응 (주기 = 종목 수 일). 순서가 한 번 어긋나는 게 싫으면
`rotation_state.txt`의 숫자를 원하는 종목의 인덱스(0부터)로 맞출 것.
