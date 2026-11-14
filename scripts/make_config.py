"""Build config for Telegram-iOS from the official template + repository secrets."""
import json
import os
import sys

template_path, output_path = sys.argv[1], sys.argv[2]
api_id = os.environ.get("TG_API_ID", "").strip()
api_hash = os.environ.get("TG_API_HASH", "").strip()
if not api_id or not api_hash:
    print("::error::Add repository secrets TG_API_ID and TG_API_HASH (Settings > Secrets and variables > Actions)")
    sys.exit(1)

with open(template_path) as f:
    config = json.load(f)

config["api_id"] = api_id
config["api_hash"] = api_hash
config["is_appstore_build"] = "false"
config["enable_siri"] = False
config["enable_icloud"] = False

with open(output_path, "w") as f:
    json.dump(config, f, indent=2)
print("Configuration written; bundle_id =", config["bundle_id"])
