# VoiceGun User Guide

## Purpose

VoiceGun is a portable Windows application for translating, transcribing and
speaking language-learning materials. It keeps the source text, translation and
pronunciation representation aligned line by line.

Supported target modules: English, French, Spanish, Russian, Japanese and
Chinese. VoiceGun uses IPA for European languages and Russian, Romaji for
Japanese, and Pinyin for Chinese.

## First start

1. Extract the complete VoiceGun ZIP archive into a folder where you have write
   permission.
2. Keep `VoiceGun.exe`, `_internal` and `language_data` together.
3. Run `VoiceGun.exe`.
4. Open **Settings** and select the interface language, source language, editor
   font size and TTS parameters.

Python does not need to be installed. Internet access is required for online
translation, Microsoft Edge TTS and refreshing the voice list.

## Main workspace

- **Source text** — text to translate. Open TXT, DOCX or SRT with **Open** or
  `Ctrl+O`, or type/paste text directly.
- **Translation** — translated text for the selected target language.
- **Transcription** — IPA, Romaji or Pinyin aligned with the translation.

Use **Clear** in a column header to clear that column. Use the `−` button in the
Translation or Transcription header to hide the column. Its restore button
remains available above the workspace.

## Translation

1. Select the target language in **Language**.
2. Enter or open the source text.
3. Select **Translate**.
4. Wait for the progress indicator to finish.

VoiceGun preserves paragraphs and line alignment. Translation is provided by
`deep-translator`; temporary network failures are retried automatically.

## Speech and synchronized playback

Select a Microsoft TTS voice and use:

- **Speak** — speak the material line by line with synchronized highlighting and
  scrolling in all three columns; after completion, the generated lines are
  combined for **Save MP3**;
- **Replay** — speak source lines sequentially, translating missing lines when
  required;
- **Stop** — stop the current playback or foreground operation;
- `Ctrl+Space` — speak the line at the mouse pointer or source caret.

The corresponding line is highlighted and scrolled into view in all visible
columns.

Outside an A–B selection, **Save MP3** always saves the complete translated
text. If line-by-line playback was stopped before the end, VoiceGun synthesizes
the complete document before writing the MP3 instead of saving only the
interrupted line.

When both A and B markers are set, **Save MP3** first offers a choice between
the marked A–B interval and the complete text. The interval is selected by
default and its actual source line numbers are shown in the dialog.

## A–B learning range

1. Place the text caret on the first source line and select **A**.
2. Place the caret on the last line and select **B**.
3. Select **A–B** to speak the inclusive range.
4. After completion, press `Space` to replay the range.
5. Select **Reset** to stop A–B playback, clear both markers and delete its
   temporary audio cache.

Repeated A–B playback uses a line audio cache and normally does not contact TTS
again unless the text, language, voice or TTS settings change.

## Saving text

Select **Save text…**, then choose an export mode:

- full document: source, translation and transcription;
- source text only: plain contents of the first window without headers,
  columns or separators;
- translation only;
- bilingual document;
- learning kit: full TXT plus MP3.

**Line-by-line columns in blocks of 10 lines** is enabled by default. It creates
an aligned table and avoids a block break in the middle of a sentence. Disable
it to save sequential sections instead.

For bilingual Chinese and Japanese materials, the readable Pinyin or Romaji is
used instead of characters in the learning translation column.

## Batch processing

Select **Batch…** to translate several TXT, DOCX or SRT files. VoiceGun reports
overall progress, avoids overwriting existing results and displays a summary of
failed files.

## Settings

Settings include:

- interface language: English or Russian;
- source text language or automatic detection;
- editor font size;
- optional French article processing;
- TTS rate, pitch and volume.

The interface language changes immediately after the Settings dialog is
confirmed.

## Portable files

VoiceGun stores its working files beside `VoiceGun.exe`:

- `settings.json` — application preferences;
- `voicegun.log` — diagnostic log;
- `language_selection.json` — selected target module;
- `language_data\<Language>` — texts, MP3, state and voice cache.

Move or back up the whole VoiceGun folder to preserve all materials. Do not
place the application in a read-only directory such as `Program Files` unless
write permission has been granted.

## Troubleshooting

- If TTS reports a timeout, check the internet connection and try **Refresh
  voices**. Built-in voice names remain available when the network list cannot
  be loaded.
- If translation returns a temporary server error, retry later.
- If the application cannot save settings or language data, move the complete
  VoiceGun folder to a user-writable location.
- Technical details are written to `voicegun.log`.

## Keyboard shortcuts

- `Ctrl+O` — open a document;
- `Ctrl+Space` — speak the selected/current line;
- `Space` — replay a completed A–B range;
- `F1` — open this guide.

## Author

AlexGeorgievich

Email: [alex34.st@gmail.com](mailto:alex34.st@gmail.com)
