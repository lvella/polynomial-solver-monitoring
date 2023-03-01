#!/usr/bin/env python3

import os
import re
import sys
from subprocess import run


def get_cpu_signature():
    identifying_elements_re = [
        r"^vendor_id\s*?: (.+?)$",
        r"^cpu family\s*?: (\d+)",
        r"^model\s*?: (\d+)",
        r"^stepping\s*?: (\d+)",
    ]

    with open("/proc/cpuinfo", "r") as cpuinfo:
        info = cpuinfo.read()

    signature = []
    for elem_re in identifying_elements_re:
        m = re.search(elem_re, info, re.M)
        if m:
            signature.append(m.group(1))

    return "_".join(signature)


def main():
    script_path = os.path.dirname(os.path.abspath(__file__))

    try:
        git_repo = sys.argv[1]
    except IndexError:
        print("Error: missing path to git repo")
        sys.exit(1)

    # Test if git repo is clean
    os.chdir(git_repo)
    r = run("git status --untracked-files=no --porcelain".split(), capture_output=True)
    r.check_returncode()
    if r.stdout:
        print("Error: repository is not clean")
        sys.exit(1)

    run("git fetch --tags".split()).check_returncode()

    # Get monitoring tags
    r = run("git show-ref --tags".split(), capture_output=True)
    r.check_returncode()
    tags = [tuple(hash_tag.split()) for hash_tag in r.stdout.splitlines()]

    # Filter monitoring tags
    mon_tag_re = re.compile(rb"^refs/tags/(mon.\d+)$")
    tags = [
        (hash.decode("ascii"), tag.group(1).decode("ascii"))
        for (hash, tag) in ((hash, mon_tag_re.match(tag)) for (hash, tag) in tags)
        if tag
    ]

    # Create the output directory for this particular processor if it doesn't
    # exist yet:
    outdir = os.path.join(script_path, "runs", get_cpu_signature())
    try:
        os.makedirs(outdir)
    except FileExistsError:
        # directory already exists
        pass

    # Run each of them that is not already present:
    tmp_filename = os.path.join(script_path, "tmp_out.csv")
    for (hash, tag) in tags:
        final_path_name = os.path.join(outdir, f"run.{tag}.{hash}.csv")
        if os.path.exists(final_path_name):
            print(f"Skipping tag {tag} ({hash}) because it is already there")
            continue
        else:
            print(f"Computing tag {tag} ({hash})")

        run(["git", "checkout", hash]).check_returncode()
        with open(tmp_filename, "wb") as output:
            r = run("cargo bench --bench monitoring".split(), stdout=output)
        if r.returncode == 0:
            os.rename(tmp_filename, final_path_name)
        else:
            print(f"Something went wrong with tag {tag} ({hash})")


if __name__ == "__main__":
    main()
