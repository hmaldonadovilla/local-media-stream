# Local Media Stream

This project provides a simple way to stream local video files with optional subtitle support. A Flask web interface allows browsing a movies folder, selecting a video and subtitle file, and starting the streaming process.

## Requirements

- Python 3.8+
- FFmpeg installed and available in your `PATH`

Use a virtual environment and install dependencies from `requirements.txt`.

## Environment Variables

- `MOVIES_DIR` (optional): Base directory containing your video files. Defaults to `~/Movies` if not set.
- `SECRET_KEY` (optional): Flask session secret. Defaults to `change_this_secret`.

## Running the Application

1. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env` and adjust the values if needed.

4. Ensure FFmpeg is installed on your system and accessible from the command line.

5. Run the Flask app:

   ```bash
   python app.py
   ```

   The interface will be available at `http://localhost:5000`.

6. Use the web interface to browse your `MOVIES_DIR`, select a video and optionally a subtitle file, set a subtitle delay (default is 1.5 seconds), and start streaming. The streaming output will be available at the displayed URL (`http://localhost:8000/output.m3u8`).

## Notes

If your movies folder is synchronized with a cloud storage provider such as OneDrive, the application will attempt to access the selected files so that they are downloaded locally before streaming.
