import sys
import wave
import json
from vosk import Model, KaldiRecognizer

wf = wave.open(sys.argv[1], "rb")
model = Model("vosk-model-small-en-us")
rec = KaldiRecognizer(model, wf.getframerate())
transcript = ""

while True:
    data = wf.readframes(4000)
    if len(data) == 0:
        break
    if rec.AcceptWaveform(data):
        res = json.loads(rec.Result())
        transcript += res.get("text", "") + " "

res = json.loads(rec.FinalResult())
transcript += res.get("text", "")
print(transcript)