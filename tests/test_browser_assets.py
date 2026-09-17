from pathlib import Path


def test_brain_coordinate_reader_uses_float32_byte_offsets():
    text = Path('site/assets/brain.js').read_text(encoding='utf-8')
    assert 'start+i*12+4,true' in text
    assert 'start+i*12+8,true' in text
    assert 'start+i*12+1,true' not in text
    assert 'start+i*12+2,true' not in text


def test_brain_viewer_has_runtime_guards():
    text = Path('site/assets/brain.js').read_text(encoding='utf-8')
    assert 'maxPixels=1800000' in text
    assert 'relatedVisible=false' in text
    assert 'length:2' in text  # only two progressive ROI loaders


def test_ci_does_not_ship_raw_network_payload_to_overview():
    app = Path('site/assets/app.js').read_text(encoding='utf-8')
    site = Path('src/dsc/site.py').read_text(encoding='utf-8')
    assert "getJSON('data/network.json')" not in app
    assert 'data_dir / "network.json"' not in site


def test_findings_ui_exposes_v04_control_fields():
    app = Path('site/assets/app.js').read_text(encoding='utf-8')
    html = Path('site/findings.html').read_text(encoding='utf-8')
    assert 'robustnessLabel' in app
    assert 'ROI overlap' in app
    assert 'finding-status' in html
    assert 'survived_controls' in html


def test_state_lab_is_reproducible_and_explicitly_model_based():
    js = Path('site/assets/state-lab.js').read_text(encoding='utf-8')
    html = Path('site/state-lab.html').read_text(encoding='utf-8')
    assert 'candidate knockout' in html
    assert 'medianize candidate inputs' in html
    assert 'DAT clearance' in html
    assert 'Dop1R1 gain' in html and 'Dop1R2 gain' in html and 'Dop2R gain' in html
    assert 'export run JSON' in html
    assert 'simulated event raster' in html
    assert 'lab-3d-canvas' in html
    assert 'state-lab-3d.js' in html
    assert 'simulate(p' in js
    assert 'buildEvents' in js
    assert "data/experiments/001_pam04.json" in js
    live3d = Path('site/assets/state-lab-3d.js').read_text(encoding='utf-8')
    assert 'source_skeleton_url_template' in live3d
    assert '001_pam04_synapses.json' in live3d
    assert 'simulated pulse' in html


def test_3d_viewer_accepts_manual_state_lab_focus():
    app = Path('site/assets/app.js').read_text(encoding='utf-8')
    assert "params.get('focus')" in app
    assert 'manual_focus' in app
