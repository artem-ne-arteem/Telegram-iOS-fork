"""Clone Telegram-iOS at the newest commit whose versions.json targets an Xcode
the runner actually has (e.g. 26.x), then fetch submodules for that commit."""
import json
import re
import subprocess
import sys

dest = sys.argv[1]
url = "https://github.com/TelegramMessenger/Telegram-iOS.git"


def run(*args, **kwargs):
    print("+", " ".join(args), flush=True)
    return subprocess.run(args, check=True, text=True, **kwargs)


def out(*args):
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def version_tuple(text):
    return tuple(int(x) for x in re.findall(r"\d+", text)[:2])


installed = version_tuple(re.search(r"Xcode (\S+)", out("xcodebuild", "-version")).group(1))
print("Installed Xcode:", installed)

run("git", "clone", "--filter=blob:none", "--no-checkout", url, dest)
history = out("git", "-C", dest, "log", "--format=%H", "origin/HEAD", "--", "versions.json").split()

target = "origin/HEAD"
for index, sha in enumerate(history):
    required = version_tuple(json.loads(out("git", "-C", dest, "show", f"{sha}:versions.json"))["xcode"])
    print(sha[:10], "requires Xcode", required)
    if required <= installed:
        if index > 0:
            # The newest state before the Xcode requirement was raised above ours.
            target = history[index - 1] + "^"
        break
else:
    sys.exit("No compatible Telegram version found")

run("git", "-C", dest, "checkout", "-q", target)
print("Checked out:", out("git", "-C", dest, "log", "-1", "--format=%H %cd %s").strip())
print("versions.json:", out("git", "-C", dest, "show", "HEAD:versions.json"))
run("git", "-C", dest, "submodule", "update", "--init", "--recursive", "--depth", "1", "--jobs", "8")
