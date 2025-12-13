from flask import Flask, Response, jsonify, request, abort, send_file, stream_with_context
from PIL import Image
import requests
import yt_dlp
import ffmpeg
import cv2
import glob
import os
import time
import math

app = Flask(__name__)
active_video_downloads = set()

DOWNLOADS_DIR = "dl"
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
                abort(404)

            frames, frame_count, width, duration, fps, fps_step = extract_frame_rgb_pixels(video_id, video_start_frame - 1)
            if frames == "":
                return jsonify({ "result": "end" })
            return jsonify({ "result": f"{frame_count},{frames}" })
        elif data.startswith("vid_prep_"):
            video_id = data[9:]
            #video_info = download_video(video_id)
            download_video(video_id)

            frames, frame_count, width, duration, fps, fps_step = extract_frame_rgb_pixels(video_id)
            if frames == "":
                return jsonify({ "result": "end" })
            return jsonify({ "result": f"{width},{VIDEO_HEIGHT},{duration},{fps},{fps_step},{frame_count},{frames}" })
        elif data.startswith("vid_"):
            video_id = data[4:]
            if video_id in active_video_downloads:
                return jsonify({ "result": "processing" })
            elif not os.path.isfile(f"{DOWNLOADS_DIR}/{video_id}_video.mp4"):
                abort(404)

            frames, frame_count, width, duration, fps, fps_step = extract_frame_rgb_pixels(video_id)
            if frames == "":
                return jsonify({ "result": "end" })
            return jsonify({ "result": f"{width},{VIDEO_HEIGHT},{duration},{fps},{fps_step},{frame_count},{frames}" })
        abort(404)

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
                    .output('pipe:', format='mp3', acodec='copy')
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

    #with yt_dlp.YoutubeDL({"quiet": True}) as meta:
        #info = meta.extract_info(video_id, download=False)
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

    #return info

def extract_frame_rgb_pixels(video_id, start_frame=0):
    vid = cv2.VideoCapture(f"{DOWNLOADS_DIR}/{video_id}_video.mp4")

    fps = round(vid.get(cv2.CAP_PROP_FPS))
    duration = int(vid.get(cv2.CAP_PROP_FRAME_COUNT)) / fps
    fps_step = round(fps / VIDEO_TARGET_FPS)

    end_frame = start_frame + VIDEO_FRAMES_IN_RESPONSE - 1

    width = 0
    frame_id = 0
    all_frame_pixels = ""

    count = 0
    while True:
        success, frame = vid.read()
        if not success:
            break

        if count % fps_step == 0:
            if frame_id < start_frame:
                frame_id += 1
            elif frame_id > end_frame:
                break
            else:
                if width == 0:
                    width = get_width(frame)

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                frame = cv2.resize(frame, (width, VIDEO_HEIGHT))

                pixels = frame.reshape(-1, 3)
                hex_pixels = [f"{r:02X}{g:02X}{b:02X}" for r, g, b in pixels]
                all_frame_pixels += "".join(hex_pixels)

                frame_id += 1

        count += 1

    vid.release()
    return all_frame_pixels, frame_id - start_frame, width, duration, fps, fps_step

def get_width(frame):
    h, w = frame.shape[:2]
    return round(w / h * VIDEO_HEIGHT)


if __name__ == '__main__': 
    app.run(host='127.0.0.1', port=80)


# def sum_rgb_pixels(path):
    # img = Image.open(path).convert("RGB")

    # w, h = img.size
    # width = round(w / h * VIDEO_HEIGHT)
    # img = img.resize((width, VIDEO_HEIGHT))

    # pixels = list(img.getdata())
    # hex_pixels = [f"{r:02X}{g:02X}{b:02X}" for (r, g, b) in pixels]

    # grid = [
        # hex_pixels[i*width:(i+1)*width]
        # for i in range(VIDEO_HEIGHT)
    # ]
    # return "".join(
        # val for row in grid for val in row
    # )
