"""Verify compact evidence package without training or database access."""
from pathlib import Path
import gzip, hashlib, json, zipfile, csv
root=Path(__file__).resolve().parent
manifest=json.loads((root/'evidence/source_manifest.json').read_text(encoding='utf-8'))
sha=lambda b:hashlib.sha256(b).hexdigest()
for f in manifest['public_files']:
    b=(root/f['path']).read_bytes()
    assert len(b)==f['bytes'] and sha(b)==f['sha256'],f['path']
bundles={}
for item in manifest['log_members']:
    path=item['bundle']
    if path not in bundles:bundles[path]=gzip.decompress((root/path).read_bytes())
    marker=(item['header']+'\n').encode('utf-8')
    content=bundles[path].split(marker,1)[1][:item['public_text_bytes']]
    assert sha(content)==item['public_text_sha256'],item['source_path']
models=json.loads((root/'evidence/model_inventory.json').read_text(encoding='utf-8'))
metrics={r['run_id']:r for r in csv.DictReader((root/'metrics.csv').open(encoding='utf-8-sig'))}
assert len(models['models'])==13
for m in models['models']:assert metrics[m['run_id']]['model_sha256']==m['sha256'],m['run_id']
assert sum(m['bytes'] for m in models['models'])==models['total_model_bytes']
with zipfile.ZipFile(root/'evidence/source_snapshots.zip') as z:
    assert z.testzip() is None
    for item in manifest['source_snapshot_members']:
        assert sha(z.read(item['path']))==item['public_sha256'],item['path']
print(json.dumps({'status':'PASS','training_runs':13,'logs':len(manifest['log_members']),'public_files_checked':len(manifest['public_files']),'model_hashes_match':True,'model_binaries_in_package':False},indent=2))
