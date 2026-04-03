"""
런타임 에러 로깅 유틸리티
- 파일 및 콘솔 로깅
- 자동 traceback 캡처
- GitHub Actions 친화적 출력
"""

import logging
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path
from functools import wraps

# 로그 디렉토리 설정
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 로거 설정
def get_logger(name: str) -> logging.Logger:
    """모듈별 로거 생성"""
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # 파일 핸들러 (에러만)
        error_file = LOG_DIR / f"errors_{datetime.now().strftime('%Y%m')}.log"
        file_handler = logging.FileHandler(error_file, encoding='utf-8')
        file_handler.setLevel(logging.WARNING)
        file_format = logging.Formatter(
            '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

        # 콘솔 핸들러
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('[%(name)s] %(message)s')
        console_handler.setFormatter(console_format)
        logger.addHandler(console_handler)

    return logger


def log_error(logger: logging.Logger, message: str, exc: Exception = None,
              include_traceback: bool = True):
    """에러 로깅 (traceback 포함)"""
    error_msg = message

    if exc:
        error_msg = f"{message}: {type(exc).__name__}: {exc}"

    if include_traceback and exc:
        tb = traceback.format_exc()
        if tb and tb != "NoneType: None\n":
            error_msg = f"{error_msg}\n{tb}"

    logger.error(error_msg)

    # GitHub Actions 워크플로우용 출력
    if os.environ.get('GITHUB_ACTIONS'):
        print(f"::error::{message}")


def log_warning(logger: logging.Logger, message: str, exc: Exception = None):
    """경고 로깅"""
    if exc:
        logger.warning(f"{message}: {type(exc).__name__}: {exc}")
    else:
        logger.warning(message)


def safe_execute(logger: logging.Logger, default=None, message: str = None):
    """데코레이터: 함수 실행 중 에러 발생 시 로깅 후 기본값 반환"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                err_msg = message or f"{func.__name__} 실행 중 오류"
                log_error(logger, err_msg, e)
                return default
        return wrapper
    return decorator


class ErrorContext:
    """컨텍스트 매니저: with 블록 내 에러 로깅"""

    def __init__(self, logger: logging.Logger, operation: str,
                 suppress: bool = False, default=None):
        self.logger = logger
        self.operation = operation
        self.suppress = suppress
        self.default = default
        self.exception = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.exception = exc_val
            log_error(self.logger, f"{self.operation} 실패", exc_val)
            return self.suppress  # True면 예외 억제
        return False


# 간편 사용을 위한 전역 함수들
_default_logger = None

def init_default_logger(name: str = "trading"):
    """기본 로거 초기화"""
    global _default_logger
    _default_logger = get_logger(name)
    return _default_logger

def get_default_logger() -> logging.Logger:
    """기본 로거 반환 (없으면 생성)"""
    global _default_logger
    if _default_logger is None:
        _default_logger = get_logger("trading")
    return _default_logger

def error(message: str, exc: Exception = None):
    """간편 에러 로깅"""
    log_error(get_default_logger(), message, exc)

def warning(message: str, exc: Exception = None):
    """간편 경고 로깅"""
    log_warning(get_default_logger(), message, exc)

def info(message: str):
    """간편 정보 로깅"""
    get_default_logger().info(message)

def debug(message: str):
    """간편 디버그 로깅"""
    get_default_logger().debug(message)
