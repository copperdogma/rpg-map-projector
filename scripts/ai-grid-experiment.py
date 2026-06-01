#!/usr/bin/env python3
"""Run AI grid-output experiments against labeled calibration fixtures.

The script intentionally writes all generated artifacts under test-results/,
which is ignored by git. It never prints API keys.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import requests
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_SOURCE_ID = "real-map-home-IMG_9717.jpg"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-grid-experiments"


@dataclass
class PromptSpec:
    prompt_id: str
    kind: str
    text: str


IMAGE_PROMPTS = [
    PromptSpec(
        "mask-white-visible-v1",
        "white_mask",
        (
            "Create a computer-vision calibration mask from this photo. "
            "Return a new image with the exact same crop, orientation, perspective, and aspect ratio as the input. "
            "Use a pure black background (#000000). Draw only the visible real one-inch battle-map grid lines as "
            "thin pure white (#FFFFFF) lines. Do not draw pencil marks, wrinkles, shadows, map texture, table texture, "
            "text, labels, or numbers. Do not straighten, rotate, crop, rescale, or otherwise change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "axis-color-visible-v1",
        "color_mask",
        (
            "Create a computer-vision calibration mask from this photo. "
            "Return a new image with the exact same crop, orientation, perspective, and aspect ratio as the input. "
            "Use a pure black background (#000000). Draw only the visible real one-inch battle-map grid lines. "
            "Draw one parallel grid family as pure red (#FF0000) and the crossing grid family as pure blue (#0000FF). "
            "Do not draw pencil marks, wrinkles, shadows, map texture, table texture, text, labels, or numbers. "
            "Do not straighten, rotate, crop, rescale, or otherwise change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "axis-color-exact-copy-user-v1",
        "color_mask",
        (
            "Create an exact copy of this image, but only the gridlines on a black background. "
            "Make the horizontal lines blue and the vertical lines red."
        ),
    ),
    PromptSpec(
        "white-grid-exact-copy-no-marks-v1",
        "white_mask",
        (
            "Create an exact copy of this image, but only the printed square battle-map gridlines on a black background. "
            "Draw all real printed gridlines as thin pure white lines. Do not include pencil drawings, marker drawings, "
            "hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or any non-grid marks. "
            "Preserve the exact crop, aspect ratio, perspective, and geometry of the source image."
        ),
    ),
    PromptSpec(
        "white-grid-printed-only-strict-v2",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with the real printed square battle-map gridlines drawn as thin pure white lines. Draw only the pre-printed "
            "regular grid that covers the mat. Do not draw pencil marks, marker drawings, hand-drawn room outlines, wall "
            "sketches, curved shapes, freehand lines, wrinkles, shadows, glare, table edges, mat borders, labels, logos, "
            "texture, or any other non-grid marks. If a visible line is irregular, freehand, curved, not part of the evenly "
            "spaced printed lattice, or you are unsure whether it is a printed gridline, leave it black. Preserve the exact "
            "crop, aspect ratio, perspective, and geometry of the source image."
        ),
    ),
    PromptSpec(
        "white-grid-regular-lattice-only-v2",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with thin pure white lines. Identify the two crossing families of evenly spaced printed square battle-map "
            "gridlines. Draw only lines that belong to those two regular lattice families and continue consistently with "
            "neighboring printed gridlines. Exclude every line or mark that is not part of the regular square lattice, "
            "including pencil or marker room drawings, walls, circles, curves, wrinkles, shadows, glare, mat border, table, "
            "logos, labels, or texture. Do not invent hidden gridlines where the printed grid is not visible. Preserve the "
            "exact crop, aspect ratio, perspective, and geometry of the source image."
        ),
    ),
    PromptSpec(
        "white-grid-no-freehand-emphasis-v3",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with the printed square battle-map gridlines drawn as thin pure white lines. The photo may contain darker "
            "hand-drawn pencil or marker room outlines, walls, circles, curves, and other freehand sketch marks. Those "
            "freehand marks are not gridlines: do not trace them, do not preserve them, and leave them black even when "
            "they overlap or run near the printed grid. Draw the faint repeated printed gridlines only. Omit any stroke "
            "that is curved, irregular, isolated, or not parallel to one of the two printed gridline families. Do not "
            "straighten, rotate, crop, rescale, regularize, complete hidden areas, or invent missing gridlines. Preserve "
            "the exact crop, aspect ratio, perspective, and geometry of the source image."
        ),
    ),
    PromptSpec(
        "white-grid-simple-only-v4",
        "white_mask",
        (
            "Create an exact copy of this image size and geometry, but with a black background and thin white lines over "
            "the actual printed square gridlines in the photo. Draw only the printed gridlines, not anything else drawn "
            "on the surface or occluding it. Preserve the exact crop, aspect ratio, perspective, and geometry."
        ),
    ),
    PromptSpec(
        "white-grid-succinct-actual-only-v5",
        "white_mask",
        (
            "Draw thin white gridlines overtop the actual printed gridlines in the photo on a black background. "
            "Draw only the printed gridlines, not drawings, marks, shadows, glare, borders, texture, table, or occluders. "
            "Keep the same image size, crop, perspective, and geometry."
        ),
    ),
    PromptSpec(
        "white-grid-solid-only-v6",
        "white_mask",
        (
            "Draw only the actual printed gridlines as solid white lines on a black background. "
            "Do not draw any other marks. Keep the same crop, perspective, and geometry."
        ),
    ),
    PromptSpec(
        "white-grid-actual-only-no-occluders-v7",
        "white_mask",
        (
            "Draw white gridlines overtop the actual gridlines in the photo on a black background. "
            "Draw only the gridlines, not anything else drawn on the surface or occluding it. "
            "Keep the same crop, perspective, and geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-less-steep-v1",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with thin pure white lines. The photo contains two crossing parallel families of printed square battle-map gridlines. "
            "Draw only the one gridline family whose image-space direction is less steep, meaning closer to left-to-right across "
            "the image than to top-to-bottom. Do not draw the crossing family at all, even at intersections. Do not draw pencil "
            "marks, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or non-grid marks. "
            "Do not straighten, rotate, crop, rescale, or change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-more-steep-v1",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with thin pure white lines. The photo contains two crossing parallel families of printed square battle-map gridlines. "
            "Draw only the one gridline family whose image-space direction is more steep, meaning closer to top-to-bottom across "
            "the image than to left-to-right. Do not draw the crossing family at all, even at intersections. Do not draw pencil "
            "marks, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or non-grid marks. "
            "Do not straighten, rotate, crop, rescale, or change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-less-steep-stripes-v2",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with thin pure white lines. Find the two crossing families of printed square battle-map gridlines. Draw only the "
            "family whose image-space angle is less steep, closer to left-to-right than top-to-bottom. The output must look like "
            "parallel stripes only, not a square grid. Do not draw any crossing/perpendicular gridlines. Do not draw grid intersections "
            "as plus signs. Do not draw pencil marks, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, "
            "mat border, texture, or non-grid marks. Do not straighten, rotate, crop, rescale, or change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-more-steep-stripes-v2",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with thin pure white lines. Find the two crossing families of printed square battle-map gridlines. Draw only the "
            "family whose image-space angle is more steep, closer to top-to-bottom than left-to-right. The output must look like "
            "parallel stripes only, not a square grid. Do not draw any crossing/perpendicular gridlines. Do not draw grid intersections "
            "as plus signs. Do not draw pencil marks, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, "
            "mat border, texture, or non-grid marks. Do not straighten, rotate, crop, rescale, or change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-slants-down-right-stripes-v1",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with thin pure white lines. Find the two crossing families of printed square battle-map gridlines. Draw only the "
            "family that visually slants downward as it moves from left to right across the image, like lines from the upper-left "
            "toward the lower-right. The output must look like parallel stripes only, not a square grid. Do not draw the crossing "
            "family at all. Do not draw pencil marks, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, "
            "mat border, texture, or non-grid marks. Do not straighten, rotate, crop, rescale, or change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-slants-up-right-stripes-v1",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with thin pure white lines. Find the two crossing families of printed square battle-map gridlines. Draw only the "
            "family that visually slants upward as it moves from left to right across the image, like lines from the lower-left "
            "toward the upper-right. The output must look like parallel stripes only, not a square grid. Do not draw the crossing "
            "family at all. Do not draw pencil marks, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, "
            "mat border, texture, or non-grid marks. Do not straighten, rotate, crop, rescale, or change the coordinate geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-horizontal-simple-v1",
        "white_mask",
        (
            "Create an exact copy of this image size and geometry, but with a black background and thin white lines over "
            "only the printed gridlines that run closer to left-right across the photo. Do not draw the crossing gridline "
            "family or anything else on the surface. Preserve the exact crop, aspect ratio, perspective, and geometry."
        ),
    ),
    PromptSpec(
        "white-grid-family-vertical-simple-v1",
        "white_mask",
        (
            "Create an exact copy of this image size and geometry, but with a black background and thin white lines over "
            "only the printed gridlines that run closer to top-bottom across the photo. Do not draw the crossing gridline "
            "family or anything else on the surface. Preserve the exact crop, aspect ratio, perspective, and geometry."
        ),
    ),
    PromptSpec(
        "white-intersection-dots-no-lines-v1",
        "dot_mask",
        (
            "Create an exact copy of this image size and geometry, but output only a black background with small pure white dots "
            "at every visible intersection of the printed square battle-map grid. Do not draw lines. Do not include pencil "
            "drawings, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or any non-grid marks. "
            "Preserve the exact crop, aspect ratio, perspective, and geometry of the source image."
        ),
    ),
    PromptSpec(
        "white-intersection-dots-simple-v2",
        "dot_mask",
        (
            "Create an exact copy of this image size and geometry, but with a black background and small white dots at every "
            "actual printed square-grid intersection in the photo. Draw only the dots, not lines or anything else."
        ),
    ),
    PromptSpec(
        "white-intersections-from-grid-mask-v1",
        "dot_mask",
        (
            "Create an exact copy of this image size and geometry, but with a black background and small white dots at every "
            "visible intersection of the white gridlines in this image. Do not draw lines or anything except the dots."
        ),
    ),
    PromptSpec(
        "white-intersection-centroids-v2",
        "dot_mask",
        (
            "Create an exact copy of this image size, crop, aspect ratio, perspective, and geometry, but output only a pure black "
            "background with one tiny pure white filled circle centered on each visible intersection where two printed square "
            "battle-map grid lines cross. Each circle should be about 2 pixels wide. Mark the center of the printed grid crossing, "
            "not the corners of a square and not points along a line. Do not draw any grid lines, plus signs, rings, numbers, labels, "
            "pencil marks, marker drawings, hand-drawn room outlines, shadows, glare, table, mat border, texture, or any non-grid marks. "
            "Preserve the exact camera perspective and do not straighten, rotate, crop, rescale, regularize, or complete hidden grid areas."
        ),
    ),
    PromptSpec(
        "white-confirmed-intersection-dots-only-v1",
        "dot_mask",
        (
            "Create an exact copy of this image size, crop, aspect ratio, perspective, and geometry, but output only a pure black "
            "background with small pure white dots. Put a dot only at confirmed visible intersections where two printed square "
            "battle-map grid lines physically cross in the photo. Do not infer, complete, straighten, regularize, or continue the "
            "grid where intersections are hidden, uncertain, obscured, too faint, outside the physical mat, or on the table/background. "
            "Do not draw lines. Do not include pencil drawings, marker drawings, hand-drawn room outlines, shadows, glare, wrinkles, "
            "mat border, texture, labels, or any non-grid marks. If uncertain, leave it black."
        ),
    ),
    PromptSpec(
        "white-intersection-dots-large-exhaustive-v1",
        "dot_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry, but output only a black background "
            "with a bright pure white circular dot at every visible intersection of the printed square battle-map grid. "
            "Make each dot about 4 pixels wide. Include faint, partial, and low-contrast grid intersections if they are visible. "
            "Do not draw lines. Do not include pencil drawings, marker drawings, hand-drawn room outlines, shadows, glare, table, labels, "
            "mat border, texture, or any non-grid marks. Do not straighten, rotate, crop, or rescale the image."
        ),
    ),
    PromptSpec(
        "white-grid-with-dot-intersections-no-marks-v1",
        "white_mask",
        (
            "Create an exact copy of this image size, crop, perspective, and geometry on a black background. "
            "Draw only the printed square battle-map grid: thin white lines for every visible printed gridline, "
            "plus a small brighter white dot at each visible grid intersection. Do not include pencil drawings, marker drawings, "
            "hand-drawn room outlines, shadows, glare, table, labels, mat border, texture, or any non-grid marks. "
            "Do not straighten, rotate, crop, or rescale the image."
        ),
    ),
    PromptSpec(
        "pink-overlay-visible-v1",
        "pink_overlay",
        (
            "Return a copy of this exact image with the same crop, orientation, perspective, and aspect ratio. "
            "Draw bright pink gridlines directly over the real one-inch battle-map gridlines in the photo. "
            "Only mark real gridlines. Do not mark pencil drawings, wrinkles, shadows, or texture. "
            "Do not straighten, rotate, crop, rescale, or otherwise change the coordinate geometry."
        ),
    ),
]

JSON_PROMPT = (
    "You are calibrating a tabletop RPG battle-map projector from a camera photo. "
    "Find the one-inch square grid printed on the physical mat. Return JSON only, no prose, using this schema: "
    '{"columns": integer, "rows": integer, "corners": [{"x": number, "y": number}, {"x": number, "y": number}, '
    '{"x": number, "y": number}, {"x": number, "y": number}], "visibleGrid": {"minColumn": integer, '
    '"maxColumn": integer, "minRow": integer, "maxRow": integer}, "confidence": number, "notes": string}. '
    "Coordinates must be pixel coordinates in the displayed, EXIF-corrected input image. The corners are the full "
    "logical outer grid rectangle in order top-left, top-right, bottom-right, bottom-left. If a logical outer corner "
    "falls outside the image, still return the extrapolated coordinate. Use the visible grid to infer the full grid."
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--providers", default="openai-image,gemini-image,grok-image,openai-json,gemini-json,grok-json")
    parser.add_argument("--prompts", default="mask-white-visible-v1,axis-color-visible-v1")
    parser.add_argument("--max-width", type=int, default=1024)
    args = parser.parse_args()

    load_project_env()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    label = load_label(args.source_id)
    input_path = ROOT / label["sourceUrl"].removeprefix("/")
    input_image = load_display_image(input_path)
    input_work_path = write_working_input(input_image, out_dir, args.max_width, args.source_id)
    input_work_size = load_display_image(input_work_path).size

    selected_prompt_ids = {value.strip() for value in args.prompts.split(",") if value.strip()}
    prompts = [prompt for prompt in IMAGE_PROMPTS if prompt.prompt_id in selected_prompt_ids]
    providers = [value.strip() for value in args.providers.split(",") if value.strip()]

    results: list[dict[str, Any]] = []
    for provider in providers:
        if provider.endswith("-image"):
            for prompt in prompts:
                results.append(run_image_experiment(provider, prompt, input_work_path, label, out_dir))
        elif provider.endswith("-json"):
            results.append(run_json_experiment(provider, input_work_path, input_work_size, label, out_dir))
        else:
            results.append({"provider": provider, "ok": False, "error": "Unknown provider id."})

    write_contact_sheet(out_dir, results, input_work_path)
    report = {
        "sourceId": args.source_id,
        "sourceUrl": label["sourceUrl"],
        "inputWorkingImage": str(input_work_path),
        "generatedAt": iso_now(),
        "results": results,
    }
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(report))
    print(render_console_summary(report))


def load_project_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key.startswith("RPG_MAP_"):
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def load_label(source_id: str) -> dict[str, Any]:
    data = json.loads(LABELS_PATH.read_text())
    for label in data["labels"]:
        if label["sourceId"] == source_id:
            return label
    raise SystemExit(f"No label found for {source_id}")


def load_display_image(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def write_working_input(image: Image.Image, out_dir: Path, max_width: int, source_id: str) -> Path:
    inputs_dir = out_dir / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    working = image
    if max_width > 0 and image.width > max_width:
        scale = max_width / image.width
        working = image.resize((max_width, round(image.height * scale)), Image.Resampling.LANCZOS)
    path = inputs_dir / f"{slugify(Path(source_id).stem)}-w{working.width}.png"
    working.save(path)
    return path


def run_image_experiment(provider: str, prompt: PromptSpec, input_path: Path, label: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    experiment_id = f"{provider}-{prompt.prompt_id}"
    started = time.perf_counter()
    result: dict[str, Any] = {
        "experimentId": experiment_id,
        "provider": provider,
        "promptId": prompt.prompt_id,
        "kind": prompt.kind,
        "ok": False,
        "elapsedMs": None,
    }
    try:
        if provider == "openai-image":
            image_path, metadata = call_openai_image_edit(prompt.text, input_path, out_dir, experiment_id)
        elif provider == "gemini-image":
            image_path, metadata = call_gemini_image_edit(prompt.text, input_path, out_dir, experiment_id)
        elif provider == "grok-image":
            image_path, metadata = call_grok_image_edit(prompt.text, input_path, out_dir, experiment_id)
        else:
            raise ValueError(f"Unsupported image provider {provider}")

        result["ok"] = True
        result["outputImage"] = str(image_path)
        result["metadata"] = metadata
        result["imageScore"] = score_output_image(image_path, label, prompt.kind)
    except Exception as error:  # noqa: BLE001 - experiment reports provider/API errors.
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        result["elapsedMs"] = round_metric((time.perf_counter() - started) * 1000)
    return result


def run_json_experiment(provider: str, input_path: Path, original_size: tuple[int, int], label: dict[str, Any], out_dir: Path) -> dict[str, Any]:
    experiment_id = provider
    started = time.perf_counter()
    result: dict[str, Any] = {
        "experimentId": experiment_id,
        "provider": provider,
        "promptId": "json-grid-v1",
        "kind": "json_grid",
        "ok": False,
        "elapsedMs": None,
    }
    try:
        prompt = json_prompt_for_size(original_size)
        if provider == "openai-json":
            payload = call_openai_json(prompt, input_path)
        elif provider == "gemini-json":
            payload = call_gemini_json(prompt, input_path)
        elif provider == "grok-json":
            payload = call_grok_json(prompt, input_path)
        else:
            raise ValueError(f"Unsupported JSON provider {provider}")
        output_path = out_dir / f"{experiment_id}.json"
        output_path.write_text(f"{json.dumps(payload, indent=2)}\n")
        result["ok"] = True
        result["outputJson"] = str(output_path)
        result["jsonScore"] = score_json_grid(payload, label, original_size)
    except Exception as error:  # noqa: BLE001 - experiment reports provider/API errors.
        result["error"] = f"{type(error).__name__}: {error}"
    finally:
        result["elapsedMs"] = round_metric((time.perf_counter() - started) * 1000)
    return result


def json_prompt_for_size(image_size: tuple[int, int]) -> str:
    width, height = image_size
    return (
        f"The attached image has already been EXIF-corrected and resized to exactly {width} pixels wide by "
        f"{height} pixels tall. All coordinates in your answer must use this {width}x{height} image coordinate "
        f"system, with x from 0 to {width - 1} and y from 0 to {height - 1} for pixels inside the image. "
        f"{JSON_PROMPT}"
    )


def call_openai_image_edit(prompt: str, input_path: Path, out_dir: Path, experiment_id: str) -> tuple[Path, dict[str, Any]]:
    key = require_env("RPG_MAP_OPENAI_API_KEY")
    started = time.perf_counter()
    with input_path.open("rb") as image_file:
        response = requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {key}"},
            data={
                "model": os.environ.get("RPG_MAP_OPENAI_IMAGE_MODEL", "gpt-image-1"),
                "prompt": prompt,
                "n": "1",
                "size": "auto",
            },
            files={"image": (input_path.name, image_file, "image/png")},
            timeout=180,
        )
    raise_for_status(response)
    data = response.json()
    item = data["data"][0]
    image_path = out_dir / f"{experiment_id}.png"
    save_image_item(item, image_path)
    return image_path, {"model": os.environ.get("RPG_MAP_OPENAI_IMAGE_MODEL", "gpt-image-1"), "apiElapsedMs": round_metric((time.perf_counter() - started) * 1000)}


def call_gemini_image_edit(prompt: str, input_path: Path, out_dir: Path, experiment_id: str) -> tuple[Path, dict[str, Any]]:
    key = require_env("RPG_MAP_GEMINI_API_KEY")
    model = os.environ.get("RPG_MAP_GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    data_url = image_data(input_path)
    mime, b64 = data_url.split(",", 1)
    mime_type = mime.removeprefix("data:").split(";", 1)[0]
    started = time.perf_counter()
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": b64}}]}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        },
        timeout=180,
    )
    raise_for_status(response)
    payload = response.json()
    image_path = out_dir / f"{experiment_id}.png"
    text_parts: list[str] = []
    for part in payload.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "text" in part:
            text_parts.append(part["text"])
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            image_path.write_bytes(base64.b64decode(inline["data"]))
            return image_path, {"model": model, "text": "\n".join(text_parts).strip(), "apiElapsedMs": round_metric((time.perf_counter() - started) * 1000)}
    raise RuntimeError(f"Gemini returned no image parts: {json.dumps(payload)[:500]}")


def call_grok_image_edit(prompt: str, input_path: Path, out_dir: Path, experiment_id: str) -> tuple[Path, dict[str, Any]]:
    key = require_env("RPG_MAP_GROK_API_KEY")
    model = os.environ.get("RPG_MAP_GROK_IMAGE_MODEL", "grok-imagine-image-quality")
    started = time.perf_counter()
    response = requests.post(
        "https://api.x.ai/v1/images/edits",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "prompt": prompt,
            "image": {"url": image_data(input_path), "type": "image_url"},
            "response_format": "b64_json",
        },
        timeout=180,
    )
    raise_for_status(response)
    payload = response.json()
    item = payload["data"][0]
    image_path = out_dir / f"{experiment_id}.png"
    if item.get("b64_json"):
        image_path.write_bytes(base64.b64decode(item["b64_json"]))
    elif item.get("url"):
        download_image(item["url"], image_path)
    else:
        raise RuntimeError(f"xAI image response had no image field: {json.dumps(payload)[:500]}")
    return image_path, {"model": model, "mimeType": item.get("mime_type"), "apiElapsedMs": round_metric((time.perf_counter() - started) * 1000)}


def call_openai_json(prompt: str, input_path: Path) -> dict[str, Any]:
    key = require_env("RPG_MAP_OPENAI_API_KEY")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": os.environ.get("RPG_MAP_OPENAI_VISION_MODEL", "gpt-5-mini"),
            "input": [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": image_data(input_path)},
                ],
            }],
            "text": {"format": {"type": "json_object"}},
        },
        timeout=120,
    )
    raise_for_status(response)
    payload = response.json()
    return extract_json_from_text(extract_openai_output_text(payload))


def call_gemini_json(prompt: str, input_path: Path) -> dict[str, Any]:
    key = require_env("RPG_MAP_GEMINI_API_KEY")
    model = os.environ.get("RPG_MAP_GEMINI_VISION_MODEL", "gemini-2.5-flash")
    data_url = image_data(input_path)
    mime, b64 = data_url.split(",", 1)
    mime_type = mime.removeprefix("data:").split(";", 1)[0]
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": b64}}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=120,
    )
    raise_for_status(response)
    payload = response.json()
    parts = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(part.get("text", "") for part in parts)
    return extract_json_from_text(text)


def call_grok_json(prompt: str, input_path: Path) -> dict[str, Any]:
    key = require_env("RPG_MAP_GROK_API_KEY")
    response = requests.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": os.environ.get("RPG_MAP_GROK_VISION_MODEL", "grok-4.3"),
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data(input_path)}},
                ],
            }],
            "response_format": {"type": "json_object"},
        },
        timeout=120,
    )
    raise_for_status(response)
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    return extract_json_from_text(content)


def raise_for_status(response: requests.Response) -> None:
    if response.status_code < 400:
        return
    body = response.text[:1000]
    raise RuntimeError(f"HTTP {response.status_code}: {body}")


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is not set")
    return value


def image_data(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def save_image_item(item: dict[str, Any], image_path: Path) -> None:
    if item.get("b64_json"):
        image_path.write_bytes(base64.b64decode(item["b64_json"]))
        return
    if item.get("url"):
        download_image(item["url"], image_path)
        return
    raise RuntimeError("Image response item had neither b64_json nor url")


def download_image(url: str, path: Path) -> None:
    with urllib.request.urlopen(url, timeout=60) as response:
        path.write_bytes(response.read())


def score_output_image(image_path: Path, label: dict[str, Any], kind: str) -> dict[str, Any]:
    with Image.open(image_path) as pil_image:
        image = ImageOps.exif_transpose(pil_image).convert("RGB")
        rgb = np.array(image)
    mask_kind = "white_mask" if kind == "dot_mask" else kind
    mask = extract_signal_mask(rgb, mask_kind)
    scaled_label = scale_label(label, image.width, image.height)
    coverage = line_mask_coverage(mask, scaled_label)
    alignment = point_alignment(mask, scaled_label)
    background = background_score(rgb, kind)
    score = {
        "width": image.width,
        "height": image.height,
        "aspectRatioDeltaPct": round_metric(abs((image.width / image.height) - (label["imageWidth"] / label["imageHeight"])) / (label["imageWidth"] / label["imageHeight"]) * 100),
        "signalPixels": int((mask > 0).sum()),
        "signalPct": round_metric(float((mask > 0).mean() * 100)),
        "coverage": coverage,
        "alignment": alignment,
        "background": background,
    }
    if kind == "dot_mask":
        score["dotScore"] = dot_intersection_score(mask, scaled_label)
    return score


def dot_intersection_score(mask: np.ndarray, label: dict[str, Any]) -> dict[str, Any]:
    components, labels_image, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    dots = []
    for index in range(1, components):
        area = int(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if 1 <= area <= 90 and width <= 16 and height <= 16:
            dots.append(centroids[index])
    if not dots:
        return {
            "dotCount": 0,
            "matchedVisibleIntersections": 0,
            "visibleExpectedIntersections": len(visible_expected_intersections(label)),
            "matchedVisibleIntersectionRatio": 0,
            "spuriousDotPct": None,
            "medianIntersectionErrorSquares": None,
        }

    points = np.float32(dots)
    image_to_grid = cv2.getPerspectiveTransform(label_corners(label), np.float32([[0, 0], [label["columns"], 0], [label["columns"], label["rows"]], [0, label["rows"]]]))
    grid_points = cv2.perspectiveTransform(points.reshape(1, -1, 2), image_to_grid).reshape(-1, 2)
    inside = (
        (grid_points[:, 0] >= -0.75)
        & (grid_points[:, 0] <= label["columns"] + 0.75)
        & (grid_points[:, 1] >= -0.75)
        & (grid_points[:, 1] <= label["rows"] + 0.75)
    )
    grid_points = grid_points[inside]
    if len(grid_points) == 0:
        return {
            "dotCount": len(dots),
            "matchedVisibleIntersections": 0,
            "visibleExpectedIntersections": len(visible_expected_intersections(label)),
            "matchedVisibleIntersectionRatio": 0,
            "spuriousDotPct": 100,
            "medianIntersectionErrorSquares": None,
        }
    distances = np.sqrt((grid_points[:, 0] - np.rint(grid_points[:, 0])) ** 2 + (grid_points[:, 1] - np.rint(grid_points[:, 1])) ** 2)
    close = grid_points[distances < 0.22]
    matched = {
        (int(round(point[0])), int(round(point[1])))
        for point in close
        if 0 <= round(point[0]) <= label["columns"] and 0 <= round(point[1]) <= label["rows"]
    }
    expected = set(visible_expected_intersections(label))
    matched_visible = len(matched & expected)
    spurious = max(0, len(dots) - len(matched))
    return {
        "dotCount": len(dots),
        "matchedVisibleIntersections": matched_visible,
        "visibleExpectedIntersections": len(expected),
        "matchedVisibleIntersectionRatio": round_metric(matched_visible / max(1, len(expected))),
        "spuriousDotPct": round_metric(spurious / max(1, len(dots)) * 100),
        "medianIntersectionErrorSquares": round_metric(float(np.median(distances))),
        "p90IntersectionErrorSquares": round_metric(float(np.percentile(distances, 90))),
        "matchedIndexRange": None if not matched else [
            [min(point[0] for point in matched), max(point[0] for point in matched)],
            [min(point[1] for point in matched), max(point[1] for point in matched)],
        ],
    }


def visible_expected_intersections(label: dict[str, Any]) -> list[tuple[int, int]]:
    columns = int(label["columns"])
    rows = int(label["rows"])
    width = int(label["imageWidth"])
    height = int(label["imageHeight"])
    grid_to_image = cv2.getPerspectiveTransform(np.float32([[0, 0], [columns, 0], [columns, rows], [0, rows]]), label_corners(label))
    expected = []
    for column in range(columns + 1):
        for row in range(rows + 1):
            point = cv2.perspectiveTransform(np.float32([[[column, row]]]), grid_to_image).reshape(2)
            if 0 <= point[0] < width and 0 <= point[1] < height:
                expected.append((column, row))
    return expected


def extract_signal_mask(rgb: np.ndarray, kind: str) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    r = rgb[:, :, 0].astype(np.int16)
    g = rgb[:, :, 1].astype(np.int16)
    b = rgb[:, :, 2].astype(np.int16)

    if kind == "pink_overlay":
        mask = (s > 35) & (v > 80) & (r > 120) & (b > 80) & ((r - g) > 25) & ((b - g) > -20) & (((h >= 135) & (h <= 179)) | ((h >= 0) & (h <= 8)))
    elif kind == "color_mask":
        red = (s > 30) & (v > 35) & ((h >= 160) | (h <= 8))
        blue = (s > 30) & (v > 35) & (h >= 95) & (h <= 140)
        mask = red | blue
    else:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        if float(np.mean(gray)) < 80:
            threshold = max(25.0, min(165.0, float(np.percentile(gray, 92))))
            mask = gray > threshold
        else:
            mask = (gray > 165) & (v > 120)

    out = mask.astype(np.uint8) * 255
    if out.size:
        out = cv2.medianBlur(out, 3)
        out = cv2.morphologyEx(out, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    return out


def background_score(rgb: np.ndarray, kind: str) -> dict[str, Any]:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if kind in {"white_mask", "color_mask"}:
        dark_pct = float(np.mean(gray < 35) * 100)
        return {"darkPixelPct": round_metric(dark_pct), "meanBrightness": round_metric(float(np.mean(gray)))}
    return {"darkPixelPct": round_metric(float(np.mean(gray < 35) * 100)), "meanBrightness": round_metric(float(np.mean(gray)))}


def scale_label(label: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    sx = width / label["imageWidth"]
    sy = height / label["imageHeight"]
    scaled = dict(label)
    scaled["imageWidth"] = width
    scaled["imageHeight"] = height
    scaled["corners"] = [{"x": point["x"] * sx, "y": point["y"] * sy} for point in label["corners"]]
    return scaled


def line_mask_coverage(mask: np.ndarray, label: dict[str, Any]) -> dict[str, Any]:
    dist = cv2.distanceTransform((mask == 0).astype(np.uint8) * 255, cv2.DIST_L2, 3)
    height, width = mask.shape
    columns = int(label["columns"])
    rows = int(label["rows"])
    corners = label_corners(label)
    grid_to_image = cv2.getPerspectiveTransform(np.float32([[0, 0], [columns, 0], [columns, rows], [0, rows]]), corners)
    cell_samples = []
    for y in np.linspace(0, rows, 5):
        points = np.float32([[[0, y], [1, y]]])
        projected = cv2.perspectiveTransform(points, grid_to_image).reshape(-1, 2)
        cell_samples.append(float(np.linalg.norm(projected[1] - projected[0])))
    for x in np.linspace(0, columns, 5):
        points = np.float32([[[x, 0], [x, 1]]])
        projected = cv2.perspectiveTransform(points, grid_to_image).reshape(-1, 2)
        cell_samples.append(float(np.linalg.norm(projected[1] - projected[0])))
    threshold = max(2.5, min(8.0, float(np.median(cell_samples)) * 0.18))

    vertical = []
    horizontal = []
    for x in range(columns + 1):
        vertical.append(sample_line_coverage(dist, grid_to_image, [[x, y] for y in np.linspace(0, rows, 80)], width, height, threshold))
    for y in range(rows + 1):
        horizontal.append(sample_line_coverage(dist, grid_to_image, [[x, y] for x in np.linspace(0, columns, 80)], width, height, threshold))

    vc = [value for value in vertical if value is not None]
    hc = [value for value in horizontal if value is not None]
    return {
        "pixelThreshold": round_metric(threshold),
        "verticalVisibleLines": len(vc),
        "horizontalVisibleLines": len(hc),
        "verticalMeanCoverage": round_metric(float(np.mean(vc))) if vc else None,
        "horizontalMeanCoverage": round_metric(float(np.mean(hc))) if hc else None,
        "lineMeanCoverage": round_metric(float(np.mean(vc + hc))) if vc or hc else None,
        "verticalLinesAbove50Pct": int(sum(value >= 0.5 for value in vc)),
        "horizontalLinesAbove50Pct": int(sum(value >= 0.5 for value in hc)),
    }


def sample_line_coverage(dist: np.ndarray, transform: np.ndarray, samples: list[list[float]], width: int, height: int, threshold: float) -> float | None:
    points = cv2.perspectiveTransform(np.float32(samples).reshape(1, -1, 2), transform).reshape(-1, 2)
    inside = (points[:, 0] >= 0) & (points[:, 0] < width) & (points[:, 1] >= 0) & (points[:, 1] < height)
    if int(inside.sum()) < 3:
        return None
    xs = np.clip(np.rint(points[inside, 0]).astype(int), 0, width - 1)
    ys = np.clip(np.rint(points[inside, 1]).astype(int), 0, height - 1)
    return float(np.mean(dist[ys, xs] <= threshold))


def point_alignment(mask: np.ndarray, label: dict[str, Any]) -> dict[str, Any]:
    columns = int(label["columns"])
    rows = int(label["rows"])
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return {"maskPointsInGrid": 0}
    points = np.stack([xs, ys], axis=1).astype(np.float32)
    if len(points) > 200000:
        indexes = np.linspace(0, len(points) - 1, 200000).astype(int)
        points = points[indexes]
    image_to_grid = cv2.getPerspectiveTransform(label_corners(label), np.float32([[0, 0], [columns, 0], [columns, rows], [0, rows]]))
    grid_points = cv2.perspectiveTransform(points.reshape(1, -1, 2), image_to_grid).reshape(-1, 2)
    finite = np.isfinite(grid_points).all(axis=1)
    grid_points = grid_points[finite]
    inside = (grid_points[:, 0] >= -1) & (grid_points[:, 0] <= columns + 1) & (grid_points[:, 1] >= -1) & (grid_points[:, 1] <= rows + 1)
    grid_points = grid_points[inside]
    if len(grid_points) == 0:
        return {"maskPointsInGrid": 0}
    dx = np.abs(grid_points[:, 0] - np.rint(grid_points[:, 0]))
    dy = np.abs(grid_points[:, 1] - np.rint(grid_points[:, 1]))
    distance = np.minimum(dx, dy)
    return {
        "maskPointsInGrid": int(len(grid_points)),
        "medianNearestLineDistanceSquares": round_metric(float(np.median(distance))),
        "p90NearestLineDistanceSquares": round_metric(float(np.percentile(distance, 90))),
        "pointsWithin0_10SquaresPct": round_metric(float(np.mean(distance <= 0.10) * 100)),
        "pointsWithin0_15SquaresPct": round_metric(float(np.mean(distance <= 0.15) * 100)),
    }


def score_json_grid(payload: dict[str, Any], label: dict[str, Any], working_size: tuple[int, int]) -> dict[str, Any]:
    columns = payload.get("columns")
    rows = payload.get("rows")
    corners = payload.get("corners")
    if not isinstance(corners, list) or len(corners) != 4:
        return {"parseableGrid": False, "error": "JSON did not contain four corners."}

    sx = label["imageWidth"] / working_size[0]
    sy = label["imageHeight"] / working_size[1]
    predicted = np.float32([[float(point["x"]) * sx, float(point["y"]) * sy] for point in corners])
    truth = label_corners(label)
    deltas = np.linalg.norm(predicted - truth, axis=1)
    square = average_truth_square_pixels(label)
    return {
        "parseableGrid": True,
        "rowColumnExact": columns == label["columns"] and rows == label["rows"],
        "expectedColumns": label["columns"],
        "expectedRows": label["rows"],
        "detectedColumns": columns,
        "detectedRows": rows,
        "meanCornerErrorSquares": round_metric(float(np.mean(deltas) / max(1.0, square))),
        "maxCornerErrorSquares": round_metric(float(np.max(deltas) / max(1.0, square))),
        "confidence": payload.get("confidence"),
    }


def label_corners(label: dict[str, Any]) -> np.ndarray:
    return np.float32([[point["x"], point["y"]] for point in label["corners"]])


def average_truth_square_pixels(label: dict[str, Any]) -> float:
    corners = label_corners(label)
    columns = max(1, int(label["columns"]))
    rows = max(1, int(label["rows"]))
    top = np.linalg.norm(corners[1] - corners[0]) / columns
    bottom = np.linalg.norm(corners[2] - corners[3]) / columns
    left = np.linalg.norm(corners[3] - corners[0]) / rows
    right = np.linalg.norm(corners[2] - corners[1]) / rows
    return float(np.mean([top, bottom, left, right]))


def extract_openai_output_text(payload: dict[str, Any]) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    chunks: list[str] = []
    for item in payload.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and "text" in content:
                chunks.append(content["text"])
    return "\n".join(chunks)


def extract_json_from_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def write_contact_sheet(out_dir: Path, results: list[dict[str, Any]], input_path: Path) -> None:
    image_paths = [input_path] + [Path(result["outputImage"]) for result in results if result.get("outputImage")]
    if not image_paths:
        return
    thumbs: list[Image.Image] = []
    labels: list[str] = ["input"]
    for path in image_paths:
        with Image.open(path) as image:
            thumb = ImageOps.exif_transpose(image).convert("RGB")
            thumb.thumbnail((320, 430), Image.Resampling.LANCZOS)
            canvas = Image.new("RGB", (340, 470), (245, 245, 245))
            canvas.paste(thumb, ((340 - thumb.width) // 2, 12))
            thumbs.append(canvas)
            if path != input_path:
                labels.append(path.stem)
    sheet = Image.new("RGB", (340 * len(thumbs), 470), (230, 230, 230))
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, (index * 340, 0))
    sheet.save(out_dir / "contact-sheet.jpg", quality=92)


def render_console_summary(report: dict[str, Any]) -> str:
    lines = [f"AI grid experiment report: {report['sourceId']}"]
    for result in report["results"]:
        if not result.get("ok"):
            lines.append(f"- {result['experimentId']}: ERROR {result.get('error')} ({result.get('elapsedMs')}ms)")
            continue
        if result["kind"] == "json_grid":
            score = result.get("jsonScore", {})
            lines.append(
                f"- {result['experimentId']}: json rows/cols {score.get('detectedColumns')}x{score.get('detectedRows')} "
                f"mean/max {score.get('meanCornerErrorSquares')}/{score.get('maxCornerErrorSquares')} sq "
                f"({result.get('elapsedMs')}ms)"
            )
        elif result["kind"] == "dot_mask":
            score = result.get("imageScore", {})
            dot = score.get("dotScore", {})
            lines.append(
                f"- {result['experimentId']}: {score.get('width')}x{score.get('height')} "
                f"dots {dot.get('matchedVisibleIntersections')}/{dot.get('visibleExpectedIntersections')} "
                f"ratio {dot.get('matchedVisibleIntersectionRatio')} err {dot.get('medianIntersectionErrorSquares')} "
                f"({result.get('elapsedMs')}ms)"
            )
        else:
            score = result.get("imageScore", {})
            coverage = score.get("coverage", {})
            alignment = score.get("alignment", {})
            lines.append(
                f"- {result['experimentId']}: {score.get('width')}x{score.get('height')} "
                f"coverage {coverage.get('lineMeanCoverage')} align<=.10 {alignment.get('pointsWithin0_10SquaresPct')}% "
                f"signal {score.get('signalPct')}% ({result.get('elapsedMs')}ms)"
            )
    lines.append(f"Artifacts: {report_path(report)}")
    return "\n".join(lines)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Grid Experiment",
        "",
        f"- Source: `{report['sourceId']}`",
        f"- Input working image: `{report['inputWorkingImage']}`",
        f"- Generated: `{report['generatedAt']}`",
        "",
        "| Experiment | OK | Elapsed ms | Output | Key score |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for result in report["results"]:
        if result.get("ok") and result["kind"] == "json_grid":
            score = result.get("jsonScore", {})
            key = f"{score.get('detectedColumns')}x{score.get('detectedRows')}; mean/max {score.get('meanCornerErrorSquares')}/{score.get('maxCornerErrorSquares')} sq"
            output = result.get("outputJson", "")
        elif result.get("ok") and result["kind"] == "dot_mask":
            score = result.get("imageScore", {})
            dot = score.get("dotScore", {})
            key = f"dots {dot.get('matchedVisibleIntersections')}/{dot.get('visibleExpectedIntersections')}; ratio {dot.get('matchedVisibleIntersectionRatio')}; err {dot.get('medianIntersectionErrorSquares')}"
            output = result.get("outputImage", "")
        elif result.get("ok"):
            score = result.get("imageScore", {})
            coverage = score.get("coverage", {})
            alignment = score.get("alignment", {})
            key = f"coverage {coverage.get('lineMeanCoverage')}; <=.10 {alignment.get('pointsWithin0_10SquaresPct')}%; signal {score.get('signalPct')}%"
            output = result.get("outputImage", "")
        else:
            key = str(result.get("error"))
            output = ""
        lines.append(f"| `{result['experimentId']}` | {result.get('ok')} | {result.get('elapsedMs')} | `{output}` | {key} |")
    lines.extend(["", f"Contact sheet: `{Path(report_path(report)).with_name('contact-sheet.jpg')}`", ""])
    return "\n".join(lines)


def report_path(report: dict[str, Any]) -> str:
    return str(Path(report["inputWorkingImage"]).parents[1] / "report.md")


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def round_metric(value: float) -> float:
    return round(float(value), 3)


def iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    main()
