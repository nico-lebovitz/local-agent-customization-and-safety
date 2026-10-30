"""Create local scene-card thumbnails from the workshop's local video assets."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
DESTINATION = ROOT / 'run/workshop/static/posters'
CLIPS = ('civil-market', 'port-container-transport', 'convoy-truck-road',
         'sample-drone-bridge', 'degraded-mountain-fog')

if __name__ == '__main__':
    DESTINATION.mkdir(exist_ok=True)
    for clip in CLIPS:
        source = ROOT / 'run/chain/clips' / f'{clip}.mp4'
        if not source.is_file():
            print(f'SKIPPED: missing local clip {clip}')
            continue
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-ss', '1', '-i', str(source),
                        '-frames:v', '1', '-vf', 'scale=640:-1', '-q:v', '5', '-y',
                        str(DESTINATION / f'{clip}.jpg')], check=True)
        print(f'Created {clip}.jpg')
