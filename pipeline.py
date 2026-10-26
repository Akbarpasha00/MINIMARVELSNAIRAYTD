"""Mini Marvels – Naira: cinematic Veo animation and YouTube automation."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import time
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps

SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']
TOPICS = [
 ['counting garden animals', 'colour hunt', 'friendly shapes', 'opposites in nature', 'fruit names', 'days of the week', 'animal sounds'],
 ['a rabbit learns to share', 'a little seed grows', 'a bird helps a friend', 'a lost pencil finds home', 'a patient turtle', 'a thankful elephant', 'a kind butterfly'],
 ['washing hands with an adult', 'tidying toys', 'saying please and thank you', 'taking turns', 'covering a sneeze', 'asking a trusted adult for help', 'saving water'],
 ['why shadows move', 'how rain helps plants', 'why butterflies visit flowers', 'where clouds come from', 'why the moon looks different', 'how a seed sprouts', 'what a rainbow is']]


def run(*args):
    return subprocess.check_output(list(map(str, args)), stderr=subprocess.STDOUT).decode().strip()


def duration(path):
    return float(run('ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                     '-of', 'default=noprint_wrappers=1:nokey=1', path))


def require(names):
    missing = [n for n in names if not os.getenv(n)]
    if missing:
        raise ValueError('Missing configuration: ' + ', '.join(missing))


def topic_for(day, slot):
    index = datetime.strptime(day, '%Y-%m-%d').toordinal()
    return TOPICS[slot - 1][index % len(TOPICS[slot - 1])]


def validate(data):
    if not isinstance(data, dict) or not isinstance(data.get('title'), str) or not 1 <= len(data['title']) <= 90:
        raise ValueError('Invalid title')
    if not isinstance(data.get('description'), str) or len(data['description']) > 3000:
        raise ValueError('Invalid description')
    scenes = data.get('scenes')
    if not isinstance(scenes, list) or len(scenes) != 4:
        raise ValueError('Exactly four scenes required')
    for scene in scenes:
        for key, limit in [('caption', 100), ('narration', 300), ('visual', 800)]:
            if not isinstance(scene.get(key), str) or not 1 <= len(scene[key]) <= limit:
                raise ValueError('Invalid scene ' + key)
    return data


def generate(client, day, slot):
    topic = topic_for(day, slot)
    prompt = f'''Create one original educational Short for Mini Marvels – Naira, ages 4–8.
Topic: {topic}. Date/variation seed: {day}, slot {slot}.
Language: {os.getenv('CONTENT_LANGUAGE', 'Telugu and simple English')}.
Return JSON: title (under 90 characters), description, scenes (exactly four objects,
each with caption, narration, visual). Narration: 8–12 words per scene, spoken comfortably inside eight seconds;
Telugu must use Telugu script, no transliteration. Captions: English only, 3–8 words.
Visual: a detailed cinematic scene with subject action, setting, lighting and camera movement. Use only a friendly fictional rabbit mascot; no human children or named copyrighted characters. Maintain the same rabbit and setting across all four scenes.
No brands, personal data requests, dangerous activities, medical advice, frightening scenes,
misleading facts, engagement bait or requests to subscribe. Science must be accurate and simple.
Story slot uses fictional animals. Other slots teach one concrete idea with an opening hook,
a useful example and a gentle closing question. Do not claim to be a real child.'''
    from google.genai import types
    response = client.models.generate_content(
        model=os.getenv('SCRIPT_MODEL', 'gemini-2.5-flash'), contents=prompt,
        config=types.GenerateContentConfig(response_mime_type='application/json'))
    return validate(json.loads(response.text))


def font(size):
    return ImageFont.truetype(os.getenv('FONT_PATH', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'), size)


def wrap(draw, text, face, width):
    lines, current = [], ''
    for word in text.split():
        candidate = (current + ' ' + word).strip()
        if draw.textbbox((0, 0), candidate, font=face)[2] > width and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    return lines + [current]


MASCOT = ('The same original rabbit in every shot: a small cream-furred rabbit with '
          'amber eyes, a sky-blue waistcoat and one yellow star badge. Realistic detailed '
          'fur, expressive gentle face, physically believable movement; premium cinematic '
          '3D animation in a sunlit miniature garden. No human child likeness.')


def veo_prompt(scene):
    return (MASCOT + ' Vertical 9:16 composition. One continuous eight-second shot. '
            + scene['visual'] + ' Smooth cinematic camera, natural motion and soft light. '
            'Preserve character, costume, environment and continuity from the starting frame if supplied. '
            'Native sound: gentle natural ambience and one warm adult storyteller voice, '
            'off-screen, speaking exactly: ' + json.dumps(scene['narration'], ensure_ascii=False)
            + '. No other speech, no music, no text or subtitles inside the image. '
            'The rabbit does not lip-sync. No logos, frightening action or rapid flashing.')


def generate_clip(client, scene, raw, operation_file, first_frame=None):
    from google.genai import types
    if raw.exists():
        return
    if operation_file.exists():
        operation = client.operations.get(types.GenerateVideosOperation(
            name=json.loads(operation_file.read_text())['name']))
    else:
        kwargs = {'model': os.getenv('VEO_MODEL', 'veo-3.1-fast-generate-001'),
                  'prompt': veo_prompt(scene),
                  'config': types.GenerateVideosConfig(aspect_ratio='9:16', duration_seconds=8,
                                                       resolution='720p', number_of_videos=1,
                                                       person_generation='allow_adult', generate_audio=True)}
        if first_frame:
            kwargs['image'] = types.Image.from_file(location=str(first_frame))
        operation = client.models.generate_videos(**kwargs)
        operation_file.write_text(json.dumps({'name': operation.name}))
    deadline = time.monotonic() + 1500
    while not operation.done:
        if time.monotonic() > deadline:
            raise TimeoutError('Veo is still generating. Saved operation can be resumed locally.')
        time.sleep(15)
        operation = client.operations.get(operation)
    if operation.error:
        raise RuntimeError('Veo generation failed: ' + str(operation.error))
    result = operation.response
    if not result or not result.generated_videos:
        raise RuntimeError('Veo returned no video, possibly due to filtering. No upload attempted.')
    video = result.generated_videos[0].video
    if not video.video_bytes:
        raise RuntimeError('Expected inline video bytes from Vertex AI; no upload attempted')
    raw.write_bytes(video.video_bytes)


def normalize_clip(raw, clip, caption):
    # Burn one scene caption over the generated motion, preserving Veo's native audio.
    overlay = clip.with_suffix('.overlay.png')
    im = Image.new('RGBA', (720, 1280))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((24, 38, 696, 112), 20, fill=(38, 26, 68, 220))
    draw.text((360, 75), 'MINI MARVELS – NAIRA', font=font(27), anchor='mm', fill='white')
    lines = wrap(draw, caption, font(35), 630)
    if len(lines) > 4:
        raise ValueError('Caption too long for safe layout')
    top = 1040 - len(lines) * 24
    draw.rounded_rectangle((25, top-30, 695, top + len(lines)*48), 20, fill=(38, 26, 68, 220))
    for i, line in enumerate(lines):
        draw.text((360, top+i*48), line, font=font(35), anchor='mt', fill='white')
    im.save(overlay)
    # Require an audio stream. A silent/invalid response must fail before publication.
    audio = run('ffprobe', '-v', 'error', '-select_streams', 'a', '-show_entries',
                'stream=index', '-of', 'csv=p=0', raw)
    if not audio:
        raise ValueError('Veo returned no audio; upload stopped')
    run('ffmpeg', '-y', '-i', raw, '-i', overlay,
        '-filter_complex', '[0:v]scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1[v];[v][1:v]overlay=0:0,format=yuv420p[out]',
        '-map', '[out]', '-map', '0:a:0', '-c:v', 'libx264', '-preset', 'fast', '-crf', '20',
        '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-r', '24', '-t', '8',
        '-movflags', '+faststart', clip)


def render(client, data, folder):
    clips, first_frame = [], None
    for index, scene in enumerate(data['scenes']):
        raw = folder / f'raw-{index+1}.mp4'
        clip = folder / f'scene-{index+1}.mp4'
        generate_clip(client, scene, raw, folder / f'operation-{index+1}.json', first_frame)
        normalize_clip(raw, clip, scene['caption'])
        first_frame = folder / f'last-frame-{index+1}.png'
        run('ffmpeg', '-y', '-sseof', '-0.1', '-i', raw, '-frames:v', '1', first_frame)
        clips.append(clip)
    manifest = folder / 'concat.txt'
    manifest.write_text(''.join(f"file '{p.name}'\n" for p in clips))
    video = folder / 'short.mp4'
    run('ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', manifest,
        '-c', 'copy', '-movflags', '+faststart', video)
    seconds = duration(video)
    if not 30 <= seconds <= 34:
        raise ValueError(f'Video is {seconds:.1f}s; expected approximately 32s. Nothing uploaded.')
    run('ffmpeg', '-y', '-i', video, '-frames:v', '1', folder / 'thumbnail.jpg')
    return video


def youtube():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    require(['YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN', 'YOUTUBE_CHANNEL_ID'])
    credentials = Credentials(None, refresh_token=os.environ['YOUTUBE_REFRESH_TOKEN'],
                              token_uri='https://oauth2.googleapis.com/token',
                              client_id=os.environ['YOUTUBE_CLIENT_ID'],
                              client_secret=os.environ['YOUTUBE_CLIENT_SECRET'], scopes=SCOPES)
    credentials.refresh(Request())
    api = build('youtube', 'v3', credentials=credentials, cache_discovery=False)
    channels = api.channels().list(part='id,contentDetails', mine=True).execute()['items']
    channel = next((c for c in channels if c['id'] == os.environ['YOUTUBE_CHANNEL_ID']), None)
    if not channel:
        raise ValueError('Authorized channel differs from YOUTUBE_CHANNEL_ID; upload stopped')
    return api, channel['contentDetails']['relatedPlaylists']['uploads']


def already_uploaded(api, playlist, marker):
    # All pages, including private uploads. Fail closed if listing fails.
    token = None
    while True:
        page = api.playlistItems().list(part='snippet', playlistId=playlist,
                                       maxResults=50, pageToken=token).execute()
        if any(marker in item['snippet'].get('description', '') for item in page.get('items', [])):
            return True
        token = page.get('nextPageToken')
        if not token:
            return False


def upload(api, data, video, marker):
    from googleapiclient.http import MediaFileUpload
    privacy = os.getenv('YOUTUBE_PRIVACY', 'private')
    if privacy not in ('private', 'unlisted', 'public'):
        raise ValueError('Invalid YOUTUBE_PRIVACY')
    body = {'snippet': {'title': data['title'] + ' #Shorts',
                        'description': data['description'] + '\n\nAI-generated animation and narration using Google Veo.\n#Shorts #MiniMarvelsNaira\n' + marker,
                        'categoryId': '27', 'tags': ['Mini Marvels Naira', 'kids learning', 'Shorts']},
            'status': {'privacyStatus': privacy, 'selfDeclaredMadeForKids': True, 'containsSyntheticMedia': True}}
    request = api.videos().insert(part='snippet,status', body=body,
                                 media_body=MediaFileUpload(str(video), mimetype='video/mp4', resumable=True))
    response = None
    # Never restart an uncertain insert automatically. Check Studio before rerunning.
    while response is None:
        _, response = request.next_chunk(num_retries=0)
    return response['id']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--slot', type=int, choices=range(1, 5), default=1)
    parser.add_argument('--date', default=datetime.now(ZoneInfo('Asia/Kolkata')).date().isoformat())
    parser.add_argument('--upload', action='store_true')
    args = parser.parse_args()
    datetime.strptime(args.date, '%Y-%m-%d')
    marker = f'mmn-{args.date}-{args.slot}'
    folder = Path('output') / marker
    folder.mkdir(parents=True, exist_ok=True)
    api = None
    if args.upload:
        api, playlist = youtube()
        if already_uploaded(api, playlist, marker):
            print('Already uploaded:', marker)
            return
    require(['GOOGLE_CLOUD_PROJECT'])
    from google import genai
    client = genai.Client(vertexai=True, project=os.environ['GOOGLE_CLOUD_PROJECT'],
                          location=os.getenv('GOOGLE_CLOUD_LOCATION', 'us-central1'))
    script_file = folder / 'script.json'
    data = validate(json.loads(script_file.read_text())) if script_file.exists() else generate(client, args.date, args.slot)
    script_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    video = render(client, data, folder)
    if api:
        video_id = upload(api, data, video, marker)
        (folder / 'upload.json').write_text(json.dumps({'video_id': video_id, 'marker': marker}))
        print('Uploaded: https://youtu.be/' + video_id)
    else:
        print('Render complete:', video)


if __name__ == '__main__':
    main()
