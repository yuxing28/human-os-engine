"""
Human-OS Engine - 结构化日志模块

替代 print 语句，提供生产级可观测性。
支持：
- 日志级别（DEBUG/INFO/WARNING/ERROR）
- 结构化输出（JSON 格式可选）
- 自动包含时间戳、模块名、行号
"""

import logging
import sys
import os

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # text or json

def _get_formatter():
    if LOG_FORMAT == "json":
        return logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s","module":"%(module)s","line":%(lineno)d,"message":"%(message)s"}',
            datefmt="%Y-%m-%dT%H:%M:%S"
        )
    return logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(module)s:%(lineno)d — %(message)s",
        datefmt="%H:%M:%S"
    )

# 配置根日志器
logger = logging.getLogger("human_os")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_get_formatter())
    logger.addHandler(handler)

# 便捷函数
def debug(msg: str, **kwargs):
    if kwargs:
        msg = f"{msg} {kwargs}"
    logger.debug(msg)

def info(msg: str, **kwargs):
    if kwargs:
        msg = f"{msg} {kwargs}"
    logger.info(msg)

def warning(msg: str, **kwargs):
    if kwargs:
        msg = f"{msg} {kwargs}"
    logger.warning(msg)

def error(msg: str, **kwargs):
    if kwargs:
        msg = f"{msg} {kwargs}"
    logger.error(msg)
