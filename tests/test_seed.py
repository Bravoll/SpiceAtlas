import gzip
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from atlas.seed import ensure_baseline
from atlas.workspaces import Workspaces

class CompressedSeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / 'catalogue.sqlite3'
        with sqlite3.connect(self.source) as db:
            db.execute('CREATE TABLE marker(value TEXT)')
            db.execute("INSERT INTO marker VALUES('bundled')")
        self.raw = self.source.read_bytes()
        self.source.with_suffix('.sqlite3.gz').write_bytes(gzip.compress(self.raw,mtime=0))
        self.manifest = self.root / 'catalogue_seed.json'
        self.manifest.write_text(json.dumps({'uncompressed_bytes':len(self.raw),'sha256':hashlib.sha256(self.raw).hexdigest()}))
        self.source.unlink()
    def tearDown(self):self.temp.cleanup()
    def test_first_start_restores_exact_database(self):
        ensure_baseline(self.source)
        self.assertEqual(self.source.read_bytes(),self.raw)
    def test_existing_database_is_preserved(self):
        self.source.write_bytes(b'local database')
        ensure_baseline(self.source)
        self.assertEqual(self.source.read_bytes(),b'local database')
    def test_wrong_hash_does_not_publish_partial_file(self):
        data=json.loads(self.manifest.read_text());data['sha256']='0'*64;self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):ensure_baseline(self.source)
        self.assertFalse(self.source.exists());self.assertEqual(list(self.root.glob('catalogue-*.tmp')),[])
    def test_oversize_seed_is_rejected(self):
        data=json.loads(self.manifest.read_text());data['uncompressed_bytes']=1;self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):ensure_baseline(self.source)
        self.assertFalse(self.source.exists())
    def test_initial_workspace_can_start_with_only_compressed_seed(self):
        manager=Workspaces(self.root,self.source)
        folder=manager.directory()
        with sqlite3.connect(folder/'catalogue.sqlite3') as db:
            self.assertEqual(db.execute('SELECT value FROM marker').fetchone()[0],'bundled')
