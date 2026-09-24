import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('build_release',ROOT/'tools/build_release.py')
module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)

class ReleaseTests(unittest.TestCase):
    def test_deterministic_archives_and_self_contained_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            first=module.build(out/'a'); second=module.build(out/'b')
            self.assertEqual(first['files'],second['files'])
            skill=out/'a'/f"assetkit-skill-v{first['version']}.zip"
            with zipfile.ZipFile(skill) as z:
                names=z.namelist()
                self.assertIn('assetkit/scripts/ledger.py',names)
                self.assertIn('assetkit/scripts/catalog.py',names)
                self.assertIn('assetkit/scripts/profiles.py',names)
                self.assertEqual(sum(n.endswith('/SKILL.md') for n in names),1)
                self.assertFalse(any('/.assets/' in n or '__pycache__' in n for n in names))
    def test_versions_match(self): self.assertEqual(module.version(),'1.1.0')

if __name__=='__main__': unittest.main()
