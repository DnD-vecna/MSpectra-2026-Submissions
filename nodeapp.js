const AriClient = require('ari-client');

AriClient.connect('http://localhost:8088', 'admin', 'admin')
  .then((client) => {

    console.log("✅ Connected to Asterisk ARI");

    client.on('StasisStart', async (event, channel) => {

      // 🔥 Handle only main channel (;1)
      if (!channel.name.endsWith(';1')) {
        console.log("⏭ Skipping:", channel.name);
        return;
      }

      console.log("🔥 Incoming call:", channel.name);

      let bridge;
      let external;

      try {
        // Answer call
        await channel.answer();

        // Create bridge
        bridge = await client.bridges.create({ type: 'mixing' });

        await bridge.addChannel({ channel: channel.id });

        // Create external media (RTP stream)
        external = await client.channels.externalMedia({
          app: 'ai-agent',
          external_host: '127.0.0.1:9000',
          format: 'slin' // IMPORTANT
        });

        await bridge.addChannel({ channel: external.id });

        console.log("🎧 Streaming started");

      } catch (err) {
        console.error("❌ Error:", err);
      }

      // 🔥 Cleanup when call ends
      channel.on('StasisEnd', async () => {
        console.log("🧹 Cleaning up:", channel.name);

        try {
          if (external) await external.hangup();
          if (bridge) await bridge.destroy();
        } catch (err) {
          console.error("Cleanup error:", err);
        }
      });
    });

    client.start('ai-agent');
  })
  .catch(console.error);