import tempfile
from pathlib import Path

from PIL import Image

from genie_core.audio import transcribe_audio
from genie_core.video.screenshot import extract_screenshots, burn_subtitle


def video_to_pdf(
    video_path: str,
    output_pdf: str,
    interval: float = 30.0,
    scene_threshold: float = 0.3,
    language: str = "zh-Hans",
    progress_callback=None,
) -> dict:
    """Convert a video file to PDF with screenshots and subtitles.

    Returns {"pdf": str, "frames": int, "segments": int}.
    """
    video_path = str(video_path)
    output_pdf = str(output_pdf)

    with tempfile.TemporaryDirectory() as tmpdir:
        frames_dir = Path(tmpdir) / "frames"
        burned_dir = Path(tmpdir) / "burned"
        burned_dir.mkdir()

        # Step 1: Transcribe audio
        if progress_callback:
            progress_callback("transcribing", 0)
        segments = transcribe_audio(video_path, language=language)

        # Step 2: Extract screenshots at scene changes + intervals
        if progress_callback:
            progress_callback("extracting_frames", 0.2)
        screenshots = extract_screenshots(
            video_path, str(frames_dir),
            interval=interval,
            scene_threshold=scene_threshold,
        )

        # Step 3: Match subtitles to screenshots and burn text
        if progress_callback:
            progress_callback("burning_subtitles", 0.5)

        burned_frames = []
        for i, shot in enumerate(screenshots):
            subtitle_text = _get_subtitle_for_time(segments, shot["time"], interval)

            if subtitle_text:
                out_file = str(burned_dir / f"burned_{i:05d}.png")
                success = burn_subtitle(
                    video_path, shot["time"], subtitle_text, out_file
                )
                if success:
                    burned_frames.append(out_file)
                else:
                    burned_frames.append(shot["path"])
            else:
                burned_frames.append(shot["path"])

            if progress_callback:
                progress_callback("burning_subtitles", 0.5 + 0.3 * (i + 1) / len(screenshots))

        # Step 4: Combine frames into PDF
        if progress_callback:
            progress_callback("generating_pdf", 0.8)

        _frames_to_pdf(burned_frames, output_pdf)

    return {
        "pdf": output_pdf,
        "frames": len(screenshots),
        "segments": len(segments),
    }


def _get_subtitle_for_time(segments: list[dict], time: float, window: float) -> str:
    """Find subtitle segments that overlap with a time window."""
    relevant = []
    window_end = time + window

    for seg in segments:
        if seg["end"] < time:
            continue
        if seg["start"] > window_end:
            break
        relevant.append(seg["text"])

    return " ".join(relevant) if relevant else ""


def _frames_to_pdf(frame_paths: list[str], output_pdf: str):
    """Combine frame images into a single PDF (same as video2blog approach)."""
    images = []
    for path in frame_paths:
        try:
            img = Image.open(path)
            if img.mode != "RGB":
                img = img.convert("RGB")
            images.append(img)
        except Exception:
            continue

    if images:
        images[0].save(
            output_pdf, "PDF",
            resolution=100.0,
            save_all=True,
            append_images=images[1:]
        )
