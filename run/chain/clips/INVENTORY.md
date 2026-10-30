# Optional video assets

Video files are not included in the participant repository. Recorded text observations
in `../descriptions/` support inference without the videos. Supply locally authorized
MP4 files with these names to enable playback:

| Filename | Consumer |
|---|---|
| `civil-market.mp4` | Browser and course |
| `port-container-transport.mp4` | Browser |
| `convoy-truck-road.mp4` | Browser and course |
| `sample-drone-bridge.mp4` | Browser and course |
| `degraded-mountain-fog.mp4` | Browser and course |
| `port-containers-cranes.mp4` | Course |

Run `python3 run/workshop/scripts/build_posters.py` from the repository root to
create browser thumbnails from supplied clips. Missing videos do not prevent the
browser's recorded-description inference or replay. Notebook 09's video player
requires its selected clip; its text-based agent exercise uses the recorded description.
Live VSS perception additionally requires the clips to be registered in the separate
VSS deployment. A file in this directory alone does not register it.
