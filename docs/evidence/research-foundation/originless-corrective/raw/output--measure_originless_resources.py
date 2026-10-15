import json
import shutil
from pathlib import Path

root = Path(__file__).resolve().parents[1]
native = root.parent.parent / 'a718' / 'QuantMesh'
owned = Path('/var/tmp/quantmesh-linux-native-90afdbee6add43169483520e384539ae')
assert json.loads((owned/'ownership.json').read_text())['nonce'] == '90afdbee6add43169483520e384539ae'
prior = json.loads((native/'output/172-task2-construction-20261013/final-resources.json').read_text())
def size(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())
original_tests = 8457206
test_growth = size(owned/'task2-tests') - original_tests
assert test_growth >= 0
names = ('check_loaded_numeric_origins.py', 'inspect_numeric_helpers.py', 'inspect_numeric_helpers-harness-failed.py',
         'probe_numeric_callback_providers.py', 'audit_current_failure.py', 'measure_originless_resources.py')
extra_files = [root/'output'/n for n in names]
extra_files += list((root/'output/0038-linux-native-admission').glob('task2-*numeric*'))
extra_files += [root/'output/0038-linux-native-admission/task2-unlocated-helper-diagnosis.md']
extra_files += list((root/'output/0038-worker-ci-fixture-policy').rglob('*'))
extra_files += [root/'docs/superpowers/plans/2026-10-13-originless-numerical-provenance.md']
bytes_added = sum(p.stat().st_size for p in extra_files if p.is_file())
result = dict(original_baseline_bytes=8876772, accepted_construction_upper=prior['introduced_logical_upper_bound'],
              owned_test_growth=test_growth, additional_root_bytes=bytes_added,
              correction_source_archive_git_forecast=600000, limit_bytes=12000000,
              free_c_bytes=shutil.disk_usage('/mnt/c').free,
              whole_C_attribution='PENDING/no reset/no materialization waiver',
              scope='same original software scope plus all root helper and CI fixture additions; future allowance conservative')
result['introduced_logical_upper_bound'] = prior['introduced_logical_upper_bound'] + test_growth + bytes_added + 600000
assert result['introduced_logical_upper_bound'] <= result['limit_bytes']
assert result['free_c_bytes'] >= 50000000000
(root/'output/0038-linux-native-admission/originless-resource-intake.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
