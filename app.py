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

    # Show TV shortcut only at the root of MOVIES_DIR
    tv_exists = (rel_path == '' and os.path.isdir(os.path.join(MOVIES_DIR, 'TV')))
    selected_video = session.get('video')
    selected_sub = session.get('subtitle')
    delay = session.get('delay', 1.5)

    template = '''
<!doctype html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
body{font-family:sans-serif;margin:0;padding:0}
.header{position:sticky;top:0;background:#fff;display:grid;grid-template-columns:1fr auto;align-items:center;padding:1rem;box-shadow:0 2px 5px rgba(0,0,0,0.1);z-index:1000}
h1{margin:0;font-size:1.5rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.stream-btn{background:#6f42c1;color:#fff;border:none;border-radius:4px;padding:0.5rem 1rem;font-size:1rem;cursor:pointer}
.delay-input{margin-bottom:1rem}
.modal-actions{display:flex;justify-content:space-between;margin-top:1rem}
.modal-actions button{padding:0.5rem 1rem;font-size:1rem;border:none;border-radius:4px;cursor:pointer}
.container{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:10px;padding:10px}
.tile{border:1px solid #ccc;border-radius:4px;padding:10px;text-align:center;word-break:break-word;display:flex;flex-direction:column;justify-content:space-between;min-height:160px}
.tile.selected{background:#28a745;color:#fff}
.tile a.action{margin-top:5px;text-decoration:none;color:#fff;background:#007bff;padding:5px;border-radius:3px}
.icon{font-size:2rem}
.modal{display:none;position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);justify-content:center;align-items:flex-start;padding-top:50px;z-index:2000}
.modal-content{background:#fff;padding:20px;border-radius:5px;min-width:250px}
</style>
</head><body>
<div class="header">
  <h1>Browse {{ rel_path or '/' }}</h1>
  <button class="stream-btn" onclick="document.getElementById('panel').style.display='flex'">Streaming Panel</button>
</div>
<div class="container">
  {% if tv_exists %}
  <div class="tile">
    <div class="icon">📺</div>
    <span>TV</span>
    <a class="action" href="{{ url_for('browse', path='TV') }}">Open</a>
  </div>
  {% endif %}
  {% if rel_path %}
  <div class="tile">
    <div class="icon">📁</div>
    <a class="action" href="{{ url_for('browse', path=parent) }}">..</a>
  </div>
  {% endif %}
  {% for e in entries %}
  <div class="tile {% if e.path==selected_video or e.path==selected_sub %}selected{% endif %}">
    {% if e.is_dir %}
      <div class="icon">📁</div>
      <span>{{ e.name }}</span>
      <a class="action" href="{{ url_for('browse', path=e.path) }}">Open</a>
    {% else %}
      <div class="icon">🎞️</div>
      <span>{{ e.name }}</span>
      <a class="action" href="{{ url_for('select_file', path=e.path) }}">{% if e.type=='video' %}Select Video{% else %}Select Subtitle{% endif %}</a>
    {% endif %}
  </div>
  {% endfor %}
</div>

<div id="panel" class="modal" onclick="if(event.target.id=='panel')this.style.display='none'">
  <div class="modal-content">
    <h2>Streaming</h2>
    <p><u>Video</u>: {{ selected_video or 'None' }}</p>
    <p><u>Subtitle</u>: {{ selected_sub or 'None' }}</p>
    <form action="{{ url_for('start_stream') }}" method="post">
      {% if selected_sub %}
      <div class="delay-input">Delay (s): <input name="delay" value="{{ delay }}"></div>
      {% endif %}
      <div class="modal-actions">
        <button type="button" onclick="document.getElementById('panel').style.display='none'">Close</button>
        <button type="submit">Start Streaming</button>
      </div>
    </form>
  </div>
</div>
</body></html>
'''
    return render_template_string(
        template,
        entries=entries,
        rel_path=rel_path,
        parent=os.path.dirname(rel_path),
        selected_video=selected_video,
        selected_sub=selected_sub,
        delay=delay,
        tv_exists=tv_exists,
    )

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
