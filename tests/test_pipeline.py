import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import MagicMock, patch
import pipeline as p


def script():
    return {'title': 'A little seed', 'description': 'Learn how seeds grow.', 'scenes': [
        {'caption': 'A seed needs water', 'narration': 'A little seed wakes in the warm garden.',
         'visual': 'The rabbit waters a seed. Slow camera push in.'} for _ in range(4)]}


class PipelineTests(unittest.TestCase):
    def test_rejects_missing_scene(self):
        data = script(); data['scenes'].pop()
        with self.assertRaises(ValueError): p.validate(data)

    def test_rejects_unbounded_narration(self):
        data = script(); data['scenes'][0]['narration'] = 'a' * 301
        with self.assertRaises(ValueError): p.validate(data)

    def test_topics_stable_and_slot_specific(self):
        self.assertEqual(p.topic_for('2026-10-26', 1), p.topic_for('2026-10-26', 1))
        self.assertNotEqual(p.topic_for('2026-10-26', 1), p.topic_for('2026-10-26', 2))

    def test_prompt_preserves_identity_and_telugu(self):
        scene = script()['scenes'][0]; scene['narration'] = 'చిన్న విత్తనం పెరుగుతుంది.'
        prompt = p.veo_prompt(scene)
        self.assertIn('sky-blue waistcoat', prompt)
        self.assertIn(scene['narration'], prompt)
        self.assertIn('off-screen', prompt)

    def test_duplicate_in_later_playlist_page(self):
        api = MagicMock()
        api.playlistItems.return_value.list.return_value.execute.side_effect = [
            {'items': [], 'nextPageToken': 'next'},
            {'items': [{'snippet': {'description': 'mmn-2026-10-26-1'}}]}]
        self.assertTrue(p.already_uploaded(api, 'uploads', 'mmn-2026-10-26-1'))
        self.assertEqual(api.playlistItems.return_value.list.call_count, 2)

    def test_playlist_failure_blocks(self):
        api = MagicMock()
        api.playlistItems.return_value.list.return_value.execute.side_effect = RuntimeError('network')
        with self.assertRaises(RuntimeError): p.already_uploaded(api, 'uploads', 'marker')

    def test_upload_private_kids_disclosure(self):
        api = MagicMock()
        api.videos.return_value.insert.return_value.next_chunk.return_value = (None, {'id': 'video123'})
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'YOUTUBE_PRIVACY': 'private'}):
            video = Path(temp)/'video.mp4'; video.write_bytes(b'test')
            self.assertEqual(p.upload(api, script(), video, 'unique-marker'), 'video123')
        call = api.videos.return_value.insert.call_args.kwargs
        self.assertEqual(call['body']['status'], {'privacyStatus': 'private', 'selfDeclaredMadeForKids': True, 'containsSyntheticMedia': True})
        self.assertIn('unique-marker', call['body']['snippet']['description'])
        api.videos.return_value.insert.return_value.next_chunk.assert_called_once_with(num_retries=0)

    def test_wrong_channel_blocks(self):
        values = {n: 'test' for n in ['YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN', 'YOUTUBE_CHANNEL_ID']}
        api = MagicMock(); api.channels.return_value.list.return_value.execute.return_value = {'items': [{'id': 'other'}]}
        with patch.dict(os.environ, values), patch('google.oauth2.credentials.Credentials'), patch('googleapiclient.discovery.build', return_value=api):
            with self.assertRaisesRegex(ValueError, 'differs'): p.youtube()

    def test_existing_clip_skips_paid_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp)/'raw.mp4'; raw.write_bytes(b'video')
            client = MagicMock()
            p.generate_clip(client, script()['scenes'][0], raw, Path(temp)/'op.json')
            client.models.generate_videos.assert_not_called()

    def test_filtered_generation_blocks(self):
        client = MagicMock()
        client.models.generate_videos.return_value = NS(name='operation1', done=True, error=None, response=NS(generated_videos=[]))
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(RuntimeError, 'no video'):
                p.generate_clip(client, script()['scenes'][0], Path(temp)/'raw.mp4', Path(temp)/'op.json')

    def test_resume_without_new_charge(self):
        client = MagicMock()
        client.operations.get.return_value = NS(done=True, error=None, response=NS(generated_videos=[NS(video=NS(video_bytes=b'video'))]))
        with tempfile.TemporaryDirectory() as temp:
            raw, op = Path(temp)/'raw.mp4', Path(temp)/'op.json'
            op.write_text(json.dumps({'name': 'saved-operation'}))
            p.generate_clip(client, script()['scenes'][0], raw, op)
            self.assertEqual(raw.read_bytes(), b'video')
            client.models.generate_videos.assert_not_called()

    def test_real_ffmpeg_motion_audio_and_concat(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); raw = folder/'fixture.mp4'
            p.run('ffmpeg', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=360x640:rate=24',
                  '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                  '-t', '8', '-c:v', 'libx264', '-preset', 'ultrafast', '-c:a', 'aac', raw)
            def fake_generate(client, scene, path, operation, first_frame=None):
                path.write_bytes(raw.read_bytes())
            with patch.object(p, 'generate_clip', side_effect=fake_generate):
                video = p.render(MagicMock(), script(), folder)
            self.assertAlmostEqual(p.duration(video), 32, delta=0.3)
            self.assertTrue((folder/'thumbnail.jpg').exists())
            streams = json.loads(p.run('ffprobe', '-v', 'error', '-show_streams', '-of', 'json', video))['streams']
            visual = next(s for s in streams if s['codec_type'] == 'video')
            self.assertEqual((visual['width'], visual['height']), (720,1280))
            self.assertTrue(any(s['codec_type'] == 'audio' for s in streams))


if __name__ == '__main__': unittest.main()
