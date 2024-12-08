from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.logger import logger
import subprocess
import cv2
from picamera2 import Picamera2
import uvicorn

app = FastAPI()

# Serve static files
app.mount("/static", StaticFiles(directory="RaspberryPi-Baby-Monitor-Server"), name="static")

# Initialize camera
picam2 = Picamera2()
picam2.configure(picam2.create_preview_configuration(main={"size": (1296, 972)}))
picam2.start()

picam2.set_controls({
    "AwbEnable": True,
    "AeEnable": True,
    "AnalogueGain": 2.0
})


def generate_frames():
    while True:
        frame = picam2.capture_array()
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
        frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        _, buffer = cv2.imencode('.jpg', frame_rgb)
        frame_bytes = buffer.tobytes()

        try:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except (BrokenPipeError, ConnectionResetError):
            # Client disconnected
            break
        except Exception as e:
            logger.error(f"Video streaming error: {e}")
            break

def generate_audio(process):
    try:
        while True:
            chunk = process.stdout.read(4096)
            if not chunk:
                break
            yield chunk
    except Exception as e:
        logger.error(f"Audio streaming error: {e}")
    finally:
        if process and process.poll() is None:
            try:
                process.terminate()
                return_code = process.wait(timeout=1)
                logger.info(f"FFmpeg process terminated with code: {return_code}")
            except subprocess.TimeoutExpired:
                process.kill()
                logger.info("FFmpeg process killed due to timeout.")

        if process and process.stderr:
            try:
                stderr_output = process.stderr.read().decode('utf-8', errors='replace')
                if stderr_output.strip():
                    logger.error(f"FFmpeg error: {stderr_output}")
            except ValueError:
                pass

@app.get("/", response_class=HTMLResponse)
async def index():
    # Removed the button and JS related to toggling audio
    # Using autoplay on the audio element
    return """
    <html>
    <head>
        <link rel="manifest" href="/static/manifest.json">
        <link rel="apple-touch-icon" href="/static/imgs/icon.png">
        <link rel="icon" href="/static/imgs/icon.png" type="image/png">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <title>アリーくんカメラ</title>
        <style>
            body {
                margin: 0;
                padding: 0;
                background: url('/static/imgs/background.jpg') no-repeat center center fixed;
                background-size: cover;
                font-family: Arial, sans-serif;
                color: #fff;
            }
            h1 {
                margin: 20px 0;
                font-size: 36px;
                text-align: center;
                color: #fff;
                text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.7);
            }
            .container {
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: flex-start;
                height: 100vh;
                padding-top: 20px;
            }
            img {
                display: block;
                width: 100%;
                height: auto;
                max-width: 100%;
            }
            audio {
                margin-top: 20px;
                width: 300px;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>アリーくんカメラ</h1>
            <img src="/video_feed" alt="Video Stream">
            <audio id="audio_feed" autoplay muted src="/audio_feed"></audio>
            <script>
            document.body.addEventListener('click', function() {
                console.log('Body clicked on second load');
                const audio = document.getElementById('audio_feed');
                console.log('Attempting to unmute and play audio on second load');
                audio.muted = false;
                audio.play().then(() => console.log('Audio playing')).catch(err => console.error('Play error:', err));
            }, { once: true });
            </script>
        </div>
    </body>
    </html>
    """

@app.get("/video_feed")
async def video_feed(request: Request):
    async def video_generator():
        while True:
            if await request.is_disconnected():
                break
            frame = picam2.capture_array()
            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
            _, buffer = cv2.imencode('.jpg', frame_rgb)
            frame_bytes = buffer.tobytes()

            message = (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            try:
                yield message
            except (BrokenPipeError, ConnectionResetError):
                # Client disconnected
                break
            except Exception as e:
                logger.error(f"Video streaming error: {e}")
                break

    return StreamingResponse(video_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/audio_feed")
def audio_feed():
    command = [
        "ffmpeg",
        "-loglevel", "error",  # Only print errors, no warnings/info
        "-f", "alsa",
        "-i", "default",
        "-vn",
        "-acodec", "libmp3lame",
        "-ar", "44100",
        "-ac", "2",
        "-b:a", "128k",
        "-f", "mp3",
        "-"
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )



    return StreamingResponse(generate_audio(process), media_type="audio/mpeg", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0"
    })



@app.websocket("/ws/audio")
async def websocket_audio(websocket: WebSocket):
    await websocket.accept()
    command = ["arecord", "-D", "plughw:3,0", "-f", "cd"]
    process = None

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        while True:
            if process.poll() is not None:
                break
            try:
                audio_chunk = process.stdout.read1(1024)
                if not audio_chunk:
                    break
                await websocket.send_bytes(audio_chunk)
            except (BrokenPipeError, ConnectionResetError):
                break
            except Exception as e:
                logger.error(f"Error in websocket audio: {e}")
                break
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        if process and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
            except Exception as e:
                logger.error(f"Error cleaning up process: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
