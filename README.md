# Ghost Studio Gemini

A local-first AI-assisted video editing studio for Windows. Gemini acts as the editing director; FFmpeg handles media operations locally.

## Status
Early foundation build: local video import, FFprobe inspection, explicit Gemini video analysis, JSON edit plan and FFmpeg rough-cut rendering. This is not yet a complete feature-for-feature port of Ghost Editor.

## Windows quick start
1. Install Python 3.11+ and FFmpeg. Check that ffmpeg and ffprobe work in PowerShell.
2. Clone this repository and open PowerShell in its folder.
3. Run: py -3.11 -m venv .venv
4. Run: .\.venv\Scripts\Activate.ps1
5. Run: pip install -r requirements.txt
6. Copy .env.example to .env and add your Gemini API key from https://aistudio.google.com/apikey.
7. Run: python app.py, then open http://127.0.0.1:8765.

You can open the app without a Gemini key; AI analysis requires one. Media probing and FFmpeg rendering are local. When you click Analyze with Gemini, the selected video is uploaded to Google's Gemini API. The app does not silently upload footage.

## Roadmap
Transcription with word timestamps, pause removal, face-aware reframing, timeline editing, motion graphics, preview renders and automated render QA.

## Relationship to Ghost Editor
An independent implementation inspired by the workflow and ideas of the open-source Ghost Editor: https://github.com/kurbaitaev/ghost-editor. This repository is not the upstream project and does not claim ownership of upstream code or assets. We will review the upstream license and preserve required notices before adapting or incorporating any upstream material. Attribution will be maintained as the project develops.

## License
Original code in this repository is released under the MIT License. This does not relicense third-party code, assets, trademarks or media. See LICENSE.
