from __future__ import annotations

import logging
import shutil
from pathlib import Path

from PIL import Image

from genie_core.audio import transcribe_audio
from genie_core.audio.loader import load_transcript
from genie_core.video.screenshot import extract_screenshots, burn_subtitle


MAX_CHARS_PER_LINE = 30
MAX_LINES = 2


def video_to_pdf(
    video_path: str,
    output_pdf: str,
    interval: float = 30.0,
    scene_threshold: float = 0.3,
    language: str = "zh-Hans",
    transcript_path: str = None,
    progress_callback=None,
) -> dict:
    """Convert a video file to PDF with screenshots and subtitles.

    Flow:
    1. Whisper transcribe (or load existing transcript)
    2. Scene-change detection + timed screenshots
    3. Each scene collects all speech in its time range
    4. If speech exceeds 2 lines x 30 chars, split into multiple PDF pages
       reusing the same screenshot with successive subtitle chunks

    Returns {"pdf": str, "frames": int, "pages": int, "segments": int}.
    """
    video_path = str(video_path)
    output_pdf = str(output_pdf)

    work_dir = Path(output_pdf).parent / ("_vid2pdf_work_%s" % Path(output_pdf).stem)
    frames_dir = work_dir / "frames"
    burned_dir = work_dir / "burned"
    frames_dir.mkdir(parents=True, exist_ok=True)
    burned_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Transcribe audio (or load existing)
        if progress_callback:
            progress_callback("transcribing", 0)

        if transcript_path:
            segments = load_transcript(transcript_path)
        else:
            segments = transcribe_audio(video_path, language=language)

        # Step 2: Extract screenshots at scene changes + intervals
        if progress_callback:
            progress_callback("extracting_frames", 0.2)
        screenshots = extract_screenshots(
            video_path, str(frames_dir),
            interval=interval,
            scene_threshold=scene_threshold,
        )

        # Step 3: For each scene, collect subtitles and split into pages
        if progress_callback:
            progress_callback("burning_subtitles", 0.5)

        burned_frames = []
        for i, shot in enumerate(screenshots):
            # First scene also owns any speech before its capture time, so
            # midpoint assignment never drops leading segments.
            scene_start = shot["time"] if i > 0 else 0.0
            next_time = screenshots[i + 1]["time"] if i + 1 < len(screenshots) else None
            scene_text = _collect_scene_text(segments, scene_start, next_time)

            if not scene_text:
                burned_frames.append(shot["path"])
            else:
                subtitle_chunks = _split_into_pages(scene_text)
                fallback_added = False
                for ci, chunk in enumerate(subtitle_chunks):
                    out_file = str(burned_dir / ("burned_%05d_%02d.png" % (i, ci)))
                    success = burn_subtitle(
                        video_path, shot["time"], chunk, out_file
                    )
                    if success:
                        burned_frames.append(out_file)
                    else:
                        logging.warning(
                            "burn_subtitle failed for scene %d chunk %d (t=%.1fs); "
                            "falling back to raw frame%s",
                            i, ci, shot["time"],
                            " (already added, skipping duplicate)" if fallback_added else "",
                        )
                        if not fallback_added:
                            burned_frames.append(shot["path"])
                            fallback_added = True

            if progress_callback:
                progress_callback("burning_subtitles", 0.5 + 0.3 * (i + 1) / len(screenshots))

        # Step 4: Combine frames into PDF (streamed one image at a time)
        if progress_callback:
            progress_callback("generating_pdf", 0.8)

        _frames_to_pdf(burned_frames, output_pdf)

    finally:
        shutil.rmtree(str(work_dir), ignore_errors=True)

    return {
        "pdf": output_pdf,
        "frames": len(screenshots),
        "pages": len(burned_frames),
        "segments": len(segments),
    }


def _collect_scene_text(segments: list[dict], scene_start: float, scene_end: float = None) -> str:
    """Collect segment texts belonging to [scene_start, scene_end).

    A segment straddling a scene boundary is assigned to exactly one scene
    by its midpoint, so it is never duplicated across adjacent scenes.
    """
    relevant = []
    for seg in segments:
        midpoint = (seg["start"] + seg["end"]) / 2.0
        if midpoint < scene_start:
            continue
        if scene_end is not None and midpoint >= scene_end:
            continue
        relevant.append(seg["text"])
    return " ".join(relevant) if relevant else ""


def _split_into_pages(text: str) -> list[str]:
    all_lines = _wrap_text(text)
    pages = []
    for i in range(0, len(all_lines), MAX_LINES):
        page_lines = all_lines[i:i + MAX_LINES]
        pages.append("\n".join(page_lines))
    return pages if pages else [""]


def _wrap_text(text: str) -> list[str]:
    lines = []
    remaining = text.strip()
    while remaining:
        if len(remaining) <= MAX_CHARS_PER_LINE:
            lines.append(remaining)
            break
        cut = remaining[:MAX_CHARS_PER_LINE]
        best_pos = -1
        for sep in ["。", "，", "、", "；", "？", "！", " ", ".", ",", "?", "!"]:
            pos = cut.rfind(sep)
            if pos > MAX_CHARS_PER_LINE // 3:
                best_pos = max(best_pos, pos)
        if best_pos > 0:
            lines.append(remaining[:best_pos + 1].rstrip())
            remaining = remaining[best_pos + 1:].lstrip()
        else:
            lines.append(cut)
            remaining = remaining[MAX_CHARS_PER_LINE:].lstrip()
    return lines


def _frames_to_pdf(frame_paths: list[str], output_pdf: str):
    """Combine frame images into PDF.

    Images are opened lazily one at a time via a generator (each file handle
    is closed as soon as the pixel data is copied, avoiding fd exhaustion)
    instead of accumulating every decoded frame up front.

    Raises RuntimeError if no page could be produced (empty frame list or
    every frame failed to load), instead of silently returning without a PDF.
    """
    def _open_rgb(path: str) -> Image.Image:
        # Copy pixel data so the file handle can be closed immediately.
        with Image.open(path) as img:
            if img.mode != "RGB":
                return img.convert("RGB")
            return img.copy()

    def _iter_images():
        for page_no, path in enumerate(frame_paths, start=1):
            try:
                yield _open_rgb(path)
            except Exception as exc:
                logging.warning(
                    "Skipping PDF page %d: failed to load frame %s (%s)",
                    page_no, path, exc,
                )

    images = _iter_images()
    first = next(images, None)
    if first is None:
        raise RuntimeError(
            "No PDF pages could be generated for %s: %d frame path(s), "
            "all empty or failed to load" % (output_pdf, len(frame_paths))
        )
    try:
        first.save(
            output_pdf, "PDF",
            resolution=100.0,
            save_all=True,
            append_images=images,
        )
    finally:
        first.close()
