#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from flask import Flask, request, send_file, jsonify
from openai import OpenAI
import os
import time
import torch
from scipy.io.wavfile import write as write_wav, read as read_wav

try:
    from openvoice.api import ToneColorConverter
    voice_clone_available = True
except:
    voice_clone_available = False
    print("Voice cloning not available")

app = Flask(__name__)

OPENAI_API_KEY = "Key"
OPENAI_VOICE = "nova"
english_ref = "english.wav"
japanese_ref = "japanese.wav"
converter_cfg = "checkpoints/converter/config.json"
converter_ckpt = "checkpoints/converter/checkpoint.pth"
output_dir = "output"

os.makedirs(output_dir, exist_ok=True)
client = OpenAI(api_key=OPENAI_API_KEY)

tone_converter = None
english_embedding = None
japanese_embedding = None

if voice_clone_available:
    try:
        print("Setting up voice clone")
        tone_converter = ToneColorConverter(converter_cfg, device="cpu")
        tone_converter.load_ckpt(converter_ckpt)

        if os.path.exists(english_ref):
            print(f"Loading English reference: {english_ref}")
            english_embedding = tone_converter.extract_se(english_ref)

        if os.path.exists(japanese_ref):
            print(f"Loading Japanese reference: {japanese_ref}")
            japanese_embedding = tone_converter.extract_se(japanese_ref)

        if not english_embedding and not japanese_embedding:
            print("No reference voices found")
            voice_clone_available = False
        else:
            print("Voice clone ready")
            if english_embedding:
                print("English voice loaded")
            if japanese_embedding:
                print("Japanese voice loaded")

            if english_embedding and not japanese_embedding:
                print("Using English voice for Japanese too")
                japanese_embedding = english_embedding
            elif japanese_embedding and not english_embedding:
                print("Using Japanese voice for English too")
                english_embedding = japanese_embedding

    except Exception as e:
        print(f"Failed to setup voice cloning: {e}")
        voice_clone_available = False


def guess_language(txt):
    jp_count = 0
    for char in txt:
        if ('\u3040' <= char <= '\u309F' or 
            '\u30A0' <= char <= '\u30FF' or 
            '\u4E00' <= char <= '\u9FFF'):
            jp_count += 1
    if len(txt) > 0 and jp_count / len(txt) > 0.3:
        return "ja"
    return "en"


@app.route('/synthesize', methods=['POST'])
def synthesize():
    try:
        data = request.json
        txt = data.get('text', '')
        spd = float(data.get('speed', 1.0))

        if not txt:
            return jsonify({"error": "need some text"}), 400

        lang = guess_language(txt)
        preview = txt[:50] + "..." if len(txt) > 50 else txt
        print(f"Generating {lang}: {preview}")

        ts = int(time.time() * 1000)
        print(" OpenAI TTS")
        resp = client.audio.speech.create(
            model="tts-1-hd",
            voice=OPENAI_VOICE,
            input=txt,
            speed=spd
        )

        tmp_mp3 = os.path.join(output_dir, f"temp_{ts}.mp3")
        resp.stream_to_file(tmp_mp3)

        import subprocess
        tmp_wav = os.path.join(output_dir, f"temp_{ts}.wav")
        subprocess.run(["ffmpeg", "-i", tmp_mp3, "-ar", "22050", "-ac", "1", tmp_wav, "-y"], capture_output=True)

        if voice_clone_available and tone_converter:
            target_embedding = japanese_embedding if lang == "ja" else english_embedding
            if target_embedding is not None:
                print(f"Applying voice clone for {lang}...")
                sr, audio = read_wav(tmp_wav)
                source_embedding = tone_converter.extract_se(tmp_wav)
                cloned = tone_converter.convert(
                    audio_src_path=tmp_wav,
                    src_se=source_embedding,
                    tgt_se=target_embedding
                )
                final_path = os.path.join(output_dir, f"voice_{ts}.wav")
                write_wav(final_path, 22050, cloned.squeeze())
                os.remove(tmp_mp3)
                os.remove(tmp_wav)
                print(f"Done! Saved to {final_path}")
                return send_file(final_path, mimetype='audio/wav', as_attachment=True, download_name='voice.wav')

        print("Returning OpenAI audio (no cloning)")
        if os.path.exists(tmp_wav):
            os.remove(tmp_wav)
        return send_file(tmp_mp3, mimetype='audio/mpeg', as_attachment=True, download_name='voice.mp3')

    except Exception as e:
        print(f"Error in synthesis: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "openai": "enabled",
        "voice_cloning": voice_clone_available,
        "english_voice": english_embedding is not None,
        "japanese_voice": japanese_embedding is not None
    })


@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "Voice synthesis server",
        "openai_tts": "enabled",
        "voice_clone": "enabled" if voice_clone_available else "disabled"
    })


if __name__ == '__main__':
    print("=" * 60)
    print("Starting voice server")
    print("=" * 60)
    print("OpenAI TTS: yes")

    if voice_clone_available:
        print("Voice cloning: yes")
        if english_embedding:
            print("English reference Ok")
        if japanese_embedding:
            print("Japanese reference OK")
    else:
        print("Voice cloning: no")

    print("\nListening on http://0.0.0.0:5005")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5005, debug=False, threaded=True)
