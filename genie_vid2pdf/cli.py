import argparse
import sys
from pathlib import Path

from .converter import video_to_pdf


def main():
    parser = argparse.ArgumentParser(description="Convert meeting recording to PDF with subtitles")
    parser.add_argument("input", help="Path to video file (.mp4, .mov)")
    parser.add_argument("-o", "--output", help="Output PDF path (default: <input>.pdf)")
    parser.add_argument("--interval", type=float, default=30.0, help="Timed capture interval in seconds (default: 30)")
    parser.add_argument("--threshold", type=float, default=0.3, help="Scene change threshold 0-1 (default: 0.3)")
    parser.add_argument("--language", default="zh", help="Whisper language code (default: zh)")
    parser.add_argument("--transcript", default=None,
                        help="Existing transcript (.json/.srt) to reuse, skipping whisper")

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    output_path = args.output or str(input_path.with_suffix(".pdf"))

    def on_progress(stage, pct):
        stages = {
            "transcribing": "Transcribing audio",
            "extracting_frames": "Extracting frames",
            "burning_subtitles": "Burning subtitles",
            "generating_pdf": "Generating PDF",
        }
        label = stages.get(stage, stage)
        print(f"\r[{pct:.0%}] {label}...", end="", flush=True)

    print(f"Processing: {input_path}")
    result = video_to_pdf(
        str(input_path),
        output_path,
        interval=args.interval,
        scene_threshold=args.threshold,
        language=args.language,
        transcript_path=args.transcript,
        progress_callback=on_progress,
    )
    print(f"\nDone! PDF: {result['pdf']} ({result['frames']} frames, {result['segments']} segments)")


if __name__ == "__main__":
    main()
