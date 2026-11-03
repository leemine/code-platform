"""Exercise portable equipment files with a GBK platform default."""
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def modules(monkeypatch):
    # Load the file boundary without starting the application or model catalog.
    root = Path(__file__).resolve().parents[3]
    directory = root / 'jiuwenswarm/server/runtime/agent_adapter/providers'
    package = '_opencode_encoding_test'
    namespace = types.ModuleType(package)
    namespace.__path__ = [str(directory)]
    monkeypatch.setitem(sys.modules, package, namespace)
    for name in ['opencode_transport', 'opencode_models']:
        module = types.ModuleType(f'{package}.{name}')
        monkeypatch.setitem(sys.modules, module.__name__, module)
    sys.modules[f'{package}.opencode_models'].build_server_model_config = lambda: ({}, None)
    result = []
    for name in ['opencode_equipment', 'opencode_service']:
        spec = importlib.util.spec_from_file_location(f'{package}.{name}', directory / f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        result.append(module)
    return result


def gbk_default(monkeypatch):
    original = Path.open

    def open_file(self, mode='r', buffering=-1, encoding=None, errors=None, newline=None):
        if 'b' not in mode and encoding in (None, 'locale'):
            encoding = 'gbk'
        return original(self, mode, buffering, encoding, errors, newline)

    monkeypatch.setattr(Path, 'open', open_file)


@pytest.mark.asyncio
async def test_skill_and_config_written_as_utf8(modules, monkeypatch, tmp_path):
    equipment_module, service_module = modules
    source = tmp_path / 'source'
    source.mkdir()
    text = '---\nname: demo\ndescription: 中文\n---\n⛔ 😀'
    (source / 'SKILL.md').write_text(text, encoding='utf-8')
    (source / 'resource.bin').write_bytes(b'\x00\xff')
    equipment = equipment_module.Equipment()
    equipment_module.add_skill(equipment, source)
    service = service_module.SessionService.__new__(service_module.SessionService)
    service.root = tmp_path / 'session'
    service.root.mkdir()
    service.process = service.client = service.revision = None
    service.executable = 'unused-cli'
    service.directory = str(tmp_path)

    async def spawn(*args, **kwargs):
        assert (service.root / 'skills/0/SKILL.md').read_text(encoding='utf-8') == text
        assert (service.root / 'skills/0/resource.bin').read_bytes() == b'\x00\xff'
        config = json.loads((service.root / 'opencode.json').read_text(encoding='utf-8'))
        assert config['permission']['skill']['demo'] == 'ask'
        raise RuntimeError('reached provider startup')

    monkeypatch.setattr(service_module.asyncio, 'create_subprocess_exec', spawn)
    gbk_default(monkeypatch)
    with pytest.raises(RuntimeError, match='reached provider startup'):
        await service.configure(equipment)


def test_package_manifest_and_persona_read_as_utf8(modules, monkeypatch, tmp_path):
    equipment_module, _ = modules
    text = '中文 ⛔ 😀'
    (tmp_path / 'persona').mkdir()
    (tmp_path / 'persona/rules.md').write_text(text, encoding='utf-8')
    manifest = {'description': text, 'persona': {'dir': 'persona'}}
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
    gbk_default(monkeypatch)
    equipment = equipment_module.Equipment()
    equipment_module.read_package(equipment, tmp_path, template=True)
    assert equipment.system == text
