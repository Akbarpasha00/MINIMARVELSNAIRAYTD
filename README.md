# Mini Marvels – Naira | Cinematic Shorts automation

Four original learning Shorts per day, generated as **moving cinematic 3D animation using Google Cloud Veo 3.1**, with native narration and ambience. This does not automate the Google Flow website. It uses Google's supported model API.

Each Short is four eight-second scenes, approximately 32 seconds, vertical 720 × 1280. A cream rabbit in a blue waistcoat is the default fictional mascot. The next scene starts from the preceding scene's final frame to guide continuity. AI output can still vary; continuity, Telugu pronunciation and factual accuracy require viewing the first private samples.

## Daily schedule (India)

| Slot | IST start | Theme |
| --- | --- | --- |
| 1 | 08:30 | Learning: numbers, colours, shapes |
| 2 | 12:30 | Original animal story |
| 3 | 16:30 | Good habits |
| 4 | 19:30 | Nature and simple science |

Times are workflow start times, not guaranteed publication times. Generation may take many minutes. GitHub schedules can be delayed or skipped, and public repository schedules can be disabled after inactivity. There is no missed-slot backfill. A manual run can recover a missed slot using the CLI with the original date.

**Installed code is not an activated service.** Automatic runs remain disabled until configuration is complete and `AUTOMATION_ENABLED=true` is set. Uploads default to private. No live generation or YouTube upload has been verified without the owner's credentials.

## 1. Google Cloud access

1. Create/select a Google Cloud project with billing enabled. Enable the Vertex AI API (`aiplatform.googleapis.com`).
2. Obtain access and adequate quota for `veo-3.1-fast-generate-001` in `us-central1`, plus a Gemini text model (`gemini-2.5-flash` by default). Four Shorts require **16 video generations / 128 generated video seconds daily**, before any retries. Confirm current model availability in your project.
3. Create a dedicated service account with `roles/aiplatform.user`. Create its JSON key, store it as the GitHub Actions secret `GCP_SA_KEY`, then remove the local key copy. Do not commit credentials. Workload Identity Federation is a keyless alternative if you adapt the auth step.
4. Set the repository variable `GOOGLE_CLOUD_PROJECT` to your project ID.

Veo is paid. Flow subscription credits are not configured or consumed by this pipeline. Check Google's current Cloud pricing and your quota before enabling daily generation. Set Cloud billing alerts; alerts alone do not impose a spending cap. Four scenes × four Shorts can be a substantial monthly expense. Manual reruns can add charges.

The Gemini API Veo preview models were shut down on October 22, 2026, so this repository intentionally uses the Google Cloud GA model instead. Model names are configurable and may need updating as providers retire them.

## 2. Authorize the correct YouTube channel

1. In Google Cloud, enable **YouTube Data API v3**. Configure the OAuth consent screen and create a **Desktop app** OAuth client. If the app is in Testing, add your Google account as a test user. Testing-mode authorizations may expire; configure the appropriate production consent setup for unattended use.
2. Download the OAuth JSON as `client_secret.json` to your own computer. Install Python 3.11, then run:

```bash
python -m pip install -r requirements.txt
python tools/authorize_youtube.py client_secret.json
```

