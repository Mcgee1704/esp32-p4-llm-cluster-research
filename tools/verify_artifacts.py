"""Read-only verification of actual built images, partition tables and model."""
import hashlib
import json
import pathlib
import struct
import sys
import zlib
from esptool.bin_image import LoadFirmwareImage

root=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.local/tooling/esp-idf/components/partition_table'))
from gen_esp32part import PartitionTable

model=(root/'.local/models/stories15M.p4lm').read_bytes()
assert model[:8]==b'P4LM0001'
assert model[48:80]==hashlib.sha256(model[:48]+model[128:]).digest()
assert struct.unpack_from('<I',model,80)[0]==zlib.crc32(model[128:])
report={'model_bytes':len(model),'model_sha256':hashlib.sha256(model).hexdigest(),'hardware_tested':False,'variants':{}}
for revision,expected in [('rev1',(100,199)),('rev3',(300,399))]:
    folder=root/'.local/build'/revision
    table=PartitionTable.from_binary((folder/'partition_table/partition-table.bin').read_bytes())
    table.verify();table.verify_size_fits(32*1024*1024)
    parts={p.name:p for p in table}
    assert len(model)<=parts['model'].size
    app=folder/'p4_tinystories.bin'
    image=LoadFirmwareImage('esp32p4',str(app));image.verify()
    assert image.stored_digest==image.calc_digest
    assert (image.min_rev_full,image.max_rev_full)==expected
    assert app.stat().st_size<=min(parts['ota_0'].size,parts['ota_1'].size)
    boot=LoadFirmwareImage('esp32p4',str(folder/'bootloader/bootloader.bin'))
    boot.verify();assert boot.stored_digest==boot.calc_digest
    assert (boot.min_rev_full,boot.max_rev_full)==expected
    assert 'CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y' in (folder/'sdkconfig').read_text()
    report['variants'][revision]={'bytes':app.stat().st_size,'sha256':hashlib.sha256(app.read_bytes()).hexdigest(),
        'chip_revision_min':expected[0],'chip_revision_max':expected[1],
        'partitions':{p.name:{'offset':p.offset,'size':p.size} for p in table}}
(root/'.local/build/artifact-verification.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,indent=2))
