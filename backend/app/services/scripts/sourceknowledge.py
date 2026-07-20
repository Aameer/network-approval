"""Deterministic Playwright script for SourceKnowledge (a 'head' network).

Reliable + fast (~10-30s) execution AND verification without Skyvern's LLM agent. This is the
per-network DOM engineering the head/tail strategy trades for: pay it once for a high-volume
network, then replay deterministically forever. A plain browser can genuinely reload + read
back (it never lies), so verification is trustworthy here — unlike the agent's self-report.
"""
from __future__ import annotations

from .base import browser_session, norm

NETWORK = "SourceKnowledge"
NEEDS_PROXY = False   # SourceKnowledge admits a plain headless browser; no residential proxy needed

LOGIN_URL = "https://app.sourceknowledge.com/login"
PROFILE_URL = "https://app.sourceknowledge.com/ui/publisher/profile"

# SourceKnowledge field label -> our canonical key
LABEL_TO_KEY = {
    "First Name": "first_name", "Last Name": "last_name", "Country": "country",
    "State/Province": "state", "Street Address": "address1", "Suite": "address2",
    "City": "city", "Zip/Postal Code": "zip_code", "Phone Number": "phone",
    "Business Name": "company_name", "URL": "website_url",
}
KEY_TO_LABEL = {v: k for k, v in LABEL_TO_KEY.items()}
DROPDOWN_KEYS = {"country", "state"}
DROPDOWN_IDS = {"country": "profile_contactInfo_countryCode",
                "state": "profile_contactInfo_regionCode"}
READONLY_KEYS = {"company_name", "email"}  # not editable on this form


def _login(page, creds):
    page.goto(LOGIN_URL, wait_until="networkidle", timeout=45000)
    page.fill("#username", creds["username"])
    page.fill("#password", creds["password"])
    page.click("button:has-text('SIGN IN')")
    page.wait_for_url(lambda u: "/login" not in u, timeout=30000)


def _open_profile(page):
    page.goto(PROFILE_URL, wait_until="networkidle", timeout=45000)
    # The form data loads async — wait until it's actually POPULATED (First Name has a value),
    # not merely rendered. Submitting before this leaves required fields empty -> save blocked.
    page.wait_for_function(
        "() => {const i=[...document.querySelectorAll('input')].find(e => e.labels && e.labels[0]"
        " && e.labels[0].innerText.trim()==='First Name'); return i && i.value.length>0;}",
        timeout=20000)
    page.wait_for_timeout(600)


def _item(page, label):
    """The Ant form-item container for a given field label."""
    return page.locator(
        f"//label[normalize-space()='{label}']/ancestor::*[contains(@class,'ant-form-item')][1]"
    ).first


def _read_all(page) -> dict:
    """Current persisted values on the profile page -> {key: value} (inputs + dropdowns)."""
    out = {}
    data = page.eval_on_selector_all("input", """els => els.map(e => ({
        label:(e.labels && e.labels[0] ? e.labels[0].innerText.trim() : null), value:e.value}))""")
    for d in data:
        k = LABEL_TO_KEY.get(d.get("label"))
        if k and k not in DROPDOWN_KEYS:
            out[k] = d.get("value") or ""
    for k in DROPDOWN_KEYS:
        try:
            item = (page.locator(f"#{DROPDOWN_IDS[k]}")
                    .locator("xpath=ancestor::div[contains(@class,'ant-select')][1]")
                    .locator(".ant-select-selection-item").first)
            out[k] = (item.inner_text(timeout=3000) or "").strip()
        except Exception:  # noqa: BLE001
            out[k] = ""
    return out


def _set_dropdown(page, key, value):
    """Select an option in an Ant Design Select that is NOT search-filterable and uses a VIRTUAL
    LIST (only ~33 options rendered at a time). Open the box, scroll the virtual list until the
    exact option (matched by its title attr) renders, click it, then CONFIRM the box now shows the
    chosen value — retry once if the click didn't take. Raises if it truly won't accept the value."""
    box = (page.locator(f"#{DROPDOWN_IDS[key]}")
           .locator("xpath=ancestor::div[contains(@class,'ant-select')][1]"))
    opt = page.locator(f"[class*='ant-select-item-option'][title='{value}']")
    cur = ""
    for _ in range(2):
        box.click()                       # the #input is covered by the display span; click the box
        page.wait_for_timeout(400)
        holder = page.locator(".rc-virtual-list-holder").first
        if holder.count():
            holder.evaluate("el => el.scrollTop = 0")
            page.wait_for_timeout(120)
            for _ in range(80):
                if opt.count() and opt.first.is_visible():
                    break
                holder.evaluate("el => el.scrollTop += 240")
                page.wait_for_timeout(60)
        try:
            opt.first.click(timeout=3000)
        except Exception:  # noqa: BLE001
            page.keyboard.press("Escape")
            continue
        page.wait_for_timeout(400)
        cur = (box.locator(".ant-select-selection-item").first.inner_text(timeout=2000) or "").strip()
        if norm(cur) == norm(value):
            return
        page.keyboard.press("Escape")     # click didn't take — close and retry
    raise RuntimeError(f"dropdown {key} did not accept {value!r} (shows {cur!r})")


def _set_field(page, key, value):
    label = KEY_TO_LABEL.get(key)
    if not label:
        return False
    if key in DROPDOWN_KEYS:
        _set_dropdown(page, key, value)
    else:
        inp = page.get_by_label(label, exact=True)
        inp.fill(str(value), timeout=8000)
    return True


def read_profile(creds, keys=None) -> dict:
    """Independent deterministic read (the verifier). Returns {key: current_value}."""
    with browser_session(use_default_proxy=NEEDS_PROXY) as page:
        _login(page, creds)
        _open_profile(page)
        vals = _read_all(page)
    return {k: v for k, v in vals.items() if (keys is None or k in keys)}


def update_profile(creds, fields: dict) -> dict:
    """Deterministic update: fill ONLY the given fields, click the bottom Submit, then RELOAD and
    read back to verify persistence. Returns per-field verified/unverified + timing."""
    import time
    fields = {k: v for k, v in (fields or {}).items()
              if k in KEY_TO_LABEL and k not in READONLY_KEYS}
    t0 = time.time()
    result = {"engine": "script", "network": "SourceKnowledge", "submitted": fields}
    with browser_session(use_default_proxy=NEEDS_PROXY) as page:
        _login(page, creds)
        _open_profile(page)
        for k, v in fields.items():
            try:
                _set_field(page, k, v)
            except Exception as exc:  # noqa: BLE001
                result.setdefault("errors", {})[k] = f"set: {type(exc).__name__}"
        # scroll to the bottom and click the single Submit button
        page.mouse.wheel(0, 30000)
        page.wait_for_timeout(500)
        submit = page.locator("button:has-text('Submit'), button:has-text('SUBMIT'), "
                              "button:has-text('Save'), button:has-text('Update')").last
        submit.scroll_into_view_if_needed(timeout=5000)
        submit.click(timeout=8000)
        result["submit_clicked"] = True
        page.wait_for_timeout(2500)  # let the save round-trip
        # INDEPENDENT VERIFY: reload the page and read the PERSISTED values
        _open_profile(page)
        persisted = _read_all(page)
    verified = {k: v for k, v in fields.items() if norm(persisted.get(k)) == norm(v)}
    unverified = {k: v for k, v in fields.items() if k not in verified}
    result.update({
        "persisted": {k: persisted.get(k) for k in fields},
        "verified": sorted(verified), "unverified": sorted(unverified),
        "fully_verified": len(unverified) == 0,
        "seconds": round(time.time() - t0, 1),
    })
    return result
