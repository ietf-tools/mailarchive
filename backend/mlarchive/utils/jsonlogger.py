# Copyright The IETF Trust 2024, All Rights Reserved
from pythonjsonlogger.json import JsonFormatter
import time


class MailArchiveJsonFormatter(JsonFormatter):
    converter = time.gmtime  # use UTC
    default_msec_format = "%s.%03d"  # '.' instead of ','


class GunicornRequestJsonFormatter(MailArchiveJsonFormatter):
    """Only works with Gunicorn's logging"""
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record.setdefault("method", record.args["m"])
        log_record.setdefault("proto", record.args["H"])
        log_record.setdefault("remote_ip", record.args["h"])
        path = record.args["U"]  # URL path
        if record.args["q"]:  # URL query string
            path = "?".join([path, record.args["q"]])
        log_record.setdefault("path", path)
        log_record.setdefault("status", record.args["s"])
        log_record.setdefault("referer", record.args["f"])
        log_record.setdefault("user_agent", record.args["a"])
        log_record.setdefault("len_bytes", record.args["B"])
        log_record.setdefault("duration_ms", record.args["M"])
        log_record.setdefault("host", record.args["{host}i"])
        log_record.setdefault("x_request_start", record.args["{x-request-start}i"])
        log_record.setdefault("x_real_ip", record.args["{x-real-ip}i"])
        log_record.setdefault("x_forwarded_for", record.args["{x-forwarded-for}i"])
        log_record.setdefault("cf_connecting_ip", record.args["{cf-connecting-ip}i"])
        log_record.setdefault("cf_connecting_ipv6", record.args["{cf-connecting-ipv6}i"])
        log_record.setdefault("cf_ray", record.args["{cf-ray}i"])
        log_record.setdefault("asn", record.args["{x-ip-src-asnum}i"])
