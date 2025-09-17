"""main.py

Main entry point for the Image Downloader web application.
The application allows users to download images from CSV files,
drag-and-drop local images for conversion, and manage advanced
conversion settings.

Version: 1.3.0
Author: Cyb3rWaste
Date: 2025.09.17
"""

from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import requests
from flask import Flask, jsonify, render_template, request
from PIL import Image, UnidentifiedImageError
from urllib.parse import urlparse
from werkzeug.utils import secure_filename

app = Flask(__name__)

UPLOAD_FOLDER = Path("uploads")
CSV_UPLOAD_FOLDER = UPLOAD_FOLDER / "csv"
DOWNLOAD_ROOT = Path("downloads")
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}
DEFAULT_QUALITY = 95
DEFAULT_CSV_COLUMN = "1000image"

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
CSV_UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)

app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["CSV_UPLOAD_FOLDER"] = str(CSV_UPLOAD_FOLDER)
app.config["DOWNLOAD_ROOT"] = str(DOWNLOAD_ROOT)
app.config["DEFAULT_QUALITY"] = DEFAULT_QUALITY
app.config["DEFAULT_CSV_COLUMN"] = DEFAULT_CSV_COLUMN


def get_daily_folder() -> Path:
    """Return (and create if needed) today's dated download folder."""
    folder_name = datetime.now().strftime("%Y.%m.%d - Images")
    daily_folder = DOWNLOAD_ROOT / folder_name
    daily_folder.mkdir(parents=True, exist_ok=True)
    return daily_folder


def get_latest_folder() -> Path:
    """Return the latest dated folder or create today's folder."""
    subdirectories = [path for path in DOWNLOAD_ROOT.iterdir() if path.is_dir()]
    if not subdirectories:
        return get_daily_folder()
    return max(subdirectories, key=lambda path: path.stat().st_mtime)


def sanitize_target_folder(folder: Optional[str]) -> Path:
    """Ensure the requested folder lives inside DOWNLOAD_ROOT."""
    if not folder:
        return get_latest_folder()
    candidate = Path(folder)
    if not candidate.is_absolute():
        candidate = DOWNLOAD_ROOT / candidate
    try:
        candidate.resolve().relative_to(DOWNLOAD_ROOT.resolve())
    except ValueError:
        return get_latest_folder()
    candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def get_unique_path(directory: Path, filename: str) -> Path:
    """Return a filesystem-safe unique path within a directory."""
    safe_name = secure_filename(filename) or "image.jpg"
    path = directory / safe_name
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix or ".jpg"
    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def parse_quality(value) -> int:
    """Clamp requested JPEG quality to Pillow's expected range."""
    try:
        quality = int(value)
    except (TypeError, ValueError):
        return DEFAULT_QUALITY
    return max(1, min(quality, 100))


