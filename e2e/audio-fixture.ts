/** WAV PCM de silêncio, sem material externo ou voz pessoal. */
export function silentWav(bytes = 32_044, rate = 16_000, channels = 1): Buffer {
  const wav = Buffer.alloc(bytes)
  wav.write('RIFF'); wav.writeUInt32LE(bytes - 8, 4); wav.write('WAVEfmt ', 8)
  wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(channels, 22)
  wav.writeUInt32LE(rate, 24); wav.writeUInt32LE(rate * channels * 2, 28)
  wav.writeUInt16LE(channels * 2, 32); wav.writeUInt16LE(16, 34)
  wav.write('data', 36); wav.writeUInt32LE(bytes - 44, 40)
  return wav
}
