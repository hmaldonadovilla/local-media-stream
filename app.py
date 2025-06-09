import os
import threading
from flask import Flask, request, redirect, url_for, render_template_string, session
from dotenv import load_dotenv

from stream import run_ffmpeg, validate_paths
import shutil

# Load environment variables from a .env file if present
load_dotenv()

# Base directory with video files
MOVIES_DIR = os.getenv("MOVIES_DIR", os.path.expanduser("~/Movies"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_secret")
# supported file extensions
VIDEO_EXTS = {'.mp4', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.webm', '.ts'}
SUB_EXTS = {'.srt', '.vtt', '.ass', '.ssa'}

def secure_path(rel_path: str) -> str:
    """Return an absolute path inside MOVIES_DIR."""
    abs_path = os.path.abspath(os.path.join(MOVIES_DIR, rel_path))
    if not abs_path.startswith(os.path.abspath(MOVIES_DIR)):
        raise ValueError("Invalid path")
    return abs_path

def ensure_local(path: str) -> None:
    """Attempt to access the file so that OneDrive downloads it if needed."""
    try:
        with open(path, 'rb') as f:
            f.read(1)
    except Exception as exc:
        print(f"Warning: could not access {path}: {exc}")

@app.route('/')
def browse():
    rel_path = request.args.get('path', '')
    abs_path = secure_path(rel_path)

    # list folders first, then files; skip hidden files
    names = [n for n in os.listdir(abs_path) if not n.startswith('.')]
    dirs = [n for n in names if os.path.isdir(os.path.join(abs_path, n))]
    files = [n for n in names if os.path.isfile(os.path.join(abs_path, n))]
    dirs.sort(); files.sort()
    entries = []
    for name in dirs + files:
        rel = os.path.join(rel_path, name) if rel_path else name
        full = os.path.join(abs_path, name)
        entry = {'name': name, 'is_dir': os.path.isdir(full), 'path': rel}
        if not entry['is_dir']:
            ext = os.path.splitext(name)[1].lower()
            if ext in VIDEO_EXTS:
                entry['type'] = 'video'
            elif ext in SUB_EXTS:
                entry['type'] = 'subtitle'
            else:
                continue
        entries.append(entry)

    template = '''
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{font-family:sans-serif;margin:0;padding:0}
h1{padding:1rem}
.container{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;padding:10px}
.tile{border:1px solid #ccc;border-radius:4px;padding:10px;text-align:center;word-break:break-word}
.tile a{display:block;margin-top:5px;text-decoration:none;color:#fff;background:#007bff;padding:5px;border-radius:3px}
.icon{font-size:2rem}
</style>
</head><body>
<h1>Browse {{ rel_path or '/' }}</h1>
<div class="container">
  {% if rel_path %}
  <div class="tile">
    <div class="icon">📁</div>
    <a href="{{ url_for('browse', path=parent) }}">..</a>
  </div>
  {% endif %}
  {% for e in entries %}
  <div class="tile">
    {% if e.is_dir %}
      <div class="icon">📁</div>
      <span>{{ e.name }}</span>
      <a href="{{ url_for('browse', path=e.path) }}">Open</a>
    {% else %}
      <div class="icon">🎞️</div>
      <span>{{ e.name }}</span>
      <a href="{{ url_for('select_file', path=e.path) }}">{% if e.type=='video' %}Select Video{% else %}Select Subtitle{% endif %}</a>
    {% endif %}
  </div>
  {% endfor %}
</div>
<form action="{{ url_for('start_stream') }}" method="post" style="padding:10px;">
  Delay (s): <input name="delay" value="{{ session.get('delay',1.5) }}">
  <button type="submit">Start Streaming</button>
</form>
</body></html>
'''
    return render_template_string(template, entries=entries, rel_path=rel_path,
                                  parent=os.path.dirname(rel_path))

@app.route('/select')
def select_file():
    rel_path = request.args.get('path')
    if not rel_path:
        return 'Invalid selection', 400
    abs_path = secure_path(rel_path)
    if not os.path.isfile(abs_path):
        return 'Not a file', 400
    ext = os.path.splitext(rel_path)[1].lower()
    if ext in VIDEO_EXTS:
        session['video'] = rel_path
    elif ext in SUB_EXTS:
        session['subtitle'] = rel_path
    else:
        return 'Unsupported file type', 400
    return redirect(url_for('browse', path=os.path.dirname(rel_path)))

@app.route('/start', methods=['POST'])
def start_stream():
    delay = float(request.form.get('delay', 1.5))
    session['delay'] = delay
    video_rel = session.get('video')
    if not video_rel:
        return 'No video selected', 400
    subtitle_rel = session.get('subtitle')

    movie_path = secure_path(video_rel)
    subtitle_path = secure_path(subtitle_rel) if subtitle_rel else None

    validate_paths(movie_path, subtitle_path)
    ensure_local(movie_path)
    if subtitle_path:
        ensure_local(subtitle_path)

    movie_folder = os.path.dirname(movie_path)
    stream_folder = os.path.join(movie_folder, 'stream')

    def worker():
        run_ffmpeg(movie_path, subtitle_path, stream_folder, 9000, delay)

    threading.Thread(target=worker, daemon=True).start()
    host = request.host.split(':')[0]
    # Render a page showing the stream URL and a stop button
    template = '''
    <h1>Streaming started</h1>
    <p>Stream URL: <a href="http://{{ host }}:9000/output.m3u8">http://{{ host }}:9000/output.m3u8</a></p>
    <form action="{{ url_for('stop_stream') }}" method="post">
        <button type="submit">Stop Streaming</button>
    </form>
    '''
    return render_template_string(template, host=host)

@app.route('/stop_stream', methods=['POST'])
def stop_stream():
    # Stop streaming: cleanup the stream folder and reset session
    video_rel = session.pop('video', None)
    session.pop('subtitle', None)
    session.pop('delay', None)
    if video_rel:
        try:
            movie_path = secure_path(video_rel)
            stream_folder = os.path.join(os.path.dirname(movie_path), 'stream')
            shutil.rmtree(stream_folder, ignore_errors=True)
        except Exception:
            pass
    # Redirect back to browsing interface
    parent = os.path.dirname(video_rel) if video_rel else ''
    return redirect(url_for('browse', path=parent))

if __name__ == '__main__':
    # Run the Flask app on all network interfaces at port 6001
    app.run(debug=True, host='0.0.0.0', port=6001)
