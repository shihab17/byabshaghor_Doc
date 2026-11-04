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
<title>Internal — ব্যবসাঘর</title>
<!-- PG_PROTECTED_V1 -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Anek+Bangla:wght@400;600;700&family=Plus+Jakarta+Sans:wght@500;600;700&display=swap" rel="stylesheet">
<style>
  body {{
    margin: 0; font-family: 'Anek Bangla', 'Hind Siliguri', sans-serif;
    background-color: #050814;
    background-image: 
      radial-gradient(circle at 50% 0%, rgba(99, 102, 241, 0.12), transparent 50%),
      radial-gradient(circle at 100% 100%, rgba(0, 242, 169, 0.08), transparent 50%);
    color: #f8fafc;
    display: flex; align-items: center; justify-content: center; min-height: 100vh;
  }}
  .box {{
    background: rgba(16, 23, 44, 0.75);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.09);
    border-top: 1px solid rgba(255, 255, 255, 0.18);
    border-radius: 20px;
    padding: 40px 44px; text-align: center; max-width: 400px; width: 90%;
    box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.8), 0 0 30px rgba(0, 242, 169, 0.08);
  }}
  .lock {{
    font-size: 46px; margin-bottom: 12px;
    filter: drop-shadow(0 0 16px rgba(245, 158, 11, 0.4));
  }}
  h1 {{
    font-size: 22px; font-weight: 700; margin: 0 0 8px; color: #fff;
    letter-spacing: -0.3px;
  }}
  p {{ color: #94a3b8; font-size: 14.5px; margin: 0 0 24px; line-height: 1.55; }}
  input {{
    background: rgba(11, 17, 32, 0.85);
    border: 1px solid rgba(255, 255, 255, 0.12);
    border-radius: 12px;
    color: #fff; padding: 11px 16px; font-size: 18px; width: 140px; text-align: center;
    letter-spacing: 6px; font-family: 'Plus Jakarta Sans', sans-serif;
    outline: none; transition: border-color 0.2s, box-shadow 0.2s;
  }}
  input:focus {{
    border-color: #00f2a9;
    box-shadow: 0 0 15px rgba(0, 242, 169, 0.25);
  }}
  button {{
    background: #00f2a9; color: #04120a;
    border: none;
    border-radius: 12px; padding: 12px 24px; font-size: 15px; font-weight: 700;
    cursor: pointer; font-family: 'Plus Jakarta Sans', sans-serif; margin-left: 8px;
    transition: all 0.2s; box-shadow: 0 4px 14px rgba(0, 242, 169, 0.3);
  }}
  button:hover {{
    filter: brightness(1.1); transform: translateY(-1px);
    box-shadow: 0 6px 20px rgba(0, 242, 169, 0.45);
  }}
  .err {{ color: #fca5a5; font-size: 13.5px; margin-top: 14px; display: none; font-weight: 600; }}
  .back {{
    display: inline-block; margin-top: 22px; font-size: 13.5px; color: #38bdf8;
    text-decoration: none; font-weight: 600; transition: color 0.15s;
  }}
  .back:hover {{ color: #bae6fd; text-decoration: underline; }}
</style>
</head>
<body>
<div class="box">
  <div class="lock">🔒</div>
  <h1>সুরক্ষিত ইন্টারনাল ডকুমেন্ট</h1>
  <p>এই ডকুমেন্টটি টিমের গোপনীয় ব্যবহারের জন্য — অনুগ্রহ করে ৬ ডিজিটের PIN দিন</p>
  <form onsubmit="tryUnlock(); return false;">
    <input id="pin" type="password" inputmode="numeric" maxlength="6" placeholder="PIN" autocomplete="off">
    <button type="submit">Unlock</button>
  </form>
  <div class="err" id="err">⚠️ ভুল PIN বা ডেটা নষ্ট হয়েছে</div>
  <a class="back" href="viewer.html">← ডক সেন্টারে ফিরে যান</a>
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

def derive_key(pin: str, salt: bytes) -> bytes:
    # PBKDF2-HMAC-SHA256 matching WebCrypto PBKDF2
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, 100_000, dklen=32)

def encrypt(html_bytes: bytes, pin: str) -> str:
    salt = os.urandom(16)
    iv = os.urandom(12)
    key = derive_key(pin, salt)
    ct = AESGCM(key).encrypt(iv, html_bytes, None)
    return base64.b64encode(salt + iv + ct).decode()

def main() -> None:
    for name in INTERNAL_FILES:
        path = DOCS / name
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8")
        if MARKER in content:
            continue  # already protected
        payload = encrypt(content.encode("utf-8"), PIN)
        path.write_text(WRAPPER.format(payload=payload), encoding="utf-8")
        print(f"protected {name}")

if __name__ == "__main__":
    main()
