from TTS.api import TTS
import sys
import os

text = sys.argv[1]
output_file = os.path.join("output", "output.wav")

tts = TTS(model_name="tts_models/en/ljspeech/tacotron2-DDC")
tts.tts_to_file(text=text, file_path=output_file)
print(f"TTS saved to {output_file}")