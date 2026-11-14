"""Telegram's fake provisioning profiles have an ExpirationDate in the past, which
rules_apple rejects. Re-issue each profile with a far-future date, signed by a
throwaway self-signed certificate. The app is re-signed later anyway (Sideloadly)."""
import datetime
import glob
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile

root = sys.argv[1]
openssl = next((p for p in ["/opt/homebrew/opt/openssl@3/bin/openssl", "/usr/local/opt/openssl@3/bin/openssl"]
                if os.path.exists(p)), shutil.which("openssl"))
print("openssl:", openssl)

work = tempfile.mkdtemp()
key, cert = os.path.join(work, "key.pem"), os.path.join(work, "cert.pem")
subprocess.run([openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", key, "-out", cert,
                "-days", "3650", "-subj", "/CN=Fake Profile Signer"], check=True, capture_output=True)

future = datetime.datetime(2036, 1, 1, tzinfo=datetime.timezone.utc)
profiles = glob.glob(os.path.join(root, "**", "*.mobileprovision"), recursive=True)
for path in profiles:
    raw = os.path.join(work, "profile.plist")
    subprocess.run([openssl, "cms", "-verify", "-noverify", "-inform", "DER", "-in", path, "-out", raw],
                   check=True, capture_output=True)
    with open(raw, "rb") as f:
        data = plistlib.load(f)
    old = data.get("ExpirationDate")
    data["ExpirationDate"] = future
    data["CreationDate"] = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    with open(raw, "wb") as f:
        plistlib.dump(data, f)
    subprocess.run([openssl, "cms", "-sign", "-nodetach", "-binary", "-outform", "DER", "-signer", cert,
                    "-inkey", key, "-in", raw, "-out", path], check=True, capture_output=True)
    print(f"refreshed {os.path.relpath(path, root)} (was {old})")

print(f"{len(profiles)} profiles refreshed")
if not profiles:
    sys.exit("no provisioning profiles found")