3. Sign in and select the **Mini Marvels – Naira channel**, including the correct Brand Account if applicable. The helper writes `token.json` locally without printing credentials.
4. Add each value in `token.json` as its own repository Actions secret: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`. Delete `token.json` and `client_secret.json` after securely storing the secrets.
5. Set the Actions variable `YOUTUBE_CHANNEL_ID` to the channel's `UC...` ID from YouTube Studio → Settings → Channel → Advanced settings. The uploader verifies that authorized channel ID before generating paid video for uploads.

The requested scopes are upload plus read-only access, used to verify the channel and inspect its uploaded-video playlist for duplicate markers.

## 3. GitHub settings

Open repository **Settings → Secrets and variables → Actions**.

### Secrets

| Name | Value |
| --- | --- |
| `GCP_SA_KEY` | Entire dedicated Google Cloud service account JSON |
| `YOUTUBE_CLIENT_ID` | OAuth desktop client ID |
| `YOUTUBE_CLIENT_SECRET` | OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | Authorized channel refresh token |

### Variables

| Name | Value / default |
| --- | --- |
| `GOOGLE_CLOUD_PROJECT` | Required Cloud project ID |
| `YOUTUBE_CHANNEL_ID` | Required exact channel ID |
| `AUTOMATION_ENABLED` | Leave unset until first successful private test; then `true` |
| `YOUTUBE_PRIVACY` | `private` by default; `public` or `unlisted` if desired |
| `CONTENT_LANGUAGE` | `Telugu and simple English` |
| `VEO_MODEL` | `veo-3.1-fast-generate-001` |
| `SCRIPT_MODEL` | `gemini-2.5-flash` |

Never paste credentials into chat, source code, README files or issue comments.

## 4. First run and activation

1. Open **Actions → Mini Marvels - 4 cinematic Shorts daily → Run workflow**.
2. Choose slot `1`, leave **upload unchecked** and run. This incurs Cloud generation charges. Download the resulting artifact and watch the video; inspect audio, scene continuity, captions and script accuracy.
3. Run again with **upload checked**, keeping `YOUTUBE_PRIVACY=private`. A separate workflow run uses a fresh runner and currently regenerates the video; see checkpoint recovery below to avoid paying again for an existing render.
4. Verify the private video in YouTube Studio, including audience and disclosure settings.
5. Set `AUTOMATION_ENABLED=true` for the four daily slots. Set `YOUTUBE_PRIVACY=public` only when you want future uploads automatically published. Existing private uploads are not automatically republished.

All uploaded videos are declared **made for kids**, with AI disclosure in their descriptions and synthetic-media metadata. English scene captions are burned into the video; they summarize each scene and are not word-aligned Telugu subtitles. A thumbnail image is included in the artifact; custom YouTube thumbnail upload is not implemented. No music is added by the editor; Veo supplies the requested narration and natural ambience.

## Reliability and recovery

- A single concurrency group serializes production runs. Scheduled and manual runs share it.
- Before an upload-mode run spends on generation, it verifies the channel and checks the uploads playlist for a date/slot marker, including private videos and all playlist pages. Already-found slots are skipped. This is best-effort duplicate prevention, not an exactly-once guarantee: YouTube listing can lag after an uncertain upload. Check Studio before retrying an interrupted upload.
- Upload requests do not automatically restart on failure. Upload API responses, generated scripts, video clips and operation IDs are saved under `output/`.
- Workflow artifacts are retained for seven days, including on failures when possible. They contain channel content and operation IDs, but not OAuth or service-account credentials. This repository is public, so consider artifact visibility before including unpublished content.
- A fresh GitHub run does **not** automatically restore prior artifacts. To resume without regenerating paid clips, download the failed run artifact and restore its `output/mmn-DATE-SLOT/` folder locally, then run the same date and slot. Completed raw clips and saved Veo operation names will be reused while the provider retains the results. Do not start repeated fresh runs blindly.
- Video output must have an audio stream and the assembled video must be about 32 seconds. Filtering, missing credentials, wrong channel, missing audio and invalid duration stop publication. Presence of audio does not validate the spoken words.
- There is no generated-quality, monetization, view-count or uptime guarantee. Review private output before enabling public uploads. Provider safety filters and channel/API restrictions may block runs.

## Local use

Install FFmpeg and DejaVu fonts. Configure Google Cloud Application Default Credentials (for example `gcloud auth application-default login`) and set `GOOGLE_CLOUD_PROJECT`. For upload mode, also set the four `YOUTUBE_*` configuration values described above.

```bash
python -m pip install -r requirements.txt
python pipeline.py --slot 1                     # paid generation, render only
python pipeline.py --slot 1 --date 2026-10-26 --upload
python -m unittest discover -s tests -v         # no paid API calls or uploads
```

To change the mascot, edit `MASCOT` in `pipeline.py`; to change topic rotation, edit `TOPICS`. The current setup uses fictional animals rather than a real child's face or voice.

## Primary references

- [Google Cloud Veo 3.1 models](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/veo/3-1-generate)
- [Google video API migration notice](https://ai.google.dev/gemini-api/docs/video)
- [YouTube video upload API](https://developers.google.com/youtube/v3/docs/videos/insert)
- [GitHub scheduled workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
