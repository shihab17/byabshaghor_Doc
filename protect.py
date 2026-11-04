"""Encrypt internal HTML pages — the file on disk becomes a PIN-gated lock
shell; the real content is AES-256-GCM ciphertext that only decrypts in the
browser with the right PIN.

Usage:  python docs/protect.py     (run AFTER build.py)
"""

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PIN = "1701"  # <- এখানে PIN বদলান (viewer.html-এর PIN-এর সাথে মিলিয়ে রাখুন)

DOCS = Path(__file__).parent

INTERNAL_FILES = [
    "competitor-analysis.html",
    "battlecards.html",
    "sales-playbook.html",
    "financial-model.html",
    "founders-agreement.html",
    "investor-agreement-guide.html",
    "company-setup-checklist.html",
    "company-setup.html",
    "founder-ops.html",
    "custom-domains.html",
    "job-orders-spec.html",
    "offline-sync-contract.html",
]

MARKER = "PG_PROTECTED_V1"

WRAPPER = """<!DOCTYPE html>
<html lang="bn">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Internal — ByabshaGhor</title>
<!-- PG_PROTECTED_V1 -->
<link href="https://fonts.googleapis.com/css2?family=Hind+Siliguri:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  body {{ margin:0; font-family:'Hind Siliguri',sans-serif; background:#0b1120; color:#f1f5f9;
         display:flex; align-items:center; justify-content:center; min-height:100vh; }}
  .box {{ background:#1e293b; border:1px solid rgba(148,163,184,.2); border-radius:16px;
          padding:36px 40px; text-align:center; max-width:380px; width:90%; }}
  .lock {{ font-size:44px; margin-bottom:12px; }}
  h1 {{ font-size:20px; margin:0 0 8px; }}
  p {{ color:#94a3b8; font-size:14px; margin:0 0 20px; }}
  input {{ background:#0b1120; border:1px solid rgba(148,163,184,.3); border-radius:10px;
           color:#f1f5f9; padding:11px 14px; font-size:17px; width:140px; text-align:center;
           letter-spacing:5px; font-family:inherit; }}
  button {{ background:rgba(34,197,94,.15); color:#22c55e; border:1px solid rgba(34,197,94,.4);
            border-radius:10px; padding:11px 22px; font-size:15px; font-weight:700;
            cursor:pointer; font-family:inherit; margin-left:8px; }}
  .err {{ color:#fca5a5; font-size:13px; margin-top:12px; display:none; }}
  .back {{ display:block; margin-top:18px; font-size:13px; color:#38bdf8; text-decoration:none; }}
</style>
</head>
<body>
<div class="box">
  <div class="lock">🔒</div>
  <h1>Internal Document</h1>
  <p>এই ডকুমেন্টটি টিমের জন্য — PIN দিন</p>
  <form onsubmit="tryUnlock(); return false;">
    <input id="pin" type="password" inputmode="numeric" maxlength="6" placeholder="PIN" autocomplete="off">
    <button type="submit">Unlock</button>
  </form>
  <div class="err" id="err">ভুল PIN বা ডেটা নষ্ট</div>
  <a class="back" href="viewer.html">← ডক লিস্টে ফিরুন</a>
</div>
<script>
const P = "{payload}";
const b64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));

async function unlock(pin) {{
  const raw = b64(P);
  const salt = raw.slice(0, 16), iv = raw.slice(16, 28), ct = raw.slice(28);
  const km = await crypto.subtle.importKey('raw', new TextEncoder().encode(pin),
    'PBKDF2', false, ['deriveKey']);
  const key = await crypto.subtle.deriveKey(
    {{ name:'PBKDF2', salt, iterations:100000, hash:'SHA-256' }},
    km, {{ name:'AES-GCM', length:256 }}, false, ['decrypt']);
  const pt = await crypto.subtle.decrypt({{ name:'AES-GCM', iv }}, key, ct);
  sessionStorage.setItem('docsPin', pin);
  document.open();
  document.write(new TextDecoder().decode(pt));
  document.close();
}}
async function tryUnlock() {{
  try {{ await unlock(document.getElementById('pin').value); }}
  catch(e) {{ document.getElementById('err').style.display = 'block'; }}
}}
(async () => {{
  const p = sessionStorage.getItem('docsPin');
  if (p) try {{ await unlock(p); }} catch(e) {{ sessionStorage.removeItem('docsPin'); }}
}})();
</script>
</body>
</html>
"""


def encrypt_html(html: str, pin: str) -> str:
    salt, iv = os.urandom(16), os.urandom(12)
    key = hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 100000, 32)
    ct = AESGCM(key).encrypt(iv, html.encode("utf-8"), None)
    payload = base64.b64encode(salt + iv + ct).decode()
    return WRAPPER.format(payload=payload)


def main() -> None:
    for name in INTERNAL_FILES:
        path = DOCS / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if MARKER in text:
            print(f"already locked {name}")
            continue
        path.write_text(encrypt_html(text, PIN), encoding="utf-8")
        print(f"locked {name}")


if __name__ == "__main__":
    main()
