from flask import Flask, Response, jsonify, request, abort, send_file, stream_with_context
from PIL import Image
from fractions import Fraction
import io
import requests
import yt_dlp
import ffmpeg
import glob
import os
import time
import math

app = Flask(__name__)
active_video_downloads = set()

DOWNLOADS_DIR = "dl"
DELIMITER = "‡"
THUMBNAIL_HEIGHT = 180
VIDEO_HEIGHT = 54
VIDEO_MINUTE_LIMIT = 5
VIDEO_TARGET_FPS = 6
VIDEO_FRAMES_IN_RESPONSE = 50


@app.after_request
def addCorsHeaders(response):
    response.headers.add("Access-Control-Allow-Origin", "*")
    response.headers.add("Access-Control-Allow-Headers", "Content-Type")
    response.headers.add("Access-Control-Allow-Methods", "GET, OPTIONS")
    return response

@app.route('/translate', methods=['GET'])
def routeTranslate(): 
    if request.method == 'GET': 
        data = request.args["text"]
        if data.startswith("HTTP "):
            data = data[5:]

        if data == "try":
            return jsonify({ "result": "success" })
        elif data.startswith("vid_start_"):
            video_req = data[10:].split("_", 1)
            video_start_frame = int(video_req[0])
            video_id = video_req[1]
            if not os.path.isfile(f"{DOWNLOADS_DIR}/{video_id}_video.mp4"):
                return jsonify({ "result": "error" })

            frames, frame_count, width, duration, fps, fps_step = extract_frame_hex_pixels(video_id, video_start_frame - 1)
            if frames == "":
                return jsonify({ "result": "end" })
            return jsonify({ "result": f"{frame_count}{DELIMITER}{frames}" })
        elif data.startswith("vid_"):
            video_id = data[4:]
            if video_id in active_video_downloads:
                return jsonify({ "result": "processing" })
            download_video(video_id)

            video_info = extract_video_info(video_id)
            if video_info:
                video_title = video_info.get("title", "")
                video_channel_name = video_info.get("uploader", "")
                video_view_count = format_view_count(video_info.get("view_count"))
                video_likes = format_likes(video_info.get("like_count"))
                video_upload_date = format_upload_date(video_info.get("upload_date", "00000000"))

            frames, frame_count, width, duration, fps, fps_step = extract_frame_hex_pixels(video_id)
            if frames == "":
                return jsonify({ "result": "end" })
            return jsonify({ "result": f"{width}{DELIMITER}{VIDEO_HEIGHT}{DELIMITER}{duration}{DELIMITER}{fps}{DELIMITER}{fps_step}{DELIMITER}{video_title}{DELIMITER}{video_channel_name}{DELIMITER}{video_view_count}{DELIMITER}{video_likes}{DELIMITER}{video_upload_date}{DELIMITER}{frame_count}{DELIMITER}{frames}" })
        elif data.startswith("search_"):
            search_query = data[7:]
            search_result = search_videos(search_query, 3)

            if not "entries" in search_result:
                return jsonify({ "result": "error" })

            result = ""
            for _, video_info in enumerate(search_result["entries"], start=1):
                video_id = video_info.get("id")
                video_title = video_info.get("title", "")
                video_description = video_info.get("description", "")
                video_channel_name = video_info.get("uploader", "")
                video_view_count = format_view_count(video_info.get("view_count"))
                video_duration = format_duration(video_info.get("duration"))

                video_thumbnail = extract_thumbnail_hex_pixels(video_id)

                result += f"{video_id}{DELIMITER}{video_title}{DELIMITER}{video_description}{DELIMITER}{video_channel_name}{DELIMITER}{video_view_count}{DELIMITER}{video_duration}{DELIMITER}{video_thumbnail}{DELIMITER}"
            return jsonify({ "result": result })

        return jsonify({ "result": "error" })

@app.route('/synth', methods=['GET'])
def routeSynth():
    if request.method == 'GET': 
        data = request.args["text"]
        if data.startswith("HTTP "):
            data = data[5:]

        if data.startswith("audio_start_"):
            audio_req = data[12:].split("_", 1)
            audio_start_time = float(audio_req[0])
            video_id = audio_req[1]

            file = f"{DOWNLOADS_DIR}/{video_id}_audio.mp3"
            if not os.path.isfile(file):
                abort(404)

            def generate():
                process = (
                    ffmpeg
                    .input(file, ss=audio_start_time)
                    .output(
                        'pipe:',
                        format='mp3',
                        acodec='copy'
                    )
                    .run_async(pipe_stdout=True, pipe_stderr=True)
                )

                while True:
                    data = process.stdout.read(4096)
                    if not data:
                        break
                    yield data

                process.wait()

            return Response(
                stream_with_context(generate()),
                mimetype="audio/mpeg"
            )
        elif data.startswith("audio_"):
            video_id = data[6:]

            file = f"{DOWNLOADS_DIR}/{video_id}_audio.mp3"
            if not os.path.isfile(file):
                abort(404)

            return send_file(
                file,
                mimetype="audio/mpeg",
                as_attachment=False
            )
        abort(404)


