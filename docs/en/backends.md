# Backends & licensing

> Specification v0.1 draft. Chinese edition: [`docs/zh/backends.md`](../zh/backends.md)

## Backend interfaces

Every capability is a replaceable backend: a Python class that implements the matching interface and declares its **capabilities** and **license information**.

```python
class TTSBackend(Protocol):
    info: BackendInfo                         # name, license, attribution, capabilities

    def design(self, prompt: str, text: str, n: int) -> list[Path]: ...       # optional: voice candidates from a description
    def synthesize(self, items: list[Line], ref: VoiceRef, seed: int) -> list[Path]: ...

@dataclass
class BackendInfo:
    id: str                      # "drama3"
    kind: str                    # import | image | voice_design | tts | asr | align | music | sfx | encode
    languages: list[str]         # ["zh-CN", "en"]
    needs_gpu: bool
    vram_gb: float | None
    license: str                 # SPDX identifier or license name
    license_url: str
    commercial_use: bool | None  # None = the user must check
    attribution: str | None      # text that must appear in the credits
    clone_requires_consent: bool # whether cloning a real person's voice needs their consent
```

| Kind | Interface essentials |
|---|---|
| `import` | Raw files → event stream; merges and deduplicates multiple exports |
| `image` | Text-to-image, generation with reference images, editing; whether it can output transparent backgrounds |
| `voice_design` | Voice candidates from a text description |
| `tts` | Whole-sentence synthesis from a fixed reference; tone directions; batching; seeds |
| `asr` | Transcription (voice QA, vocal detection in BGM) |
| `align` | Forced alignment with per-character/word timing (bleeping) |
| `music` | Optional score → audio; whether it can produce a score before rendering |
| `sfx` | Procedural synthesis or a sound pack |
| `encode` | Preset-based encoding; detects available hardware encoders |

Third parties can register new backends as plugins without touching the core.

## First-wave backends

The license column reflects what was known at M0. **Each license will be checked against its official terms when the backend is integrated in M1**, and that check takes precedence.

| Kind | Backend | Notes | License (to be verified) |
|---|---|---|---|
| import | Foundry VTT, plain text | FVTT used in production | This project's code |
| image | Codex (`codex exec`) | Used in production; needs the user's own Codex, with model and effort set in `[harness.codex]` | Governed by OpenAI's terms |
| image | ComfyUI | Runs the user's own workflows (planned) | Depends on the models used |
| image | Manual import | Bring your own images | — |
| image | Placeholder | Simple silhouettes and gradients, to run the pipeline end to end | This project's code |
| voice_design | Qwen3-TTS | VoiceDesign + Base cloning | To be verified |
| tts | Fish Audio Drama 3 (local audio.cpp build) | Used in production; supports bracketed tone directions | Fish Audio community license: requires "Built with Fish Audio" attribution; only consented voices may be cloned (designed synthetic voices are fine) |
| asr | SenseVoice | Used in production for voice QA | To be verified |
| align | FunASR fa-zh | Used in production for Chinese bleeping | To be verified |
| asr / align (English) | Whisper + WhisperX | For English projects | Whisper is MIT; WhisperX to be verified |
| music | YuE2 (through ComfyUI) | Used in production; can produce a score before rendering | Weights are CC BY-NC 4.0: **non-commercial only**, attribution required |
| music | Manual import | Your own music | — |
| music | Placeholder | A soft chord pad, to run the pipeline end to end | This project's code |
| sfx | Built-in synthesized library | Synthesized by this project | Released with this project (Apache-2.0) |
| encode | ffmpeg | NVENC / AMF / QSV / CPU | Uses the system ffmpeg; if an installer bundles ffmpeg, it uses an LGPL build |

## Licensing principles

1. **No model weights are bundled or distributed.** The setup wizard tells users where to download each model and where to put it, or lets them point to an existing install.
2. **Every backend carries license information.** Studio shows it when choosing backends, and warns before export when the project uses a non-commercial-only backend.
3. **Credits are generated automatically.** The "Music", "Voice", "Art" sections of the credits list the backends actually used; attribution required by a backend (e.g. "Built with Fish Audio") always appears.
4. **This project's own work is Apache-2.0.** That covers the code, the player and the built-in SFX library. Fonts are OFL-licensed (Source Han Serif / Noto).

## Privacy and consent

Session logs are real people's conversations, and replays are often published.

- **On import**: Studio asks to confirm that every player agrees to publication, and flags real names or contact details found in the log.
- **Anonymization**: `replay.toml` can map player names to aliases; scripts, subtitles and credits then use the aliases.
- **Voices**: designed synthetic voices are the default. Cloning a real person's voice (e.g. a player's own) requires that person's consent; for backends declaring `clone_requires_consent`, Studio requires a confirmation checkbox.
- **Sample project**: the sample session in the public repository is entirely made up and contains no real session logs.

## Hardware

- An NVIDIA GPU with 12 GB+ VRAM is recommended (production used an RTX 5070 Ti 16 GB). Each backend states its VRAM needs in `BackendInfo`, and `replay doctor` gives advice from that.
- Without a GPU, every capability must still have at least one usable option: a cloud API, a CPU build, or manual import.
- When VRAM can't hold two large models at once (e.g. YuE2 and Drama 3), the pipeline queues them instead of running them concurrently.
