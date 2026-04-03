const { exec } = require("child_process");
const fs = require("fs");
const path = require("path");

// Native fetch is built into Node.js v24, so no need for require("node-fetch")
const inputAudio = path.join(__dirname, "input", "input.wav");
const outputAudio = path.join(__dirname, "output", "output.wav");

async function main() {
  console.log("🎤 Converting speech to text...");

  // 1. Use Whisper STT (Using venv Python to ensure dependencies are found)
  exec(`.\\venv\\Scripts\\python.exe python_scripts/stt_whisper.py "${inputAudio}"`, async (err, stdout) => {
    if (err) {
      console.error("STT Error:", err);
      return;
    }
    
    const userText = stdout.trim();
    if (!userText) {
      console.error("Error: No speech detected in audio file.");
      return;
    }
    
    console.log("📝 User said:", userText);

    // 2. Send to Ollama LLM
    console.log("🤖 Sending to LLM...");
    try {
      const res = await fetch("http://localhost:11434/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "llama3",
          prompt: userText,
          stream: false // Ensures we get a single complete response for the TTS
        }),
      });

      const data = await res.json();
      
      // Ollama returns the result in 'response' field
      const reply = data.response.trim();
      console.log("💬 LLM reply:", reply);

      // 3. Generate TTS (Using venv Python for Piper/Coqui)
      console.log("🔊 Generating TTS...");
      exec(`.\\venv\\Scripts\\python.exe python_scripts/tts_piper.py "${reply}"`, (err2) => {
        if (err2) {
          console.error("TTS Error:", err2);
          return;
        }
        console.log(`✅ Reply saved to ${outputAudio}`);
      });

    } catch (fetchError) {
      console.error("LLM Error: Could not connect to Ollama. Make sure the Ollama app is running!");
    }
  });
}

main();