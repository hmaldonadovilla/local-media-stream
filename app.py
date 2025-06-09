import os
import threading
from flask import Flask, request, redirect, url_for, render_template_string, session
from dotenv import load_dotenv

from stream import run_ffmpeg, validate_paths

# Load environment variables from a .env file if present
load_dotenv()

# Base directory with video files
MOVIES_DIR = os.getenv("MOVIES_DIR", os.path.expanduser("~/Movies"))

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change_this_secret")

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

    entries = []
    for name in sorted(os.listdir(abs_path)):
        full = os.path.join(abs_path, name)
        entries.append({'name': name, 'is_dir': os.path.isdir(full)})

    template = '''
    <h1>Browse {{ rel_path or '/' }}</h1>
    {% if session.get('video') %}<p>Video: {{ session['video'] }}</p>{% endif %}
    {% if session.get('subtitle') %}<p>Subtitle: {{ session['subtitle'] }}</p>{% endif %}
    <form action="{{ url_for('start_stream') }}" method="post">
        Delay (s): <input name="delay" value="{{ session.get('delay', 1.5) }}">
        <input type="submit" value="Start Streaming">
    </form>
    <ul>
        {% if rel_path %}<li><a href="{{ url_for('browse', path=parent) }}">..</a></li>{% endif %}
        {% for e in entries %}
            {% if e.is_dir %}
                <li>[DIR] <a href="{{ url_for('browse', path=join(rel_path, e.name)) }}">{{ e.name }}</a></li>
            {% else %}
                <li>{{ e.name }} - <a href="{{ url_for('select_file', type='video', path=join(rel_path, e.name)) }}">video</a>
                <a href="{{ url_for('select_file', type='subtitle', path=join(rel_path, e.name)) }}">subtitle</a></li>
            {% endif %}
        {% endfor %}
    </ul>
    '''
    return render_template_string(template, entries=entries, rel_path=rel_path,
                                  parent=os.path.dirname(rel_path), join=os.path.join)

@app.route('/select')
def select_file():
    ftype = request.args.get('type')
    rel_path = request.args.get('path')
    if ftype not in {'video', 'subtitle'} or rel_path is None:
        return 'Invalid selection', 400
    abs_path = secure_path(rel_path)
    if not os.path.isfile(abs_path):
        return 'Not a file', 400
    session[ftype] = rel_path
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
        run_ffmpeg(movie_path, subtitle_path, stream_folder, 8000, delay)

    threading.Thread(target=worker, daemon=True).start()
    return 'Streaming started on http://localhost:8000/output.m3u8'

if __name__ == '__main__':
    app.run(debug=True)
