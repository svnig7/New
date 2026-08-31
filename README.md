# streambot

Standalone Telegram bot that turns any file/video/audio into a streamable
watch page + direct link, using Pyrogram's MTProto client instead of the
Bot API — so there's no ~2GB file-size wall.

Modeled on WZML-X's `/stream` feature: a pool of bot tokens shares
streaming load, plus playlists, self-expiring links, custom thumbnails,
and a custom player with multi-audio/multi-subtitle switching.

## `/stream` command

Reply to any file with:

```
/stream
/stream -pl "Movie Night"
/stream -t https://example.com/poster.jpg
/stream -ttl 2h
/stream -pl "Movie Night" -t https://example.com/poster.jpg -ttl 1d
```

- **`-pl <name>`** — adds the file to a named playlist instead of making a
  standalone link. Quote multi-word names. Calling it again with the same
  name (per chat) appends to the same playlist.
- **`-t <url>`** — sets a custom poster/thumbnail shown on the watch page
  (and as the link-preview image).
- **`-ttl <30m|2h|1d|...>`** — makes the link self-expiring. Units: `s`/`m`/`h`/`d`.
  Omit for a link that never expires.

### Multi-audio / multi-subtitle

Send the video **plus** its alternate-language audio files and
`.srt`/`.vtt`/`.ass` subtitle files as **one Telegram album**, then reply
`/stream` to any item in it. The bot pulls the siblings in automatically:
audio files become switchable audio tracks, subtitle files become
switchable subtitle tracks in the watch page's player (the "Fused
Player" — a custom control bar with an audio-track menu and a
subtitle-track menu, on top of the native `<video>` element).

Audio-track switching works by muting the video's own track and playing
the chosen alternate `<audio>` element in sync — a real technique, not a
transcode; it doesn't require re-encoding the file. Subtitle files are
converted to WebVTT on the fly (`.srt` cleanly; `.ass` best-effort —
positioning/karaoke/styling aren't preserved, only text and timing).

### Playing MKV/AVI/FLV in the browser

Chrome (and most browsers) can't parse Matroska/AVI/FLV containers
natively in a `<video>` tag, even when the codecs inside are otherwise
fine. For these, the watch page's player pulls from `/remux/<token>`
instead of `/stream/<token>`: the byte stream is piped through
`ffmpeg -c copy` (repackaging only, no re-encoding — cheap) into
fragmented MP4 on the fly. Download / VLC / MX Player still get the
original, untouched file via `/dl` and `/stream`, which already support
these containers natively.

Limitation: because ffmpeg consumes the source sequentially, remuxed
playback doesn't support seeking — dragging the progress bar restarts
from the beginning. Real seeking would need segment-based HLS or a
WASM demuxer feeding Media Source Extensions (what WZML-X does with
`@libmedia/avplayer`); this is the simpler, cheaper version of that.

## How it works

1. `/stream` copies the target message into a private `LOG_CHANNEL` (so
   the bot doesn't need standing access to the original chat later).
2. The channel message id — plus kind (file/playlist/subtitle) and an
   optional expiry — is HMAC-signed into a short token. That token *is*
   the link. No database for links themselves.
3. Extra per-file metadata (thumbnail, audio/subtitle tracks) and named
   playlists are kept in small JSON files under `data/` — no external DB
   needed, but they don't survive a redeploy on platforms without a
   persistent volume (see Limitations).
4. `/watch/<token>` renders the player page; `/stream/<token>` and
   `/dl/<token>` serve bytes, range-request aware, pulled live from
   Telegram via `Client.stream_media`.
5. Each request goes to whichever bot in the pool currently has the
   fewest active viewers (`STREAM_PER_CLIENT`), capped globally by
   `STREAM_GATE`.

## Setup

1. Get `API_ID` / `API_HASH` from <https://my.telegram.org>.
2. Create a primary bot via @BotFather. Optionally create a few more —
   these go into `STREAM_TOKENS` and only exist to spread streaming load.
3. Create a private channel, add the primary bot **and every worker bot**
   as admin. That's `LOG_CHANNEL` (its id starts with `-100`).
4. Copy `.env.sample` to `.env` and fill it in.
5. `pip install -r requirements.txt`
6. `python -m app`

## Deploying (Koyeb / Railway / Render)

- Push this repo, point the platform at the included `Dockerfile`.
- Set all the vars from `.env.sample` in the platform's env settings.
- `BASE_URL` must be the public URL the platform assigns you — links are
  built from it directly.
- The web server binds `0.0.0.0:$PORT`, which all three platforms expect.
- If the platform gives you a persistent volume, mount it at `/app/data`
  so playlists and track metadata survive redeploys.
- On Render's **free tier**, the service spins down after inactivity. The
  first request after a cold start has to both boot the process and do a
  fresh MTProto handshake with Telegram's media DC (~1-2s), which can be
  slow enough that a browser's download hand-off gives up and resets the
  connection before headers arrive. If a download looks "broken" only on
  the *first* request after idling, that's why — try again immediately
  after (the service is warm by then), or move off the free tier if this
  needs to be reliable.

## Tuning notes

- `STREAM_CHUNK`: bytes per MTProto request. Pyrogram's `stream_media`
  fixes this at 1 MiB internally, so leaving the default is recommended.
- `STREAM_PIPELINE`: read-ahead depth per viewer. Raises memory use per
  stream a little, smooths playback on slower client connections.
- `STREAM_PER_CLIENT` / `STREAM_GATE`: capacity planning. Each additional
  worker token roughly adds `STREAM_PER_CLIENT` more comfortable concurrent
  viewers before the pool starts queuing behind `STREAM_GATE`.

## Notes / limitations

- `data/playlists.json` and `data/media_meta.json` are plain JSON files,
  not a real database — fine for personal/small-group use, but there's no
  concurrent-write safety beyond a single asyncio lock per process, and
  no migration path if you outgrow it. Swap in Mongo/D1 if that happens.
- No link revocation UI — `-ttl` is the only expiry mechanism.
- `AUTH_USERS` gates who can *create* links; anyone with a link can view it.
- ASS subtitle conversion is text-only (no positioning/styling/karaoke).
