"""Email verification utilities.

Provides `verify_email(email, enable_smtp=False)` which runs:
 - Tier 1: syntax validation via email-validator
 - Tier 2: DNS checks (MX, fallback A/AAAA)
 - Tier 3: optional SMTP probe (disabled by default)

Results are conservative and honest: when unsure, return `unknown`.
"""

from __future__ import annotations

import random
import socket
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import smtplib
from email_validator import EmailNotValidError, validate_email

try:
    import dns.resolver
except Exception:  # pragma: no cover - dns not available in some test environments
    dns = None  # type: ignore

from cold_emailer.utils import get_logger

logger = get_logger(__name__)


@dataclass
class VerifyResult:
    status: str
    confidence: float
    reasons: List[str]
    mx_hosts: List[str]
    is_catch_all: Optional[bool]
    normalized_email: Optional[str]


# Simple in-memory caches and rate-limits
_probe_cache: Dict[str, Tuple[VerifyResult, float]] = {}
_last_probe_time: Dict[str, float] = {}


def _dns_lookup_mx(domain: str, timeout: int = 5) -> List[str]:
    """Return MX hostnames for domain, prefer by priority."""
    hosts: List[str] = []
    if dns is None:
        return hosts
    try:
        answers = dns.resolver.resolve(domain, "MX", lifetime=timeout)
        # Sort by preference
        mx = sorted([(r.preference, str(r.exchange).rstrip(".")) for r in answers], key=lambda x: x[0])
        hosts = [h for _, h in mx]
    except Exception as e:  # pragma: no cover - network
        logger.debug("MX lookup failed", domain=domain, error=str(e))
    return hosts


def _dns_lookup_a(domain: str, timeout: int = 5) -> bool:
    """Return True if domain resolves to A/AAAA records.

    Uses socket.getaddrinfo as fallback.
    """
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def _connect_smtp_and_probe(mx_host: str, target: str, mail_from: str, timeout: int = 8) -> Tuple[int, str]:
    """Connect to MX host and run MAIL/RCPT. Returns (code, message)."""
    try:
        smtp = smtplib.SMTP(mx_host, 25, timeout=timeout)
        smtp.ehlo_or_helo_if_needed()
        # Use MAIL FROM with an invalid but syntactically correct domain to avoid accidental delivery
        code_mail, resp_mail = smtp.mail(mail_from)
        code_rcpt, resp_rcpt = smtp.rcpt(target)
        try:
            smtp.quit()
        except Exception:
            pass
        return code_rcpt, resp_rcpt.decode() if isinstance(resp_rcpt, bytes) else str(resp_rcpt)
    except Exception as e:
        logger.debug("SMTP probe connection failed", mx=mx_host, error=str(e))
        return 0, str(e)


