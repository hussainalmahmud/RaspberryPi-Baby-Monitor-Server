# RaspberryPi-Baby-Monitor-Server

This code was tested on Raspberry Pi 4 Model B, a camera, and a microphone bought from Amazon.

Using `Python 3.11.2`

Used `Picamera2` to capture images from the camera.

Used `FastAPI` to serve the images and audio to the web browser.

Used `ffmpeg` to stream the audio from the microphone to the web browser.



## Folder structure

```
.
├── imgs
│   ├── background.jpg  // web server background
│   └── icon.png        // web server icon
├── LICENSE
├── main.py           // web server
├── manifest.json     // web server manifest
├── README.md         // readme file
└── requirements.txt  // dependencies

```

## How to run

Create a virtual environment and install the dependencies
```
python3 -m venv venv  
source venv/bin/activate
```

Install the dependencies
```
pip install -r requirements.txt
```

Run the server
```
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

You should get an output like this click the link and view the web server

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```


