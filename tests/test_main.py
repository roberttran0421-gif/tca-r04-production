import unittest, tempfile, wave
from pathlib import Path
from src.main import SCENE_IDS, srt_time, get_scenes, tone_wav
class Check(unittest.TestCase):
    def test_19(self): self.assertEqual(len(SCENE_IDS), 19)
    def test_clock(self): self.assertEqual(srt_time(1.5), "00:00:01,500")
    def test_fixture(self): self.assertEqual(len(get_scenes(None)), 19)
    def test_wave(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"test.wav"
            tone_wav(p, .2)
            with wave.open(str(p),"rb") as w: self.assertEqual(w.getframerate(),24000)
if __name__=="__main__": unittest.main()
