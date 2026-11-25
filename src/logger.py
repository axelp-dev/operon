import logging
from pathlib import Path

COLORS = {
    "SEARCH": "\033[34m",  # Blue
    "FILTER": "\033[36m",  # Cyan
    "READ": "\033[35m",  # Magenta
    "INDEX": "\033[32m",  # Green
    "QUERY": "\033[33m",  # Yellow
    "WARN": "\033[33m",
    "ERROR": "\033[31m",
    "GREEN": "\033[32m",
    "RED": "\033[31m",
}

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"


class ScopeFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        scope = getattr(record, "scope", "INFO")
        color = COLORS.get(scope, "")
        return f"{color}{BOLD}[{scope:<6}]{RESET} {record.getMessage()}"


class OperonLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("operon")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

    def setup(self, log_file: Path | None = None) -> None:
        self._logger.handlers.clear()
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(ScopeFormatter())
        self._logger.addHandler(console)

        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file, encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(
                logging.Formatter("%(asctime)s [%(scope)s] %(levelname)s: %(message)s")
            )
            self._logger.addHandler(fh)

        logging.getLogger("httpx").setLevel(logging.WARNING)

    def reading_progress(self, idx: int, total: int, uid: str) -> None:
        """Display temporary reading status (only in console, not in log file)"""
        print(
            f"\r\033[35m{BOLD}[READ  ]{RESET} [{idx}/{total}] {uid} {DIM}... evaluating{RESET}",
            end="",
            flush=True,
        )

    def article(
        self, idx: int, total: int, uid: str, score: int, accepted: bool
    ) -> None:
        """Erase last temporary log line with final status & log it in file"""
        status = (
            f"{COLORS['GREEN']}{BOLD}✔ ACCEPTED ({score}/5){RESET}"
            if accepted
            else f"{DIM}{COLORS['RED']}✘ REJECTED ({score}/5){RESET}"
        )
        # \r\033[K erase line "... evaluating" before writing final status
        print(f"\r\033[K\033[35m{BOLD}[READ  ]{RESET} [{idx}/{total}] {status}  {uid}")

        # Clean trace in data/operon.log
        verdict = "ACCEPTED" if accepted else "REJECTED"
        self._logger.debug(
            f"[{idx}/{total}] {verdict} ({score}/5) - {uid}",
            extra={"scope": "READ"},
        )

    def wave(self, n_iter: int, max_iter: int) -> None:
        print(
            f"\n{BOLD}\033[36m━━━ WAVE {n_iter}/{max_iter} ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}"
        )

    def search(self, msg: str) -> None:
        self._logger.info(msg, extra={"scope": "SEARCH"})

    def filter(self, msg: str) -> None:
        self._logger.info(msg, extra={"scope": "FILTER"})

    def read(self, msg: str) -> None:
        self._logger.info(msg, extra={"scope": "READ"})

    def index(self, msg: str) -> None:
        self._logger.info(msg, extra={"scope": "INDEX"})

    def query(self, msg: str) -> None:
        self._logger.info(msg, extra={"scope": "QUERY"})

    def warn(self, msg: str) -> None:
        self._logger.warning(msg, extra={"scope": "WARN"})

    def info(self, msg: str) -> None:
        self._logger.info(msg, extra={"scope": "INFO"})

    def debug(self, scope: str, msg: str) -> None:
        self._logger.debug(msg, extra={"scope": scope.upper()})


log = OperonLogger()