def format_view_count(view_count):
    if view_count is None:
        formatted_view_count = "N/A"
    elif view_count >= 1_000_000_000:
        formatted_view_count = f"{view_count / 1_000_000_000:.1f}B"
    elif view_count >= 1_000_000:
        formatted_view_count = f"{view_count / 1_000_000:.1f}M"
    elif view_count >= 1_000:
        formatted_view_count = f"{view_count / 1_000:.1f}K"
    else:
        formatted_view_count = str(view_count)
    return formatted_view_count

def format_likes(likes):
    if likes is None:
        formatted_likes = "N/A"
    elif likes >= 1_000_000:
        formatted_likes = f"{likes / 1_000_000:.1f}M"
    elif likes >= 1_000:
        formatted_likes = f"{likes / 1_000:.1f}K"
    else:
        formatted_likes = str(likes)

def format_upload_date(upload_date):
    return f"{upload_date[6:]}.{upload_date[4:6]}.{upload_date[:4]}" if len(upload_date) == 8 else ""

def format_duration(duration):
    duration = int(duration)
    hours = duration // 3600
    minutes = (duration % 3600) // 60
    seconds = duration % 60
    if hours > 0:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def search_videos(query, num_results):
    ytdl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
        "extractor_args": {
            "youtube": ["approximate_date"],
            "youtubetab": ["approximate_date"],
        },
    }
    try:
        with yt_dlp.YoutubeDL(ytdl_opts) as meta:
            results = meta.extract_info(f"ytsearch{num_results}:{query}", download=False)
    except Exception as e:
        print(f"Error fetching search results for \"{query}\": {e}")

    return results

def extract_video_info(video_id):
    ytdl_opts = {
        "quiet": True,
        "skip_download": True,
    }
    try:
        with yt_dlp.YoutubeDL(ytdl_opts) as meta:
            info = meta.extract_info(video_id, download=False)
    except Exception as e:
        print(f"Error fetching metadata for video \"{video_id}\": {e}")

    return info

def download_video(video_id):
    video_opts = {
        "download_sections": {"*": f"0:00-{VIDEO_MINUTE_LIMIT}:00"},
        "format": "bestvideo[height<=144]",
        "merge_output_format": None,
        "outtmpl": f"{DOWNLOADS_DIR}/{video_id}_video.mp4",
        "noplaylist": True,
        "quiet": True,
    }
    audio_opts = {
        "download_sections": {"*": f"0:00-{VIDEO_MINUTE_LIMIT}:00"},
        "format": "bestaudio",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "outtmpl": f"{DOWNLOADS_DIR}/{video_id}_audio.%(ext)s",
        "noplaylist": True,
        "quiet": True,
    }

    active_video_downloads.add(video_id)
    try:
        if not os.path.isfile(f"{DOWNLOADS_DIR}/{video_id}_video.mp4"):
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                ydl.download([video_id])
        if not os.path.isfile(f"{DOWNLOADS_DIR}/{video_id}_audio.mp3"):
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                ydl.download([video_id])
    finally:
        active_video_downloads.remove(video_id)


def extract_thumbnail_hex_pixels(video_id):
    response = requests.get(f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
    response.raise_for_status()

    img = Image.open(io.BytesIO(response.content)).convert("RGB")

    orig_width, orig_height = img.size
    aspect_ratio = orig_width / orig_height
    target_width = int(THUMBNAIL_HEIGHT * aspect_ratio)
    img = img.resize((target_width, THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)

    frame_raw = img.tobytes()
    frame_size = len(frame_raw)

    pixels = memoryview(frame_raw)
    hex_pixels = [
        f"{pixels[i]:02X}{pixels[i+1]:02X}{pixels[i+2]:02X}"
        for i in range(0, frame_size, 3)
    ]
    return "".join(hex_pixels)

def extract_frame_hex_pixels(video_id, start_frame=0):
    video_path = f"{DOWNLOADS_DIR}/{video_id}_video.mp4"

    probe = ffmpeg.probe(video_path)
    stream = next(s for s in probe['streams'] if s['codec_type'] == 'video')

    fps = round(Fraction(stream['avg_frame_rate']))
    duration = int(float(stream.get('duration') or probe['format']['duration']))
    fps_step = round(fps / VIDEO_TARGET_FPS)

    width = (int(stream['width']) * VIDEO_HEIGHT) // int(stream['height'])
    frame_size = width * VIDEO_HEIGHT * 3 # RGB24 format

    process = (
        ffmpeg
        .input(video_path, ss=start_frame * fps_step / fps)
        .filter('select', f'not(mod(n,{fps_step}))')
        .filter('scale', width, VIDEO_HEIGHT)
        .output(
            'pipe:',
            format='rawvideo',
            pix_fmt='rgb24',
            vsync='vfr',
            vframes=VIDEO_FRAMES_IN_RESPONSE
        )
        .run_async(pipe_stdout=True, pipe_stderr=True)
    )

    frame_idx = 0
    all_frame_pixels = ""
    while True:
        frame_raw = process.stdout.read(frame_size)
        if len(frame_raw) < frame_size:
            break

        pixels = memoryview(frame_raw)
        hex_pixels = [
            f"{pixels[i]:02X}{pixels[i+1]:02X}{pixels[i+2]:02X}"
            for i in range(0, frame_size, 3)
        ]
        all_frame_pixels += "".join(hex_pixels)

        frame_idx += 1

    process.wait()
    return all_frame_pixels, frame_idx, width, duration, fps, fps_step


if __name__ == '__main__': 
    app.run(host='127.0.0.1', port=80)
