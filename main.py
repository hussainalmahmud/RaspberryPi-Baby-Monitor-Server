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
app.mount("/static", StaticFiles(directory="static"), name="static")

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
    """
    Generate frames from the camera and yield them as a stream of bytes.

    This function is used to stream the video feed to the web browser.

    1. Capture the frame from the camera.
    2. Convert the frame to BGR format. 
    3. Convert the frame to RGB format. 
    4. Encode the frame to JPEG format.
    5. Return the frame as a stream of bytes.
    returns:
        A stream of bytes representing the video feed.
    """
    # while True:
    frame = picam2.capture_array()
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    _, buffer = cv2.imencode('.jpg', frame_rgb)
    frame_bytes = buffer.tobytes()

    return frame_bytes

def generate_audio(process):
    """
    Generate audio from the microphone and yield it as a stream of bytes.

    This function is used to stream the audio feed to the web browser.

    1. Read the audio from the microphone.
    2. Yield the audio as a stream of bytes.

    returns:
        A stream of bytes representing the audio feed.
    """
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
    """
    Serve the index.html file.

    This function is used to serve the index.html file to the web browser.

    returns:
        The index.html file as a response.
    """

    return HTMLResponse(content=open("static/index.html", "r").read())

@app.get("/video_feed")
async def video_feed(request: Request):
    """
    Stream video from the camera to the web browser.

    This function is used to stream the video feed to the web browser.

    1. Generate the frames from the camera.
    2. Yield the frames as a stream of bytes.
    3. Return the streaming response with the video feed.

    returns:
        A streaming response with the video feed.
    """
    async def video_generator():
        while True:
            if await request.is_disconnected():
                break

            frame_bytes = generate_frames()

            message = (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            try:
                yield message
            except (BrokenPipeError, ConnectionResetError):
                break
            except Exception as e:
                logger.error(f"Video streaming error: {e}")
                break

    return StreamingResponse(video_generator(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/audio_feed")
def audio_feed():
    """
    Stream audio from the microphone to the web browser.

    
    This function is used to stream the audio feed to the web browser.

    1. Run the ffmpeg command to capture the audio from the microphone.
    2. Yield the audio as a stream of bytes.
    3. Return the streaming response with the audio feed.

    returns:
        A streaming response with the audio feed.
    """
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
    # Run the server
    uvicorn.run(app, host="0.0.0.0", port=8000)
