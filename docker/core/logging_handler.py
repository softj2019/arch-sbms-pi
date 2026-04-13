### 실행 함수 로그 추적 및 기록
import sys
import os
import logging
from datetime import datetime

from core.network_resilience import record_outage_log

# 로그파일 저장 디렉토리 설정
def get_log_directory(folder):
    base_dir    = os.path.dirname(os.path.abspath(__file__))
    now         = datetime.now()
    month_dir   = now.strftime("%y%m")
    path        = os.path.join(base_dir, "logs", folder, month_dir)

    os.makedirs(path, exist_ok=True)
    os.chmod(path, 0o777)               # 권한 777

    return path

# 출력 로그 레벨 설정
class NetworkOutageBufferHandler(logging.Handler):
    def emit(self, record):
        if record.levelno < logging.WARNING:
            return

        try:
            record_outage_log(
                level=record.levelname,
                logger_name=record.name,
                message=record.getMessage(),
                created_at=record.created,
            )
        except Exception:
            pass


def setup_logging(folder):
    # INFO 레벨 이상의 로그만 출력
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # 핸들러 중복 설정 방지
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # INFO(20), WARNING(30)은 stdout → app.log
    info_handler = logging.StreamHandler(sys.stdout)
    info_handler.setLevel(logging.INFO)
    info_handler.addFilter(lambda record: record.levelno < logging.ERROR)
    info_handler.setFormatter(formatter)

    # ERROR(40) 이상은 stderr → app.err
    error_handler = logging.StreamHandler(sys.stderr)
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)

    # 로그 파일 저장 경로
    LOG_DIR = get_log_directory(folder)
    today   = datetime.now().strftime("%y%m%d")

    # 생성 파일 디렉토리 설정
    info_log_path  = os.path.join(LOG_DIR, f"{today}.log")
    err_log_path   = os.path.join(LOG_DIR, f"{today}.err")

    # INFO/WARNING 로그 출력 설정 및 파일 생성
    file_info_handler = logging.FileHandler(info_log_path, encoding="utf-8")
    file_info_handler.setLevel(logging.INFO)
    file_info_handler.addFilter(lambda r: r.levelno < logging.ERROR)
    file_info_handler.setFormatter(formatter)

    # ERROR 로그 출력 설정 및 파일 생성
    file_error_handler = logging.FileHandler(err_log_path, encoding="utf-8")
    file_error_handler.setLevel(logging.ERROR)
    file_error_handler.setFormatter(formatter)

    outage_buffer_handler = NetworkOutageBufferHandler()
    outage_buffer_handler.setLevel(logging.WARNING)

    # 핸들러 등록
    logger.handlers = [
        info_handler,
        error_handler,
        file_info_handler,
        file_error_handler,
        outage_buffer_handler,
    ]

    return logger
