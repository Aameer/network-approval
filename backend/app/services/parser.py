"""Inbox parser — reads the holding-co mailbox over IMAP, finds network-approval
emails, and extracts a candidate Publisher ID. Degrades gracefully with a clear
message if not configured or if Gmail rejects the password (needs an App Password).
"""
from __future__ import annotations

import email
import imaplib
import re
from email.header import decode_header, make_header

from ..config import PARSER_EMAIL, PARSER_IMAP_HOST, PARSER_PASSWORD

_PUB_RE = re.compile(r"(?:publisher|pub|affiliate)\s*(?:id|#)?\s*[:#]?\s*([A-Za-z0-9][A-Za-z0-9\-]{3,})", re.I)
_APPROVE_KW = ("approved", "approval", "welcome", "accepted", "publisher", "activated")


def configured() -> bool:
    return bool(PARSER_IMAP_HOST and PARSER_EMAIL and PARSER_PASSWORD)


def _text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="replace")
                except Exception:
                    pass
        return ""
    try:
        return msg.get_payload(decode=True).decode(errors="replace")
    except Exception:
        return str(msg.get_payload())


def scan_inbox(limit: int = 15) -> dict:
    if not configured():
        return {"error": "inbox parser not configured (PARSER_EMAIL / PARSER_PASSWORD)"}
    try:
        M = imaplib.IMAP4_SSL(PARSER_IMAP_HOST)
        M.login(PARSER_EMAIL, PARSER_PASSWORD)
    except imaplib.IMAP4.error as e:
        return {"error": f"IMAP login failed ({e}). Gmail needs an App Password (enable 2FA, then "
                         "Google Account → Security → App passwords) — a normal password won't work."}
    except Exception as e:
        return {"error": f"IMAP connect failed: {type(e).__name__}: {e}"}
    try:
        M.select("INBOX")
        _typ, data = M.search(None, "ALL")
        ids = data[0].split()[-limit:]
        results = []
        for i in reversed(ids):
            _typ, msg_data = M.fetch(i, "(RFC822)")
            msg = email.message_from_bytes(msg_data[0][1])
            subj = str(make_header(decode_header(msg.get("Subject", ""))))
            frm = str(make_header(decode_header(msg.get("From", ""))))
            body = _text(msg)
            blob = f"{subj}\n{body}"
            approval = any(k in blob.lower() for k in _APPROVE_KW)
            pub = None
            m = _PUB_RE.search(blob)
            if m:
                pub = m.group(1)
            results.append({"from": frm, "subject": subj,
                            "looks_like_approval": approval, "publisher_id": pub})
        M.logout()
        approvals = [r for r in results if r["looks_like_approval"]]
        return {"mailbox": PARSER_EMAIL, "scanned": len(results),
                "approvals_found": len(approvals), "approvals": approvals, "recent": results}
    except Exception as e:
        try:
            M.logout()
        except Exception:
            pass
        return {"error": f"IMAP read failed: {type(e).__name__}: {e}"}