def verify_email(email: str, enable_smtp: bool = False, settings: Any | None = None) -> Dict[str, Any]:
    """Verify the given email address.

    Returns a dictionary with keys: status, confidence, reasons, mx_hosts, is_catch_all, normalized_email

    - enable_smtp: attempt SMTP probe (may be rate-limited)
    - settings: optional app settings to read TTL/rate limits
    """
    # Load settings defaults
    ttl = 3600
    rate_limit = 60
    smtp_timeout = 8
    if settings is not None:
        try:
            ev = getattr(settings, "email_verification", None)
            if ev is not None:
                ttl = int(getattr(ev, "probe_cache_minutes", ttl)) * 60
                rate_limit = int(getattr(ev, "probe_rate_limit_seconds", rate_limit))
                smtp_timeout = int(getattr(ev, "smtp_timeout_seconds", smtp_timeout))
        except Exception:
            pass

    reasons: List[str] = []
    mx_hosts: List[str] = []
    is_catch_all: Optional[bool] = None
    normalized = None

    # Tier 1: Syntax validation
    try:
        validated = validate_email(email)
        normalized = validated.email
    except EmailNotValidError as e:
        return {
            "status": "syntax_invalid",
            "confidence": 1.0,
            "reasons": [str(e)],
            "mx_hosts": [],
            "is_catch_all": None,
            "normalized_email": None,
        }

    # Cache check by domain
    domain = normalized.split("@", 1)[1].lower()
    now = time.time()
    cache_key = f"{normalized}"
    cached = _probe_cache.get(cache_key)
    if cached and now - cached[1] < ttl:
        logger.debug("Returning cached verification result", email=normalized)
        res = cached[0]
        return {
            "status": res.status,
            "confidence": res.confidence,
            "reasons": res.reasons,
            "mx_hosts": res.mx_hosts,
            "is_catch_all": res.is_catch_all,
            "normalized_email": res.normalized_email,
        }

    # Tier 2: DNS MX lookup
    mx_hosts = _dns_lookup_mx(domain)
    if mx_hosts:
        reasons.append("mx_found")
    else:
        # Fallback to A/AAAA
        if _dns_lookup_a(domain):
            reasons.append("no_mx_a_found")
            # risky
            result = VerifyResult(
                status="risky",
                confidence=0.35,
                reasons=reasons,
                mx_hosts=[],
                is_catch_all=None,
                normalized_email=normalized,
            )
            _probe_cache[cache_key] = (result, now)
            return {
                "status": result.status,
                "confidence": result.confidence,
                "reasons": result.reasons,
                "mx_hosts": result.mx_hosts,
                "is_catch_all": result.is_catch_all,
                "normalized_email": result.normalized_email,
            }
        else:
            reasons.append("domain_not_resolvable")
            result = VerifyResult(
                status="invalid",
                confidence=0.9,
                reasons=reasons,
                mx_hosts=[],
                is_catch_all=None,
                normalized_email=normalized,
            )
            _probe_cache[cache_key] = (result, now)
            return {
                "status": result.status,
                "confidence": result.confidence,
                "reasons": result.reasons,
                "mx_hosts": result.mx_hosts,
                "is_catch_all": result.is_catch_all,
                "normalized_email": result.normalized_email,
            }

    # If we have MX records but SMTP probing disabled
    if not enable_smtp:
        reasons.append("smtp_probe_disabled")
        result = VerifyResult(
            status="smtp_probe_disabled",
            confidence=0.5,
            reasons=reasons,
            mx_hosts=mx_hosts,
            is_catch_all=None,
            normalized_email=normalized,
        )
        _probe_cache[cache_key] = (result, now)
        return {
            "status": result.status,
            "confidence": result.confidence,
            "reasons": result.reasons,
            "mx_hosts": result.mx_hosts,
            "is_catch_all": result.is_catch_all,
            "normalized_email": result.normalized_email,
        }

    # Rate limit per domain
    last = _last_probe_time.get(domain)
    if last and now - last < rate_limit:
        reasons.append("probe_rate_limited")
        result = VerifyResult(
            status="unknown",
            confidence=0.3,
            reasons=reasons,
            mx_hosts=mx_hosts,
            is_catch_all=None,
            normalized_email=normalized,
        )
        _probe_cache[cache_key] = (result, now)
        return {
            "status": result.status,
            "confidence": result.confidence,
            "reasons": result.reasons,
            "mx_hosts": result.mx_hosts,
            "is_catch_all": result.is_catch_all,
            "normalized_email": result.normalized_email,
        }

    # Tier 3: SMTP probe
    _last_probe_time[domain] = now
    is_accept_all = False
    probe_result_status = "unknown"
    probe_reasons: List[str] = []

    # Use a conservative MAIL FROM
    mail_from = "verifier@ourdomain.invalid"

    for mx in mx_hosts:
        code, resp = _connect_smtp_and_probe(mx, normalized, mail_from, timeout=smtp_timeout)
        if code in (250, 251):
            probe_result_status = "likely_valid"
            probe_reasons.append(f"rcpt_accepted_by_{mx}")
            break
        if code in (550, 551, 553):
            probe_result_status = "invalid_mailbox"
            probe_reasons.append(f"rcpt_rejected_by_{mx}")
            break
        if code in (450, 451, 452, 421, 0):
            probe_result_status = "unknown"
            probe_reasons.append(f"temp_error_or_timeout_{mx}")
            # try next MX

    # Detect accept-all by probing a random address
    random_local = f"probe-{random.randint(100000,999999)}"
    random_target = f"{random_local}@{domain}"
    for mx in mx_hosts[:3]:
        code_r, resp_r = _connect_smtp_and_probe(mx, random_target, mail_from, timeout=smtp_timeout)
        if code_r in (250, 251):
            # Random address accepted too -> accept-all
            is_accept_all = True
            probe_reasons.append(f"random_rcpt_accepted_by_{mx}")
            break

    # Map probe_result_status to final conservative statuses
    if is_accept_all:
        final_status = "accept_all"
        confidence = 0.6
    elif probe_result_status == "likely_valid":
        final_status = "valid"
        confidence = 0.9
    elif probe_result_status == "invalid_mailbox":
        final_status = "invalid"
        confidence = 0.95
    else:
        final_status = "unknown"
        confidence = 0.3

    reasons.extend(probe_reasons)

    result = VerifyResult(
        status=final_status,
        confidence=confidence,
        reasons=reasons,
        mx_hosts=mx_hosts,
        is_catch_all=is_accept_all,
        normalized_email=normalized,
    )

    _probe_cache[cache_key] = (result, now)

    return {
        "status": result.status,
        "confidence": result.confidence,
        "reasons": result.reasons,
        "mx_hosts": result.mx_hosts,
        "is_catch_all": result.is_catch_all,
        "normalized_email": result.normalized_email,
    }
