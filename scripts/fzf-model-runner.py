#!/usr/bin/env python3

import argparse
import configparser
import os
import re
import socket
import subprocess
import sys
from pathlib import Path


SKIP_OPTIONS = {"alias", "host", "load-on-startup", "port", "stop-timeout"}


def load_profiles(preset):
    text = re.sub(r"^\s*version\s*=.*\n", "", preset.read_text(), count=1, flags=re.M)
    config = configparser.ConfigParser(interpolation=None)
    config.read_string(text)
    profiles = [name for name in config.sections() if name != "*"]
    return config, profiles


def select(options, prompt):
    try:
        result = subprocess.run(
            ["fzf", f"--prompt={prompt}"],
            input="\n".join(options) + "\n",
            text=True,
            stdout=subprocess.PIPE,
            check=False,
        )
    except FileNotFoundError:
        sys.exit("fzf is not installed")
    return result.stdout.strip() if result.returncode == 0 else ""


def port_in_use(host, port):
    with socket.socket() as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def profile_options(config, profile):
    options = dict(config["*"]) if config.has_section("*") else {}
    options.update(config[profile])
    return options


def make_command(server, config, profile, context_size, host, port):
    options = profile_options(config, profile)
    options["ctx-size"] = context_size
    if not options.get("model") and not options.get("hf-repo"):
        sys.exit(f"profile {profile!r} has no model or hf-repo")

    command = [str(server)]
    for key, value in options.items():
        if key in SKIP_OPTIONS:
            continue
        if value == "true":
            command.append(f"--{key}")
        elif value == "false":
            command.append(f"--no-{key}")
        else:
            command.extend((f"--{key}", value))

    return command + ["--alias", profile, "--host", host, "--port", str(port)]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("preset", type=Path)
    parser.add_argument("server", type=Path)
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--context-sizes", default="4096,8192,12288,16384")
    args = parser.parse_args()

    config, profiles = load_profiles(args.preset)
    if args.list:
        print("\n".join(profiles))
        return
    if not profiles:
        sys.exit("no model profiles found")
    if port_in_use(args.host, args.port):
        sys.exit(f"{args.host}:{args.port} is already in use; refusing to start")

    profile = select(profiles, "Model> ")
    if not profile:
        return

    context_sizes = [size.strip() for size in args.context_sizes.split(",") if size.strip()]
    if not context_sizes or not all(size.isdigit() and int(size) > 0 for size in context_sizes):
        sys.exit("context sizes must be positive integers")
    profile_context = profile_options(config, profile).get("ctx-size")
    if profile_context and profile_context.isdigit():
        context_sizes = [size for size in context_sizes if int(size) <= int(profile_context)]
        context_sizes = [profile_context] + [size for size in context_sizes if size != profile_context]
    context_size = select(context_sizes, "Context> ")
    if not context_size:
        return
    os.execv(args.server, make_command(args.server, config, profile, context_size, args.host, args.port))


if __name__ == "__main__":
    main()
