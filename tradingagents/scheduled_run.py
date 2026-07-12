"""Unattended TradingAgents run for Windows Task Scheduler.

Runs daily and analyzes ONE ticker per run, rotating through TICKERS so
each ticker gets analyzed once per cycle (7 tickers = weekly per ticker).
The rotation position is kept in rotation_state.txt, so missed days are
never skipped — the next run simply picks up the next ticker in line.

Saves the full report tree under reports/<TICKER>/<date>/, appends to
scheduled_runs.log, and shows a Windows toast notification when done.

Run with the project venv's pythonw.exe so no console window appears:
    C:\\claude\\TradingAgents\\.venv\\Scripts\\pythonw.exe scheduled_run.py
"""

import base64
import datetime
import logging
import subprocess
import traceback
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
STATE_FILE = PROJECT_DIR / "rotation_state.txt"

logging.basicConfig(
    filename=PROJECT_DIR / "scheduled_runs.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("scheduled_run")

TICKERS = ["TSLA", "NVDA", "RKLB", "ORCL", "META", "PLTR", "IONQ"]


def read_rotation_index() -> int:
    try:
        return int(STATE_FILE.read_text().strip()) % len(TICKERS)
    except (FileNotFoundError, ValueError):
        return 0


def write_rotation_index(index: int) -> None:
    STATE_FILE.write_text(str(index % len(TICKERS)))


def toast(title: str, body: str) -> None:
    """Show a Windows toast via PowerShell/WinRT (no extra packages needed)."""
    ps = f"""
$title = @'
{title}
'@
$body = @'
{body}
'@
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$nodes = $template.GetElementsByTagName('text')
$nodes.Item(0).AppendChild($template.CreateTextNode($title.Trim())) | Out-Null
$nodes.Item(1).AppendChild($template.CreateTextNode($body.Trim())) | Out-Null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
$appId = '{{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}}\\WindowsPowerShell\\v1.0\\powershell.exe'
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show($toast)
"""
    encoded = base64.b64encode(ps.encode("utf-16-le")).decode("ascii")
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-EncodedCommand", encoded],
            timeout=30,
            capture_output=True,
        )
    except Exception:
        log.error("Toast notification failed:\n%s", traceback.format_exc())


def main() -> None:
    from dotenv import load_dotenv

    # Must run before importing tradingagents: DEFAULT_CONFIG reads
    # TRADINGAGENTS_* overrides and the API key at import time.
    load_dotenv(PROJECT_DIR / ".env")

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    from tradingagents.reporting import write_report_tree

    run_date = datetime.date.today().isoformat()
    index = read_rotation_index()
    ticker = TICKERS[index]
    next_ticker = TICKERS[(index + 1) % len(TICKERS)]
    log.info("=== Run started: %s on %s (rotation %d/%d) ===",
             ticker, run_date, index + 1, len(TICKERS))

    try:
        graph = TradingAgentsGraph(debug=False, config=DEFAULT_CONFIG.copy())
        final_state, decision = graph.propagate(ticker, run_date)
        save_path = PROJECT_DIR / "reports" / ticker / run_date
        write_report_tree(final_state, ticker, save_path)
        log.info("=== %s -> %s (report: %s) ===", ticker, decision, save_path)
        toast(f"TradingAgents {run_date}",
              f"{ticker}: {decision} (다음 차례: {next_ticker})")
    except Exception:
        log.error("%s failed:\n%s", ticker, traceback.format_exc())
        toast(f"TradingAgents {run_date} - 실패",
              f"{ticker} 분석 실패. scheduled_runs.log 확인 (다음 차례: {next_ticker})")
    finally:
        # Advance even on failure so one bad day doesn't stall the cycle;
        # the failed ticker comes around again next cycle.
        write_rotation_index(index + 1)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.critical("Run aborted:\n%s", traceback.format_exc())
        toast("TradingAgents 실행 실패", "scheduled_runs.log를 확인하세요.")
