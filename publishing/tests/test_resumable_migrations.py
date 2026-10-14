"""Only the explicitly approved, independently hashed source stage can migrate."""
import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'publishing'))
import checkpoint_migrations as migration


class SourcePackageMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.cp=self.root/'checkpoint';self.source=self.cp/'sources/illinois'
        self.source.mkdir(parents=True)
        raw=b'unchanged raw source crop';digest=hashlib.sha256(raw).hexdigest()
        (self.source/'crop.part-0000').write_bytes(raw)
        receipt={'crop':{'encoding':'raw','bytes':len(raw),'sha256':digest,
            'parts':[{'path':'crop.part-0000','bytes':len(raw),'sha256':digest}]}}
        (self.source/'receipt.json').write_text(json.dumps(receipt))
        self.checkpoint={'codeFingerprint':migration.FROM_CODE,'config':{'id':'chicagoland'},
            'purpose':'refresh','sourcePlan':{'planId':'pinned-plan','runtime':{'python':'pinned'}},
            'generationId':'same-generation','files':{'source':'same-inventory'},
            'progress':{'completedStates':['illinois'],'indexReady':False,'batchIds':[],
                'batchCount':0,'completedBatches':[]},'nextStage':{'kind':'source','state':'wisconsin'},
            'failureCount':0,'needsAttention':False}
        from rollout_snapshot import _records
        self.checkpoint['files']=_records(self.cp,include_metadata=True)
        (self.cp/'checkpoint.json').write_text(json.dumps(self.checkpoint))
        self.pin=patch.object(migration,'FROM_DESCRIPTOR',hashlib.sha256((self.cp/'checkpoint.json').read_bytes()).hexdigest())
        self.pin.start();self.addCleanup(self.pin.stop)

    def eligible(self):return migration.eligible(self.cp,self.checkpoint,ROOT)

    def test_exact_source_only_descriptor_migrates_without_touching_any_file(self):
        before={p.relative_to(self.cp).as_posix():p.read_bytes() for p in self.cp.rglob('*') if p.is_file()}
        self.assertTrue(self.eligible())
        result=migration.migrate(self.cp,self.checkpoint,ROOT,target_fingerprint='a'*64,
            verified_fingerprint='a'*64,now=dt.datetime(2026,10,14,tzinfo=dt.timezone.utc))
        self.assertEqual({k:v for k,v in result.items() if k not in ('codeFingerprint','migration')},
                         {k:v for k,v in self.checkpoint.items() if k!='codeFingerprint'})
        self.assertEqual(result['migration']['fromCodeFingerprint'],migration.FROM_CODE)
        self.assertEqual(result['migration']['preservedSourcePlanId'],'pinned-plan')
        self.assertEqual(before,{p.relative_to(self.cp).as_posix():p.read_bytes() for p in self.cp.rglob('*') if p.is_file()})

    def test_old_identity_or_progress_changes_are_not_eligible(self):
        for mutate in (lambda c:c.update(codeFingerprint='0'*64),
                       lambda c:c.update(generationId='different'),
                       lambda c:c['progress'].update(indexReady=True),
                       lambda c:c['sourcePlan'].update(runtime={'python':'changed'})):
            with self.subTest(mutate=mutate):
                before=copy.deepcopy(self.checkpoint);mutate(self.checkpoint)
                self.assertFalse(self.eligible());self.checkpoint=before
        (self.cp/'checkpoint.json').write_text(json.dumps(self.checkpoint)+'\n')
        self.assertFalse(self.eligible())

    def test_test_receipt_mismatch_cannot_authorize_migration(self):
        with self.assertRaisesRegex(ValueError,'not authorized'):
            migration.migrate(self.cp,self.checkpoint,ROOT,target_fingerprint='a'*64,
                              verified_fingerprint='b'*64,now=dt.datetime.now(dt.timezone.utc))

    def test_corrupt_crop_or_inconsistent_whole_hash_is_refused(self):
        (self.source/'crop.part-0000').write_bytes(b'corrupt')
        self.assertFalse(self.eligible())
        raw=b'unchanged raw source crop'
        (self.source/'crop.part-0000').write_bytes(raw)
        receipt=json.loads((self.source/'receipt.json').read_text());receipt['crop']['sha256']='f'*64
        (self.source/'receipt.json').write_text(json.dumps(receipt))
        self.assertFalse(self.eligible())

    def test_changed_source_semantics_or_dependency_is_refused(self):
        with patch.object(migration,'SOURCE_SEMANTICS','0'*64):self.assertFalse(self.eligible())
        with patch.dict(migration.PROTECTED_FILES,{'tools/build_region.py':'0'*64}):self.assertFalse(self.eligible())

    def test_source_semantics_fingerprint_ignores_only_new_packaging_boundary(self):
        path=self.root/'tools/resumable_region.py';path.parent.mkdir()
        original=(ROOT/'tools/resumable_region.py').read_text();path.write_text(original)
        self.assertEqual(migration.source_semantics(self.root),migration.SOURCE_SEMANTICS)
        path.write_text(original+'\n# comment only\n')
        self.assertEqual(migration.source_semantics(self.root),migration.SOURCE_SEMANTICS)
        path.write_text(original.replace("'Pinned source checksum mismatch; refusing replacement'","'changed acquisition'"))
        self.assertNotEqual(migration.source_semantics(self.root),migration.SOURCE_SEMANTICS)


if __name__=='__main__':unittest.main()
