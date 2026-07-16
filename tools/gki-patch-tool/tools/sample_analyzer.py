#!/usr/bin/env python3
"""Random sample analysis: pick N commits from a tag range and run patch_analyzer on them."""
import json
import random
import sys
import time
from pathlib import Path

# Import from the main analyzer
sys.path.insert(0, str(Path(__file__).parent))
from cli_config import (
    add_settings_argument,
    get_analysis_options,
    get_repo_dir,
    load_settings,
    sample_analyzer_defaults,
    strip_settings_from_argv,
)
from patch_analyzer import (
    CommitItem,
    analyze_commit,
    build_summary,
    fetch_commits_between_tags,
    load_config,
    normalize_repo_url,
    run_parallel_analysis,
)


def main():
    import argparse

    settings_path, argv_rest = strip_settings_from_argv(sys.argv[1:])
    settings, loaded_from = load_settings(settings_path)
    defaults = sample_analyzer_defaults(settings)
    analysis = get_analysis_options(settings)

    parser = argparse.ArgumentParser(description="Random sample patch analysis")
    add_settings_argument(parser)
    parser.add_argument("--repo", default=defaults["repo"])
    parser.add_argument("--from-tag", required=True)
    parser.add_argument("--to-tag", required=True)
    parser.add_argument("--config", default=defaults["config"])
    parser.add_argument("--sample-size", type=int, default=defaults["sample_size"])
    parser.add_argument("--repo-dir", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument("--seed", type=int, default=defaults["seed"])
    args = parser.parse_args(argv_rest)

    if loaded_from:
        print(f"[config] 已加载: {loaded_from}", file=sys.stderr)

    random.seed(args.seed)

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"错误: 评分配置文件不存在: {config_path}", file=sys.stderr)
        return 2

    config = load_config(config_path)
    repo = normalize_repo_url(args.repo)
    repo_dir = get_repo_dir(settings, cli_repo_dir=args.repo_dir)
    if args.output:
        out_path = Path(args.output).expanduser()
        if not out_path.is_absolute():
            out_path = (Path.cwd() / out_path).resolve()
    else:
        out_path = Path(defaults["output"])

    print(f"[1/3] Fetching commit list between {args.from_tag} and {args.to_tag} ...", file=sys.stderr)
    all_commits = fetch_commits_between_tags(repo, args.from_tag, args.to_tag, repo_dir=repo_dir)
    total = len(all_commits)
    print(f"[1/3] Total commits: {total}", file=sys.stderr)

    sample_size = min(args.sample_size, total)
    sampled = random.sample(all_commits, sample_size)
    sampled.sort(key=lambda c: c.sha)
    print(f"[2/3] Sampled {sample_size} commits (seed={args.seed}), analyzing ...", file=sys.stderr)

    patches, failures = run_parallel_analysis(
        repo_url=repo,
        commits=sampled,
        config=config,
        workers=max(1, analysis["workers"]),
        chunk_size=max(1, min(analysis["chunk_size"], sample_size)),
        retry=max(0, analysis["retry"]),
        repo_dir=repo_dir,
    )
    patches.sort(key=lambda x: x["commit"])

    output = {
        "repo": repo,
        "from_tag": args.from_tag,
        "to_tag": args.to_tag,
        "total": total,
        "sampled": sample_size,
        "analyzed": len(patches),
        "failed": len(failures),
        "failed_items": failures,
        "summary": build_summary(patches),
        "patches": patches,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[3/3] Done: analyzed={len(patches)}, failed={len(failures)}, output={out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
