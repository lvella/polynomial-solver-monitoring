#!/usr/bin/env python3

import os
import re
import sys
from subprocess import run


def main():
    script_path = os.path.dirname(os.path.abspath(__file__))

    try:
        git_repo = sys.argv[1]
    except IndexError:
        print("Error: missing path to git repo")
        sys.exit(1)

    # Test if git repo is clean
    os.chdir(git_repo)
    r = run(
        "git status --untracked-files=no --porcelain".split(), capture_output=True)
    r.check_returncode()
    if r.stdout:
        print("Error: repository is not clean")
        sys.exit(1)

    run("git fetch --tags".split()).check_returncode()

    # Get monitoring tags
    r = run("git show-ref --tags".split(),
            capture_output=True)
    r.check_returncode()
    tags = [tuple(hash_tag.split()) for hash_tag in r.stdout.splitlines()]

    # Filter monitoring tags
    mon_tag_re = re.compile(rb"^refs/tags/(mon.\d+)$")
    tags = [(hash.decode("ascii"), tag.group(1).decode("ascii")) for (hash, tag) in ((hash, mon_tag_re.match(tag))
                                                                                     for (hash, tag) in tags) if tag]

    # Just run each of them:
    tmp_filename = os.path.join(script_path, "tmp_out.csv")
    for (hash, tag) in tags:
        run(["git", "checkout", hash]).check_returncode()
        with open(tmp_filename, "wb") as output:
            r = run("cargo bench --bench monitoring".split(), stdout=output)
        if r.returncode == 0:
            os.rename(tmp_filename, f"run.{tag}.{hash}.csv")
        else:
            print(f"Something went wrong with tag {tag} ({hash})")


if __name__ == "__main__":
    main()
