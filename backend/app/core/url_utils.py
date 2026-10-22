import ipaddress
import re
from urllib.parse import urlparse, urlunparse

BLOCKED_HOSTS = {
    "169.254.169.254",  # AWS/GCP/Azure link-local metadata
    "metadata.google.internal",
    "instance-data",
}

URL_REGEX = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)


def is_blocked_host(host: str | None) -> tuple[bool, str]:
    """Check if host is in SSRF blocklist or resolves to prohibited link-local/cloud metadata address."""
    if not host:
        return False, ""
    clean_host = host.strip("[]").lower()
    if clean_host in BLOCKED_HOSTS:
        return True, f"Security error: target host '{host}' is blocked to prevent SSRF."

    if clean_host in ("0.0.0.0", "fd00:ec2::254"):
        return True, f"Security error: target host '{host}' is blocked to prevent SSRF."

    try:
        ip = ipaddress.ip_address(clean_host)
        if ip.is_link_local:
            return True, f"Security error: target host '{host}' is a link-local address and blocked to prevent SSRF."
        if str(ip) in ("169.254.169.254",):
            return True, f"Security error: target host '{host}' is cloud metadata and blocked to prevent SSRF."
    except ValueError:
        pass

    return False, ""


def validate_and_normalize_url(url: str, allow_data_urls: bool = False) -> str:
    """Validate and normalize a target URL, preventing SSRF and scheme violations."""
    if not url:
        raise ValueError("URL cannot be empty.")

    clean_url = url.strip()

    if allow_data_urls and clean_url.startswith("data:"):
        return clean_url

    parsed = urlparse(clean_url)
    scheme = (parsed.scheme or "").lower()

    if scheme not in ("http", "https"):
        raise ValueError(f"Invalid URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

    if parsed.username or parsed.password or "@" in (parsed.netloc or ""):
        raise ValueError("Security violation: embedded user credentials in target URL are prohibited.")

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise ValueError(f"Invalid URL '{clean_url}': missing hostname.")

    blocked, reason = is_blocked_host(hostname)
    if blocked:
        raise ValueError(reason)

    # Normalize: strip trailing slash from base if path is empty or just '/'
    path = parsed.path or "/"
    normalized = urlunparse((
        scheme,
        parsed.netloc,
        path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))

    return normalized


def extract_target_url(text: str | None) -> str | None:
    """Extract and validate the first HTTP/HTTPS target URL from textual requirements or criteria."""
    if not text:
        return None

    match = URL_REGEX.search(text)
    if not match:
        return None

    candidate = match.group(0).rstrip(".,;!?:")
    try:
        return validate_and_normalize_url(candidate)
    except ValueError:
        return None


def resolve_navigation_url(step_url: str | None, base_url: str | None) -> str:
    """Resolve an action's navigation URL against an explicit base target URL.

    Raises a clear ValueError if a relative navigation is attempted without a valid target base URL.
    """
    raw = (step_url or "").strip()

    if raw.startswith("data:"):
        return raw

    if raw.startswith("http://") or raw.startswith("https://"):
        return validate_and_normalize_url(raw)

    # Relative navigation step
    if not base_url or not base_url.strip():
        raise ValueError(
            "Target URL is missing or undefined. A web test case requires a valid target website URL "
            "(e.g., 'https://example.com') in the requirement or test case to resolve relative navigation steps."
        )

    clean_base = validate_and_normalize_url(base_url.strip())
    parsed_base = urlparse(clean_base)
    base_root = f"{parsed_base.scheme}://{parsed_base.netloc}"

    if not raw or raw == "/":
        # If relative is root or empty, use base_url if it has a specific path, otherwise base_root/
        if parsed_base.path and parsed_base.path != "/":
            return clean_base
        return f"{base_root}/"

    # Relative path
    if raw.startswith("/"):
        # Absolute path relative to host
        full_url = f"{base_root}{raw}"
    else:
        # Relative to base path
        base_path = parsed_base.path.rstrip("/")
        full_url = f"{base_root}{base_path}/{raw}"

    return validate_and_normalize_url(full_url)
