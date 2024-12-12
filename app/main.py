"""
main.py

This is the entry point for the Image Downloader web application.
The application allows users to:
- Upload a CSV file containing image URLs.
- Parse the file to extract the image URLs.
- Download the images to a local directory.
- Provide feedback on the download process.

Version: 1.0.0
Author: Neil Randle
Date: 2024.12.12
"""
import os
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from PIL import Image
import pandas as pd
import requests
from urllib.parse import urlparse
from datetime import datetime

app = Flask(__name__)

# Folder to save uploaded files and downloaded images
UPLOAD_FOLDER = 'uploads'
DOWNLOAD_FOLDER = 'downloads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER

# Route: Home Page
@app.route('/')
def home():
    """Render the homepage with the file upload form."""
    return render_template('index.html')

# Route: File Upload and Process
@app.route('/upload', methods=['POST'])
def upload_file():
    """Handle CSV file upload and image downloading."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part in the request."}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected for uploading."}), 400
    
    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        
        try:
            # Process the CSV file
            image_urls = extract_image_urls(filepath)
            if not image_urls:
                return jsonify({"error": "No valid image URLs found in the CSV."}), 400
            
            # Download images to the main downloads folder
            download_images(image_urls, DOWNLOAD_FOLDER)
            
            return jsonify({
                "message": "Images downloaded successfully.",
                "image_count": len(image_urls),
                "download_folder": DOWNLOAD_FOLDER
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

# Route: Convert Images to JPG
@app.route('/convert', methods=['POST'])
def convert_images():
    """Convert images in the download folder to JPG format."""
    try:
        # Convert all images in the downloads folder one at a time
        image_files = [file for file in os.listdir(DOWNLOAD_FOLDER) if file.lower().endswith(('png', 'gif', 'bmp'))]
        for image_file in image_files:
            file_path = Path(DOWNLOAD_FOLDER) / image_file
            convert_to_jpg_with_white_background(file_path)
        
        return jsonify({"message": "Images converted to JPG."}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

from PIL import Image

# Function: Convert Image to JPG with White Background
def convert_to_jpg_with_white_background(image_path):
    """Convert an image to JPG format with a white background for transparent images."""
    try:
        with Image.open(image_path) as img:
            # Check if image has an alpha channel (RGBA or other)
            if img.mode == 'RGBA':
                # Create a white background
                background = Image.new('RGBA', img.size, (255, 255, 255, 255))  # White background
                background.paste(img, (0, 0), img)  # Paste the image onto the white background
                img = background.convert('RGB')  # Convert to RGB to drop the alpha channel
            elif img.mode in ['LA', 'P']:  # Handle images with palette-based transparency (like PNG-8)
                img = img.convert('RGBA')  # Convert palette-based image to RGBA
                background = Image.new('RGBA', img.size, (255, 255, 255, 255))  # White background
                background.paste(img, (0, 0), img)  # Paste with transparency mask
                img = background.convert('RGB')  # Convert to RGB
            else:
                # For images already in RGB mode (no transparency), just convert to RGB
                img = img.convert('RGB')

            # Save as JPG with high quality or PNG for lossless
            jpg_path = image_path.with_suffix('.jpg')
            img.save(jpg_path, 'JPEG', quality=95)  # Adjust the quality (1-100), 95 is near lossless

            # Optionally, save as PNG for completely lossless
            # png_path = image_path.with_suffix('.png')
            # img.save(png_path, 'PNG')

            # Optionally, delete the original image
            os.remove(image_path)
            
    except Exception as e:
        print(f"Failed to convert {image_path}: {e}")

# Function: Extract Image URLs from CSV
def extract_image_urls(csv_path):
    """Read the CSV file and extract image URLs from the '1000image' column."""
    df = pd.read_csv(csv_path)
    if '1000image' not in df.columns:
        raise ValueError("The CSV file must contain a '1000image' column.")
    return df['1000image'].dropna().tolist()

# Function: Download Images
def download_images(image_urls, folder_path):
    """Download images from the given URLs to the specified folder."""
    for url in image_urls:
        try:
            # Parse the URL to get the filename
            parsed_url = urlparse(url)
            filename = os.path.basename(parsed_url.path)
            file_path = Path(folder_path) / filename
            
            # Download the image
            response = requests.get(url, stream=True)
            if response.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
        except Exception as e:
            print(f"Failed to download {url}: {e}")

# Run the app
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)