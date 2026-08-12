# VoiceGun User Guide

## Purpose

VoiceGun is a portable Windows application for translating, transcribing and
speaking language-learning materials. It keeps the source text, translation and
pronunciation representation aligned line by line.

Supported target modules: English, French, Spanish, German, Italian, Turkish,
Russian, Japanese and Chinese. VoiceGun uses IPA for European languages,
Turkish and Russian, Romaji for Japanese, and Pinyin for Chinese.

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

Use **Open package** for offline work. Select a language and then a package from
its `language_data\<Language>` directory. VoiceGun validates the TXT,
document.json, MP3, timestamp JSON and SRT files, then restores all three text
panels and synchronized audio. Playback, cards and A–B work without internet.

**Package history** lists up to 10 recently saved or opened packages. Double-click
an entry to open it. Removing or clearing history never deletes package files.

Use **Clear** in a column header to clear that column. Use the `−` button in the
Source, Translation or Transcription header to hide the column. Its restore
button remains available above the workspace. VoiceGun always keeps at least
one text window visible, so the last open window cannot be collapsed.

**Switch windows** reverses the learning direction. For European languages and
Russian it places Translation before Source. For Chinese and Japanese it places
the readable Pinyin or Romaji first, followed by Source and the character form.
Press it again to restore the original order. The arrangement is remembered for
each target language.

## Learning cards

Select **Cards** to open the current synchronized sentence in a large modal learning
view. In the normal order Source appears first; after switching windows the
translated learning side appears first. Only columns that are currently open in
the main workspace are included; when one panel is active, the card contains
only that panel's synchronized sentence. Colors match the Source, Translation and
Transcription panels in the main window. The header shows the active range, and
the progress bar shows the current position.

- `Right Arrow` or `>` — show and speak the next sentence;
- `Left Arrow` or `<` — show and speak the previous sentence;
- `Space` — repeat the current card, or play one complete A–B cycle when both
  range markers are active;
- `Down Arrow` — hide supporting texts; `Up Arrow` — restore them;
- `Esc` or **Close** — stop card playback and return to the workspace.

If A and B are set, Cards is restricted to that inclusive range and navigation
cycles from the last card to the first and back. `Space` plays all A–B cards
once; after that cycle finishes, pressing `Space` starts one new cycle. Without
A–B it repeats only the current sentence. During an A–B cycle, the modal card text
and progress change in sync with every spoken sentence. In complete package mode
playback seeks by timestamps; in fast mode each card is synthesized once and
kept in a separate temporary cache.

## Translation

1. Select the target language in **Language**.
2. Enter or open the source text.
3. Select **Translate**.
4. Wait for the progress indicator to finish.

VoiceGun preserves paragraphs and line alignment. Translation is provided by
`deep-translator`; temporary network failures are retried automatically. What
happens next depends on **Audio preparation mode** in Settings. The default
**Fast line-by-line** mode finishes immediately after translation and prepares
audio as lines are played. **Complete audio package** additionally prepares one
complete MP3, an internal JSON timing manifest and an SRT subtitle file. If TTS
is temporarily unavailable, the completed translation remains available and
the audio error is reported separately.

After a successful translation, Source enters protected study mode: accidental
editing is disabled, **Translate** becomes inactive, and **Edit** in the Source
header becomes available. Click any sentence to select it; `Down`/`Right` move
to and speak the next sentence, `Up`/`Left` move to and speak the previous one,
and `Space` repeats the current sentence. **Speak** continues sequentially from
the selected sentence to the end or until **Stop**. **Edit** stops playback,
unlocks Source, clears A–B and stale audio, and enables **Translate** again.

## Speech and synchronized playback

Select a Microsoft TTS voice and use:

- **Speak** — synthesize and play sentences immediately in fast mode, or play the
  complete prepared MP3 in package mode; both variants highlight and scroll the
  corresponding sentence in all three columns;
- **Replay** — repeat the prepared package or the cached line sequence;
- **Stop** — stop the current playback or foreground operation;
- `Ctrl+Space` — speak the sentence at the mouse pointer or source caret.

The corresponding sentence is highlighted and scrolled into view in all visible
columns.

Outside an A–B selection, **Save MP3** saves the complete translated text as a
five-file offline package with the same base name: `.txt`, `.document.json`,
`.mp3` audio, `.srt` subtitles and an internal `.json` timing manifest. Stopping
playback does not truncate
the saved audio because playback uses the already prepared complete MP3.

When both A and B markers are set, **Save MP3** first offers a choice between
the marked A–B interval and the complete text. The interval is selected by
default and its actual source line or sentence numbers are shown in the dialog.

## A–B learning range

1. Place the text caret inside the first sentence and select **A**.
2. Place the caret inside the last sentence and select **B**. Both sentences
   may be located inside the same physical line.
3. Select **A–B** to speak the inclusive range.
4. After completion, press `Space` to replay the same A–B range.
5. Select **Reset** to stop A–B playback, clear both markers and delete its
   temporary audio cache.

When a prepared audio package exists, A–B playback seeks directly to the marked
timestamps in the complete MP3 and does not contact TTS again. The line cache is
used only as a fallback for material without a prepared package.

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
- primary and additional text sizes for learning cards;
- optional French article processing;
- audio preparation: fast line-by-line (default) or complete package;
- TTS rate, pitch and volume.

The interface language changes immediately after the Settings dialog is
confirmed. Audio preparation mode is remembered independently for each target
language module.

## Portable files

VoiceGun stores its working files beside `VoiceGun.exe`:

- `settings.json` — application preferences;
- `voicegun.log` — diagnostic log;
- `language_selection.json` — selected target module;
- `language_data\<Language>` — texts, MP3/SRT/JSON audio packages, state and
  voice cache.

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
- `Ctrl+Space` — speak the selected/current sentence;
- `Space` — replay a completed A–B range in the main window; inside Cards it
  repeats the current sentence or starts one A–B card cycle;
- `F1` — open this guide.

## Author

AlexGeorgievich

Email: [alex34.st@gmail.com](mailto:alex34.st@gmail.com)