def coerce_bool(value) -> bool:
    """Interpret common truthy values."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def sanitize_sku(value: Optional[str]) -> Optional[str]:
    """Return a safe SKU fragment suitable for embedding in filenames."""
    if value is None:
        return None
    candidate = secure_filename(str(value).strip())
    cleaned = candidate.replace("_", "-")
    return cleaned or None


def build_output_filename(
    source_path: Path,
    extension: str,
    *,
    include_suffix: bool = False,
    sku: Optional[str] = None,
) -> Path:
    """Return a unique filename, optionally appending SKU details and a -web suffix."""
    base_name = source_path.stem
    parts: list[str] = [base_name]

    if include_suffix:
        normalized = sanitize_sku(sku)
        if normalized:
            parts.append(normalized)
        parts.append("web")

    candidate_name = "-".join(filter(None, parts))
    safe_stem = secure_filename(candidate_name).replace("_", "-") or "image"
    candidate_with_extension = f"{safe_stem}{extension}"
    return get_unique_path(source_path.parent, candidate_with_extension)


def convert_image_for_web(
    image_path: Path,
    *,
    quality: int,
    keep_png: bool,
    enhance_filenames: bool = False,
    sku: Optional[str] = None,
) -> Optional[Path]:
    """Convert or rename an image according to the requested output format."""
    suffix = image_path.suffix.lower()
    sku_fragment = sku if enhance_filenames else None

    if suffix == ".png" and keep_png:
        if enhance_filenames:
            target_path = build_output_filename(
                image_path,
                ".png",
                include_suffix=True,
                sku=sku_fragment,
            )
            try:
                return image_path.rename(target_path)
            except OSError as exc:  # pragma: no cover - rename failures are rare
                print(f"Failed to rename {image_path} to PNG web version: {exc}")
                return None
        return image_path

    try:
        with Image.open(image_path) as img:
            if img.mode in ("RGBA", "LA"):
                rgba_image = img.convert("RGBA")
                background = Image.new("RGBA", rgba_image.size, (255, 255, 255, 255))
                background.paste(rgba_image, mask=rgba_image.split()[3])
                working = background.convert("RGB")
            elif img.mode == "P":
                rgba_image = img.convert("RGBA")
                background = Image.new("RGBA", rgba_image.size, (255, 255, 255, 255))
                background.paste(rgba_image, mask=rgba_image.split()[3])
                working = background.convert("RGB")
            else:
                working = img.convert("RGB")

        target_path = build_output_filename(
            image_path,
            ".jpg",
            include_suffix=enhance_filenames,
            sku=sku_fragment,
        )
        working.save(target_path, "JPEG", quality=quality, optimize=True)
    except (UnidentifiedImageError, OSError) as exc:
        print(f"Failed to convert {image_path}: {exc}")
        return None

    if target_path != image_path and image_path.exists():
        image_path.unlink(missing_ok=True)

    return target_path


def post_process_files(
    file_jobs: Iterable[tuple[Path, Optional[str]]],
    quality: int,
    keep_png: bool,
    enhance_filenames: bool,
) -> tuple[list[str], list[str]]:
    """Convert downloaded or uploaded files and return processed + failed names."""
    processed: list[str] = []
    failed: list[str] = []

    for path, sku in file_jobs:
        result = convert_image_for_web(
            path,
            quality=quality,
            keep_png=keep_png,
            enhance_filenames=enhance_filenames,
            sku=sku,
        )
        if result:
            processed.append(result.name)
        else:
            failed.append(path.name)

    return processed, failed


def create_upload_token() -> str:
    """Generate a token for temporary CSV storage."""
    return secrets.token_urlsafe(16)


def store_csv_upload(file_storage) -> tuple[str, Path, str]:
    """Persist an uploaded CSV and return its token and details."""
    token = create_upload_token()
    target_path = CSV_UPLOAD_FOLDER / f"{token}.csv"
    file_storage.save(target_path)
    original_name = file_storage.filename or "upload.csv"
    return token, target_path, original_name


def resolve_upload_token(token: str) -> Path:
    """Translate a token back into a CSV path."""
    safe_token = secure_filename(token)
    if not safe_token:
        raise FileNotFoundError("Invalid upload token.")
    candidate = CSV_UPLOAD_FOLDER / f"{safe_token}.csv"
    if not candidate.exists():
        raise FileNotFoundError("The CSV upload token has expired or is invalid.")
    return candidate


def list_csv_columns(csv_path: Path) -> list[str]:
    """Return the header row for a CSV file."""
    df = pd.read_csv(csv_path, nrows=0)
    columns = [str(column) for column in df.columns]
    if not columns:
        raise ValueError("The CSV file did not contain any column headings.")
    return columns


def extract_image_records(
    csv_path: Path,
    column: str,
) -> tuple[list[tuple[str, Optional[str]]], Optional[str]]:
    """Read the CSV file and return (url, sku) records for the requested column."""
    df = pd.read_csv(csv_path)
    if column not in df.columns:
        raise ValueError(f"The CSV file must contain a '{column}' column.")

    sku_column: Optional[str] = None
    for candidate in df.columns:
        name = str(candidate).strip().lower()
        if name == "sku":
            sku_column = candidate
            break

    records: list[tuple[str, Optional[str]]] = []
    for _, row in df.iterrows():
        raw_url = row[column]
        if pd.isna(raw_url):
            continue
        url = str(raw_url).strip()
        if not url:
            continue
        sku_value: Optional[str] = None
        if sku_column is not None:
            raw_sku = row[sku_column]
            if pd.notna(raw_sku):
                sku_value = str(raw_sku).strip()
        records.append((url, sku_value))

    return records, sku_column


def download_images(
    image_records: Iterable[tuple[str, Optional[str]]],
    folder_path: Path,
) -> tuple[list[tuple[Path, Optional[str]]], list[str]]:
    """Download images from the given URLs to the specified folder."""
    downloaded: list[tuple[Path, Optional[str]]] = []
    failed: list[str] = []

    for url, sku in image_records:
        try:
            filename = Path(urlparse(url).path).name or "image.jpg"
            target_path = get_unique_path(folder_path, filename)
            response = requests.get(url, stream=True, timeout=20)
            response.raise_for_status()
            with target_path.open("wb") as output:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        output.write(chunk)
            downloaded.append((target_path, sku))
        except Exception as exc:  # pylint: disable=broad-except
            print(f"Failed to download {url}: {exc}")
            failed.append(url)

    return downloaded, failed


@app.route("/")
def home():
    """Render the homepage with configuration defaults."""
    return render_template(
        "index.html",
        default_quality=DEFAULT_QUALITY,
        default_column=DEFAULT_CSV_COLUMN,
    )


@app.route("/csv/prepare", methods=["POST"])
def prepare_csv():
    """Store a CSV upload and return available columns for selection."""
    csv_file = request.files.get("file")
    if not csv_file or csv_file.filename == "":
        return jsonify({"error": "No CSV file supplied."}), 400

    if Path(csv_file.filename).suffix.lower() != ".csv":
        return jsonify({"error": "The uploaded file must be a CSV."}), 400

    try:
        token, saved_path, display_name = store_csv_upload(csv_file)
    except Exception as exc:  # pylint: disable=broad-except
        return jsonify({"error": str(exc)}), 500

    try:
        columns = list_csv_columns(saved_path)
        default_column = DEFAULT_CSV_COLUMN if DEFAULT_CSV_COLUMN in columns else columns[0]
    except Exception as exc:  # pylint: disable=broad-except
        saved_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 400

    return (
        jsonify(
            {
                "token": token,
                "columns": columns,
                "default_column": default_column,
                "filename": display_name,
            }
        ),
        200,
    )


@app.route("/csv/process", methods=["POST"])
def process_csv():
    """Download and convert images defined in a prepared CSV."""
    payload = request.get_json(silent=True) or {}
    token = payload.get("token")
    column = payload.get("column") or DEFAULT_CSV_COLUMN
    quality = parse_quality(payload.get("quality"))
    keep_png = coerce_bool(payload.get("keep_png"))
    enhance_filenames = coerce_bool(payload.get("enhance_filenames"))

    if not token:
        return jsonify({"error": "Missing CSV token."}), 400

    try:
        csv_path = resolve_upload_token(token)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 400

    sku_column: Optional[str] = None
    try:
        image_records, sku_column = extract_image_records(csv_path, column)
    except ValueError as exc:
        csv_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:  # pylint: disable=broad-except
        csv_path.unlink(missing_ok=True)
        return jsonify({"error": str(exc)}), 500

    if not image_records:
        csv_path.unlink(missing_ok=True)
        return jsonify({"error": "No valid image URLs found in the selected column."}), 400

    target_folder = get_daily_folder()
    downloaded, download_failures = download_images(image_records, target_folder)
    processed, conversion_failures = post_process_files(
        downloaded,
        quality,
        keep_png,
        enhance_filenames,
    )

    sku_applied = False
    if enhance_filenames:
        for _, candidate_sku in downloaded:
            if sanitize_sku(candidate_sku):
                sku_applied = True
                break

    folder_key = str(target_folder.relative_to(DOWNLOAD_ROOT))
    csv_path.unlink(missing_ok=True)

    skipped = [f"Download failed: {url}" for url in download_failures]
    skipped.extend(f"Conversion failed: {name}" for name in conversion_failures)

    message = "No images were processed."
    if processed:
        message = f"Downloaded and processed {len(processed)} image(s)."

    response_payload = {
        "message": message,
        "processed": processed,
        "skipped": skipped,
        "folder_key": folder_key,
        "download_folder": f"{DOWNLOAD_ROOT.name}/{folder_key}",
        "quality": quality,
        "keep_png": keep_png,
        "enhance_filenames": enhance_filenames,
        "sku_applied": sku_applied,
        "column": column,
        "source": "csv",
    }

    if sku_column is not None:
        response_payload["sku_column"] = str(sku_column)

    if not processed:
        response_payload["note"] = "Verify the URLs and conversion settings, then try again."

    if enhance_filenames and sku_column is None:
        response_payload.setdefault(
            "note",
            "No SKU column detected; added only the -web suffix.",
        )
    elif enhance_filenames and not sku_applied:
        response_payload.setdefault(
            "note",
            "SKU values were empty or invalid; added only the -web suffix.",
        )

    if skipped:
        response_payload["skipped_count"] = len(skipped)

    return jsonify(response_payload), 200


@app.route("/upload-images", methods=["POST"])
def upload_images():
    """Accept drag-and-drop image uploads for conversion and compression."""
    files = request.files.getlist("images")
    if not files:
        return jsonify({"error": "No images supplied."}), 400

    quality = parse_quality(request.form.get("quality"))
    keep_png = coerce_bool(request.form.get("keep_png"))
    enhance_filenames = coerce_bool(request.form.get("enhance_filenames"))
    folder_key = request.form.get("folder_key")
    target_folder = sanitize_target_folder(folder_key) if folder_key else get_daily_folder()

    saved_paths: list[Path] = []
    skipped: list[str] = []

    for storage in files:
        if not storage.filename:
            skipped.append("Unnamed file")
            continue

        extension = Path(storage.filename).suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            skipped.append(f"Unsupported format: {storage.filename}")
            continue

        destination = get_unique_path(target_folder, storage.filename)
        storage.save(destination)
        saved_paths.append(destination)

    processed, conversion_failures = post_process_files(
        ((path, None) for path in saved_paths),
        quality,
        keep_png,
        enhance_filenames,
    )
    skipped.extend(f"Conversion failed: {name}" for name in conversion_failures)

    folder_key = str(target_folder.relative_to(DOWNLOAD_ROOT))

    message = "No images were processed."
    message_type = "info"
    if processed:
        message = f"Processed {len(processed)} image(s)."
        message_type = "success"

    response_payload = {
        "message": message,
        "message_type": message_type,
        "processed": processed,
        "skipped": skipped,
        "folder_key": folder_key,
        "download_folder": f"{DOWNLOAD_ROOT.name}/{folder_key}",
        "quality": quality,
        "keep_png": keep_png,
        "enhance_filenames": enhance_filenames,
        "sku_applied": False,
        "source": "images",
    }

    if skipped:
        response_payload["skipped_count"] = len(skipped)
        if processed:
            response_payload.setdefault("note", "Some files were skipped or failed to convert.")
        else:
            response_payload.setdefault("note", "All files failed to process. Check formats and try again.")

    return jsonify(response_payload), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
