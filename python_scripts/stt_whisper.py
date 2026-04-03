import whisper
import sys
import os

audio_file = sys.argv[1]
model = whisper.load_model("base")  # base, small, medium, large
result = model.transcribe(audio_file)
print(result["text"])