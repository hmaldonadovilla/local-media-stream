#!/usr/bin/env python3
"""
This module provides a command-line utility to:
1. Convert a given video + subtitle into an HLS playlist (with WebVTT subtitles).
2. Serve the generated files via a built-in Python HTTP server.

Usage:
    python convert_and_serve.py <relative_movie_path> <relative_subtitle_path>
Example:
    python convert_and_serve.py MyMovieFolder/myvideo.mp4 MyMovieFolder/mysubs.srt
"""

import argparse
import atexit
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
from typing import NoReturn

# Global variable to store the stream folder path for cleanup
STREAM_FOLDER_PATH = None

def cleanup_stream_folder():
    """
    Delete the stream folder when the program exits.
    This function is registered with atexit to ensure cleanup happens
    regardless of how the program terminates.
    """
    global STREAM_FOLDER_PATH
    if STREAM_FOLDER_PATH and os.path.exists(STREAM_FOLDER_PATH):
        print(f"\nCleaning up: Deleting stream folder at {STREAM_FOLDER_PATH}")
        try:
            shutil.rmtree(STREAM_FOLDER_PATH)
            print("Stream folder successfully deleted.")
        except Exception as e:
            print(f"Error deleting stream folder: {e}")

# Register the cleanup function to run at program exit
atexit.register(cleanup_stream_folder)

def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments using argparse.

    Returns:
        An argparse.Namespace object containing the parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Convert a video file into an HLS playlist with optional WebVTT subtitles, "
            "then serve the files via a local Python HTTP server. "
            "All paths must be given relative to the Movies/ folder."
        )
    )
    parser.add_argument(
        'movie_rel_path',
        help='Relative path to the movie file inside the Movies/ folder (e.g., MyMovieFolder/movie.mp4)'
    )
    parser.add_argument(
        '--subtitle-path', '-s',
        help='Optional: Relative path to the subtitle file inside the Movies/ folder (e.g., MyMovieFolder/subs.srt)'
    )
    parser.add_argument(
        '--subtitle-delay', '-d',
        type=float,
        default=0.0,
        help='Delay subtitles by specified number of seconds (can be negative, default: 0.0)'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=8000,
        help='Port number to serve the HLS stream (default: 8000)'
    )
    return parser.parse_args()

def validate_paths(movie_path: str, subtitle_path: str | None = None) -> None:
    """
    Validate that the required video file and optional subtitle file exist.

    Args:
        movie_path: The absolute path to the movie file.
        subtitle_path: Optional absolute path to the subtitle file.

    Raises:
        SystemExit: If any of the required paths are invalid.
    """
    if not os.path.isfile(movie_path):
        print(f"Error: Movie file '{movie_path}' not found.")
        sys.exit(1)

    if subtitle_path and not os.path.isfile(subtitle_path):
        print(f"Error: Subtitle file '{subtitle_path}' not found.")
        sys.exit(1)

