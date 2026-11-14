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

IOS27_MARKERS = ["reservedRegions"]


def uses_newer_sdk(rev):
    # Code adopting the next iOS SDK can land before versions.json is bumped.
    result = subprocess.run(["git", "-C", dest, "grep", "-l", "-e", IOS27_MARKERS[0], rev, "--",
                             "submodules/Display"], text=True, capture_output=True)
    return bool(result.stdout.strip())


candidates = []
for index, sha in enumerate(history):
    required = version_tuple(json.loads(out("git", "-C", dest, "show", f"{sha}:versions.json"))["xcode"])
    print(sha[:10], "requires Xcode", required, out("git", "-C", dest, "log", "-1", "--format=%cd", sha).strip())
    if required <= installed:
        if index > 0:
            candidates.append(history[index - 1] + "^")
        candidates.append(sha)
        candidates.extend(history[index + 1:index + 4])
        break

target = None
for rev in candidates:
    if uses_newer_sdk(rev):
        print(rev, "already uses a newer SDK, going back")
        continue
    target = rev
    break
if target is None:
    sys.exit("No compatible Telegram version found")

run("git", "-C", dest, "checkout", "-q", target)
print("Checked out:", out("git", "-C", dest, "log", "-1", "--format=%H %cd %s").strip())
print("versions.json:", out("git", "-C", dest, "show", "HEAD:versions.json"))
run("git", "-C", dest, "submodule", "update", "--init", "--recursive", "--depth", "1", "--jobs", "8")
