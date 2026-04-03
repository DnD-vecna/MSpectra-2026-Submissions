const dgram = require('dgram');
const fs = require('fs');

const server = dgram.createSocket('udp4');

let audioChunks = [];

// When RTP packet arrives
server.on('message', (msg, rinfo) => {
  console.log(`🎧 Packet received: ${msg.length} bytes`);

  // Remove RTP header (first 12 bytes)
  const payload = msg.slice(12);

  audioChunks.push(payload);
});

// Error handling
server.on('error', (err) => {
  console.error('❌ UDP Error:', err);
  server.close();
});

// When server starts
server.on('listening', () => {
  const address = server.address();
  console.log(`🎧 Listening on ${address.address}:${address.port}`);
});

// 🔥 Save WAV every 5 seconds (optional)
setInterval(() => {
  if (audioChunks.length === 0) return;

  const audioBuffer = Buffer.concat(audioChunks);

  // WAV header (8kHz mono PCM)
  const wavHeader = Buffer.alloc(44);

  wavHeader.write('RIFF', 0);
  wavHeader.writeUInt32LE(36 + audioBuffer.length, 4);
  wavHeader.write('WAVE', 8);
  wavHeader.write('fmt ', 12);
  wavHeader.writeUInt32LE(16, 16);
  wavHeader.writeUInt16LE(1, 20); // PCM
  wavHeader.writeUInt16LE(1, 22); // mono
  wavHeader.writeUInt32LE(8000, 24); // sample rate
  wavHeader.writeUInt32LE(16000, 28);
  wavHeader.writeUInt16LE(2, 32);
  wavHeader.writeUInt16LE(16, 34);
  wavHeader.write('data', 36);
  wavHeader.writeUInt32LE(audioBuffer.length, 40);

  const wavFile = Buffer.concat([wavHeader, audioBuffer]);

  fs.writeFileSync('output.wav', wavFile);

  console.log("💾 Saved output.wav");

  audioChunks = [];

}, 5000);

// 🔥 Bind UDP port
server.bind(9000);