def serve_output(stream_folder_path: str, port: int = 8000) -> NoReturn:
    """
    Launch a Python HTTP server to serve HLS files from the specified directory.

    Args:
        stream_folder_path: Directory containing HLS output files.
        port: The port on which the server will listen.

    Raises:
        KeyboardInterrupt: If the user stops the server manually.
    """
    os.chdir(stream_folder_path)
    handler = http.server.SimpleHTTPRequestHandler

    print(f"\nConversion complete! Serving HLS stream on http://localhost:{port}/output.m3u8")
    print(f"You can also access the HLS master playlist at http://localhost:{port}/master.m3u8")
    print("Press Ctrl+C to stop the server.")

    with socketserver.TCPServer(("", port), handler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nStopping server...")
            httpd.server_close()
            sys.exit(0)

def run_ffmpeg(
    movie_path: str,
    subtitle_path: str | None,
    stream_folder_path: str,
    port: int = 8000,
    subtitle_delay: float = 0.0
) -> None:
    """
    Execute an FFmpeg command to convert a movie and optional subtitle file
    into an HLS playlist with optional WebVTT subtitles.

    Args:
        movie_path: Path to the movie file.
        subtitle_path: Optional path to the subtitle file.
        stream_folder_path: Path where output HLS segments and playlists will be stored.
        port: Port number to serve the HLS stream on.
        subtitle_delay: Number of seconds to delay subtitles (can be negative).

    Raises:
        SystemExit: If FFmpeg fails.
    """
    # Set global stream folder path for cleanup
    global STREAM_FOLDER_PATH
    STREAM_FOLDER_PATH = stream_folder_path

    # Create stream folder if it doesn't exist
    os.makedirs(stream_folder_path, exist_ok=True)

    # Start with ffmpeg command and input files
    ffmpeg_command = ["ffmpeg"]
    
    # Add all input files first
    ffmpeg_command.extend(["-i", movie_path])
    if subtitle_path:
        if subtitle_delay != 0:
            ffmpeg_command.extend(["-itsoffset", str(subtitle_delay)])
        ffmpeg_command.extend(["-i", subtitle_path])

    # Add all mapping and codec options
    ffmpeg_command.extend([
        "-map", "0:v",     # Map video from first input
        "-map", "0:a",     # Map audio from first input
    ])
    
    if subtitle_path:
        ffmpeg_command.extend([
            "-map", "1:0"  # Map subtitles from second input
        ])

    # Add codec options
    ffmpeg_command.extend([
        "-c:v", "copy",    # Copy video codec
        "-c:a", "copy",    # Copy audio codec
    ])

    if subtitle_path:
        ffmpeg_command.extend([
            "-c:s", "webvtt"  # Convert subtitles to WebVTT format
        ])

    # Add output options
    ffmpeg_command.extend([
        "-start_number", "0",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-hls_segment_filename", os.path.join(stream_folder_path, "segment_%03d.ts"),
        os.path.join(stream_folder_path, "output.m3u8")
    ])

    print("Running FFmpeg command:")
    print(" ".join(ffmpeg_command))

    try:
        subprocess.run(ffmpeg_command, check=True)
        master_playlist_path = os.path.join(stream_folder_path, "master.m3u8")
        with open(master_playlist_path, "w") as master_playlist:
            master_playlist.write("#EXTM3U\n\n")
            # Add subtitle track to master playlist only if subtitles were provided
            if subtitle_path:
                master_playlist.write('#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="English",DEFAULT=NO,AUTOSELECT=YES,LANGUAGE="en",URI="output_vtt.m3u8"\n\n')
                master_playlist.write('#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1920x1080,SUBTITLES="subs"\n')
            else:
                master_playlist.write('#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1920x1080\n')
            master_playlist.write("output.m3u8\n")
    except subprocess.CalledProcessError as exc:
        print(f"FFmpeg failed with error code {exc.returncode}.")
        sys.exit(exc.returncode)

    # Serve the output
    serve_output(stream_folder_path, port)

def main() -> None:
    """
    Main function that orchestrates:
    1. Argument parsing (paths relative to Movies/).
    2. Path validation.
    3. FFmpeg HLS generation.
    4. Serving the output via an HTTP server.
    """
    args = parse_arguments()

    # Adjust this to your actual Movies directory path
    movies_dir = "/Users/a57321/Movies"

    # Build absolute paths
    movie_path = os.path.join(movies_dir, args.movie_rel_path)
    subtitle_path = os.path.join(movies_dir, args.subtitle_path) if args.subtitle_path else None

    # Validate input files
    validate_paths(movie_path, subtitle_path)

    # Figure out where the output should go (same folder as the movie)
    movie_folder_path = os.path.dirname(movie_path)
    stream_folder_path = os.path.join(movie_folder_path, "stream")
    
    # Set global stream folder path for cleanup
    global STREAM_FOLDER_PATH
    STREAM_FOLDER_PATH = stream_folder_path

    # Convert to HLS
    run_ffmpeg(movie_path, subtitle_path, stream_folder_path, args.port, args.subtitle_delay)

if __name__ == "__main__":
    main()