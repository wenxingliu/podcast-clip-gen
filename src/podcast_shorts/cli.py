from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .cutter import run_cut
from .renderer import run_render


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="podcast-clips", description="Local podcast clipping and branded audiogram generation")
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)

    cut = commands.add_parser("cut", help="align marked transcript selections and export audio clips")
    cut.add_argument("--audio", required=True)
    cut.add_argument("--transcript", required=True)
    cut.add_argument("--out", required=True)
    cut.add_argument("--episode-id")
    cut.add_argument("--alignment", help="existing Whisper/WhisperX JSON (skips ASR)")
    cut.add_argument("--overrides", help="JSON mapping clip IDs to start_sec/end_sec")
    cut.add_argument("--padding-ms", type=int, default=150)
    cut.add_argument("--confidence-threshold", type=float, default=.78)
    cut.add_argument("--ambiguity-margin", type=float, default=.04)
    cut.add_argument("--format", choices=["mp3", "wav"], default="mp3")
    cut.add_argument("--dry-run", action="store_true")
    cut.add_argument("--model", default="small", help="faster-whisper model name")
    cut.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")

    render = commands.add_parser("render", help="render branded videos from a manifest or standalone clip")
    render.add_argument("--manifest")
    render.add_argument("--audio")
    render.add_argument("--timed-transcript")
    render.add_argument("--cover", required=True)
    render.add_argument("--config")
    render.add_argument("--out", required=True)
    render.add_argument("--clip-id")

    all_cmd = commands.add_parser("all", help="cut clips then render all successfully exported clips")
    all_cmd.add_argument("--audio", required=True)
    all_cmd.add_argument("--transcript", required=True)
    all_cmd.add_argument("--cover", required=True)
    all_cmd.add_argument("--config")
    all_cmd.add_argument("--out", required=True)
    all_cmd.add_argument("--episode-id")
    all_cmd.add_argument("--alignment")
    all_cmd.add_argument("--overrides")
    all_cmd.add_argument("--padding-ms", type=int, default=150)
    all_cmd.add_argument("--confidence-threshold", type=float, default=.78)
    all_cmd.add_argument("--ambiguity-margin", type=float, default=.04)
    all_cmd.add_argument("--format", choices=["mp3", "wav"], default="mp3")
    all_cmd.add_argument("--model", default="small")
    all_cmd.add_argument("--device", choices=["cpu", "cuda", "auto"], default="cpu")
    return root


def _cut_args(args: argparse.Namespace) -> dict:
    return {
        "audio": args.audio, "transcript": args.transcript, "out": args.out,
        "episode_id": args.episode_id, "alignment": args.alignment,
        "overrides": args.overrides, "padding_ms": args.padding_ms,
        "threshold": args.confidence_threshold,
        "ambiguity_margin": args.ambiguity_margin,
        "output_format": args.format, "dry_run": getattr(args, "dry_run", False),
        "model": args.model, "device": args.device,
    }


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    try:
        if args.command == "cut":
            values = _cut_args(args)
            manifest, code = run_cut(**values)
            print(json.dumps({"manifest": str(Path(args.out).resolve() / "manifest.json"), "clips": len(manifest["clips"])}, ensure_ascii=False))
            return code
        if args.command == "render":
            report, code = run_render(manifest_path=args.manifest, audio_path=args.audio, timed_path=args.timed_transcript, cover_path=args.cover, config_path=args.config, out=args.out, clip_id=args.clip_id)
            print(json.dumps({"render_report": str(Path(args.out).resolve() / "render-report.json"), "renders": len(report["renders"])}, ensure_ascii=False))
            return code
        values = _cut_args(args)
        values["dry_run"] = False
        _, cut_code = run_cut(**values)
        report, render_code = run_render(manifest_path=str(Path(args.out) / "manifest.json"), audio_path=None, timed_path=None, cover_path=args.cover, config_path=args.config, out=str(Path(args.out) / "videos"))
        print(json.dumps({"manifest": str(Path(args.out).resolve() / "manifest.json"), "renders": len(report["renders"])}, ensure_ascii=False))
        return max(cut_code, render_code)
    except (ValueError, RuntimeError, FileNotFoundError) as exc:
        logging.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())

